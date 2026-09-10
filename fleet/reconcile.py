"""Observe the OSWM fleet and emit one deterministic health report."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fleet.github import GitHubClient, GitHubError
from fleet.registry import FleetNode, FleetPolicy, load_registry


EXPECTED_WORKFLOWS = {
    "daily": "data_daily_updating.yml",
    "weekly": "weekly.yml",
    "sync": "update_codebase.yml",
    "pages": "pages.yml",
}
SHA = re.compile(r"^[0-9a-f]{40}$")


def literal_assignments(source: str) -> dict[str, Any]:
    tree = ast.parse(source, filename="config.py")
    values: dict[str, Any] = {}
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)) or statement.value is None:
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                values[target.id] = ast.literal_eval(statement.value)
            except (TypeError, ValueError):
                continue
    return values


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def previous_scheduled_time(cron: object, now: datetime) -> datetime:
    """Resolve the fixed daily/weekly cron shapes supported by node config."""

    fields = str(cron).split()
    if len(fields) != 5:
        raise ValueError("cron must have five fields")
    minute, hour, day, month, weekday = fields
    if day != "*" or month != "*" or not minute.isdigit() or not hour.isdigit():
        raise ValueError("fleet health supports fixed daily or weekly UTC crons")
    minute_number = int(minute)
    hour_number = int(hour)
    if not 0 <= minute_number <= 59 or not 0 <= hour_number <= 23:
        raise ValueError("cron contains an invalid UTC time")

    now = now.astimezone(timezone.utc)
    candidate = now.replace(
        hour=hour_number,
        minute=minute_number,
        second=0,
        microsecond=0,
    )
    if weekday == "*":
        if candidate > now:
            candidate -= timedelta(days=1)
        return candidate

    if not weekday.isdigit() or int(weekday) not in range(0, 8):
        raise ValueError("fleet health supports one numeric weekly weekday")
    cron_weekday = int(weekday) % 7
    python_weekday = (cron_weekday - 1) % 7
    candidate -= timedelta(days=(candidate.weekday() - python_weekday) % 7)
    if candidate > now:
        candidate -= timedelta(days=7)
    return candidate


def _run_view(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not run:
        return None
    return {
        "id": run.get("id"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "run_attempt": run.get("run_attempt"),
        "head_sha": run.get("head_sha"),
        "url": run.get("html_url"),
    }


def _workflow_runs(runs: list[dict[str, Any]], filename: str) -> list[dict[str, Any]]:
    matching = [
        run
        for run in runs
        if isinstance(run, dict)
        and isinstance(run.get("path"), str)
        and Path(run["path"]).name == filename
    ]
    return sorted(
        matching,
        key=lambda run: parse_time(run.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def _issue(issues: list[dict[str, str]], level: str, code: str, message: str) -> None:
    issues.append({"level": level, "code": code, "message": message})


def inspect_node(
    node: FleetNode,
    policy: FleetPolicy,
    client: GitHubClient,
    *,
    now: datetime,
    desired_sha: str | None,
    desired_managed_revision: int | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": node.id,
        "repository": node.repository,
        "role": node.role,
        "enabled": node.enabled,
        "branch": node.branch,
        "pages_url": node.pages_url,
        "rollout_wave": node.rollout_wave,
        "status": "paused" if not node.enabled else "healthy",
        "issues": [],
        "workflows": {},
    }
    if not node.enabled:
        return result

    issues: list[dict[str, str]] = result["issues"]
    try:
        snapshot = client.node_snapshot(node.repository, node.branch, policy.workflow_history)
    except (GitHubError, ValueError, TypeError) as error:
        _issue(issues, "error", "repository_unreachable", str(error))
        result["status"] = "unreachable"
        return result

    try:
        config = literal_assignments(snapshot["config_text"])
    except (SyntaxError, TypeError, KeyError) as error:
        config = {}
        _issue(issues, "error", "invalid_node_config", str(error))

    core_sha = snapshot.get("core_sha")
    result["core_sha"] = core_sha
    if desired_sha and core_sha != desired_sha:
        _issue(
            issues,
            "warning",
            "core_revision_behind",
            f"node pins {core_sha or 'no core revision'}; desired is {desired_sha}",
        )

    managed_revision = None
    managed_source_revision = None
    try:
        managed = json.loads(snapshot["managed_text"])
        if isinstance(managed, dict):
            managed_revision = managed.get("managed_revision")
            managed_source_revision = managed.get("source_revision")
    except (json.JSONDecodeError, TypeError, KeyError):
        _issue(issues, "warning", "invalid_managed_state", ".oswm-managed-files.json is invalid")
    result["managed_workflow_revision"] = managed_revision
    result["managed_workflow_source_sha"] = managed_source_revision
    if desired_managed_revision is not None and managed_revision != desired_managed_revision:
        _issue(
            issues,
            "warning",
            "managed_workflows_behind",
            f"managed workflows report revision {managed_revision or 'legacy'}; "
            f"desired is {desired_managed_revision}",
        )

    workflows = snapshot.get("workflows", [])
    runs = snapshot.get("runs", [])
    workflow_index = {
        Path(workflow["path"]).name: workflow
        for workflow in workflows
        if isinstance(workflow, dict) and isinstance(workflow.get("path"), str)
    }
    active_run = False
    stale = False
    warning_delay = timedelta(minutes=policy.schedule_warning_minutes)
    grace = timedelta(minutes=policy.schedule_grace_minutes)

    for kind, filename in EXPECTED_WORKFLOWS.items():
        workflow = workflow_index.get(filename)
        matching_runs = _workflow_runs(runs, filename)
        latest = matching_runs[0] if matching_runs else None
        latest_success = next(
            (run for run in matching_runs if run.get("conclusion") == "success"),
            None,
        )
        view = {
            "filename": filename,
            "state": workflow.get("state") if workflow else "missing",
            "latest": _run_view(latest),
            "latest_success": _run_view(latest_success),
        }
        result["workflows"][kind] = view

        if workflow is None:
            _issue(issues, "error", f"{kind}_workflow_missing", f"{filename} is missing")
            stale = True
            continue
        if workflow.get("state") != "active":
            _issue(
                issues,
                "error",
                f"{kind}_workflow_disabled",
                f"{filename} is {workflow.get('state')}",
            )
            stale = True

        if latest and latest.get("status") in {"queued", "in_progress", "waiting", "pending"}:
            active_run = True
        elif latest and latest.get("conclusion") not in {None, "success", "skipped"}:
            _issue(
                issues,
                "warning",
                f"{kind}_latest_failed",
                f"latest {filename} run concluded {latest.get('conclusion')}",
            )

        cron_setting = {
            "daily": "NODE_DAILY_CRON",
            "weekly": "NODE_WEEKLY_CRON",
        }.get(kind)
        if not cron_setting:
            continue
        cron = config.get(cron_setting)
        try:
            expected = previous_scheduled_time(cron, now)
            view["previous_scheduled_at"] = expected.isoformat().replace("+00:00", "Z")
        except ValueError as error:
            _issue(issues, "warning", f"unsupported_{kind}_cron", f"{cron_setting}: {error}")
            continue
        success_time = parse_time(latest_success.get("updated_at")) if latest_success else None
        latest_time = parse_time(latest.get("created_at")) if latest else None
        current_cycle_running = bool(
            latest
            and latest.get("status") in {"queued", "in_progress", "waiting", "pending"}
            and latest_time
            and latest_time >= expected
        )
        current_cycle_succeeded = success_time is not None and success_time >= expected
        if not current_cycle_running and not current_cycle_succeeded:
            expected_text = expected.isoformat().replace("+00:00", "Z")
            if now > expected + grace:
                _issue(
                    issues,
                    "error",
                    f"{kind}_overdue",
                    f"no successful {kind} run after {expected_text}",
                )
                stale = True
            elif now > expected + warning_delay:
                _issue(
                    issues,
                    "warning",
                    f"{kind}_delayed",
                    f"no successful {kind} run after {expected_text}; within grace period",
                )

    pages = client.probe_url(node.pages_url)
    result["pages"] = pages
    if not pages.get("ok"):
        _issue(
            issues,
            "error",
            "pages_unavailable",
            f"Pages probe returned {pages.get('status') or pages.get('error') or 'an error'}",
        )
        stale = True

    if stale:
        result["status"] = "stale"
    elif active_run:
        result["status"] = "updating"
    elif issues:
        result["status"] = "degraded"
    return result


def reconcile(
    registry_path: str | Path,
    client: GitHubClient,
    *,
    now: datetime | None = None,
    desired_sha: str | None = None,
    desired_managed_revision: int | None = None,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if desired_sha is not None:
        desired_sha = desired_sha.strip().lower()
        if not SHA.fullmatch(desired_sha):
            raise ValueError("desired core revision must be a full 40-character SHA")

    def inspect(registered_node: FleetNode) -> dict[str, Any]:
        return inspect_node(
            registered_node,
            registry.policy,
            client,
            now=observed_at,
            desired_sha=desired_sha,
            desired_managed_revision=desired_managed_revision,
        )

    # Node reads are independent. Keeping the pool bounded by the registry
    # prevents a slow or unavailable Pages site from serially delaying every
    # other fleet observation while avoiding unbounded API fan-out.
    with ThreadPoolExecutor(max_workers=min(8, len(registry.nodes))) as executor:
        nodes = list(executor.map(inspect, registry.nodes))
    counts = Counter(node["status"] for node in nodes)
    return {
        "schema_version": 1,
        "generated_at": observed_at.isoformat().replace("+00:00", "Z"),
        "desired_core_sha": desired_sha,
        "desired_managed_workflow_revision": desired_managed_revision,
        "summary": {key: counts.get(key, 0) for key in (
            "healthy", "updating", "degraded", "stale", "unreachable", "paused"
        )},
        "nodes": nodes,
    }


def _short_sha(value: object) -> str:
    return str(value)[:8] if value else "—"


def markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "## OSWM fleet status",
        "",
        f"Observed: `{report['generated_at']}`  ",
        f"Desired core: `{report.get('desired_core_sha') or 'not checked'}`",
        "",
        "| Node | Status | Core | Daily | Weekly | Pages | Issues |",
        "|---|---|---|---|---|---|---:|",
    ]
    for node in report["nodes"]:
        workflows = node.get("workflows", {})

        def conclusion(kind: str) -> str:
            latest = workflows.get(kind, {}).get("latest") or {}
            status = latest.get("status")
            if status == "completed":
                return str(latest.get("conclusion") or status)
            return str(status or latest.get("conclusion") or "—")

        pages = node.get("pages") or {}
        page_status = str(pages.get("status") or ("ok" if pages.get("ok") else "—"))
        lines.append(
            "| {id} | {status} | `{core}` | {daily} | {weekly} | {pages} | {issues} |".format(
                id=node["id"],
                status=node["status"],
                core=_short_sha(node.get("core_sha")),
                daily=conclusion("daily"),
                weekly=conclusion("weekly"),
                pages=page_status,
                issues=len(node.get("issues", [])),
            )
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="fleet/registry.toml")
    parser.add_argument("--output", default="fleet/status.json")
    parser.add_argument("--summary")
    parser.add_argument("--desired-sha", default=os.environ.get("GITHUB_SHA"))
    parser.add_argument(
        "--fail-on-status",
        action="append",
        choices=("healthy", "updating", "degraded", "stale", "unreachable", "paused"),
        default=[],
    )
    args = parser.parse_args(argv)

    registry = load_registry(args.registry)
    manifest_path = Path(args.registry).resolve().parent.parent / "workflows/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    desired_managed_revision = manifest.get("revision")
    if (
        isinstance(desired_managed_revision, bool)
        or not isinstance(desired_managed_revision, int)
        or desired_managed_revision <= 0
    ):
        parser.error("workflows/manifest.json must contain a positive integer revision")
    client = GitHubClient(
        token=os.environ.get("GH_TOKEN") or None,
        api_timeout_seconds=registry.policy.api_timeout_seconds,
        page_timeout_seconds=registry.policy.page_timeout_seconds,
    )
    report = reconcile(
        args.registry,
        client,
        desired_sha=args.desired_sha,
        desired_managed_revision=desired_managed_revision,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = markdown_summary(report)
    if args.summary:
        Path(args.summary).write_text(summary, encoding="utf-8")
    print(summary, end="")
    return 1 if any(report["summary"].get(status) for status in args.fail_on_status) else 0


if __name__ == "__main__":
    raise SystemExit(main())
