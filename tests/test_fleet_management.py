from __future__ import annotations

import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from fleet.reconcile import markdown_summary, previous_scheduled_time, reconcile
from fleet.registry import load_registry


ROOT = Path(__file__).resolve().parents[1]
REVISION = "a" * 40


class FakeClient:
    def __init__(self, snapshots, pages=None):
        self.snapshots = snapshots
        self.pages = pages or {}

    def node_snapshot(self, repository, branch, history):
        return self.snapshots[repository]

    def probe_url(self, url):
        return self.pages.get(url, {"ok": True, "status": 200, "url": url})


def _registry(tmp_path, *, enabled=True):
    path = tmp_path / "registry.toml"
    path.write_text(
        f'''schema_version = 1
[policy]
schedule_warning_minutes = 30
schedule_grace_minutes = 60
workflow_history = 20
api_timeout_seconds = 5
page_timeout_seconds = 5

[[nodes]]
id = "test-node"
repository = "example/test-node"
branch = "main"
role = "pilot"
enabled = {str(enabled).lower()}
rollout_wave = 1
pages_url = "https://example.github.io/test-node/"
''',
        encoding="utf-8",
    )
    return path


def _run(path, when, *, conclusion="success", status="completed"):
    return {
        "id": 1,
        "path": f".github/workflows/{path}",
        "status": status,
        "conclusion": conclusion,
        "created_at": when,
        "updated_at": when,
        "run_attempt": 1,
        "head_sha": "b" * 40,
        "html_url": "https://github.com/example/test-node/actions/runs/1",
    }


def _healthy_snapshot():
    workflows = [
        {"path": f".github/workflows/{name}", "state": "active"}
        for name in (
            "data_daily_updating.yml",
            "weekly.yml",
            "update_codebase.yml",
            "pages.yml",
        )
    ]
    return {
        "config_text": 'NODE_DAILY_CRON = "30 7 * * *"\nNODE_WEEKLY_CRON = "5 8 * * 0"\n',
        "core_sha": REVISION,
        "managed_text": json.dumps({
            "managed_revision": 2,
            "source_revision": REVISION,
        }),
        "workflows": workflows,
        "runs": [
            _run("data_daily_updating.yml", "2026-09-07T08:00:00Z"),
            _run("weekly.yml", "2026-09-06T09:00:00Z"),
            _run("update_codebase.yml", "2026-09-07T06:00:00Z"),
            _run("pages.yml", "2026-09-07T08:30:00Z"),
        ],
    }


def test_canonical_registry_is_valid_and_covers_current_fleet():
    registry = load_registry(ROOT / "fleet/registry.toml")
    assert {node.id for node in registry.nodes} == {
        "curitiba", "hiroshima", "lima", "milan", "oslo"
    }
    assert registry.nodes[0].role == "reference"
    assert all(node.enabled for node in registry.nodes)
    assert registry.policy.schedule_warning_minutes == 180
    assert registry.policy.schedule_grace_minutes == 420


def test_previous_scheduled_time_supports_daily_and_weekly_crons():
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)  # Monday
    assert previous_scheduled_time("30 7 * * *", now) == datetime(
        2026, 9, 7, 7, 30, tzinfo=timezone.utc
    )
    assert previous_scheduled_time("5 8 * * 0", now) == datetime(
        2026, 9, 6, 8, 5, tzinfo=timezone.utc
    )


def test_reconcile_reports_a_healthy_node(tmp_path):
    registry = _registry(tmp_path)
    client = FakeClient({"example/test-node": _healthy_snapshot()})
    report = reconcile(
        registry,
        client,
        now=datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
        desired_sha=REVISION,
        desired_managed_revision=2,
    )
    assert report["summary"]["healthy"] == 1
    assert report["nodes"][0]["issues"] == []
    assert "| test-node | healthy |" in markdown_summary(report)


def test_reconcile_separates_core_drift_from_overdue_runs(tmp_path):
    registry = _registry(tmp_path)
    snapshot = _healthy_snapshot()
    snapshot["core_sha"] = "b" * 40
    snapshot["managed_text"] = json.dumps({
        "managed_revision": 1,
        "source_revision": "c" * 40,
    })
    snapshot["runs"] = [
        _run("data_daily_updating.yml", "2026-09-06T08:00:00Z"),
        _run("weekly.yml", "2026-09-06T09:00:00Z"),
    ]
    report = reconcile(
        registry,
        FakeClient({"example/test-node": snapshot}),
        now=datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
        desired_sha=REVISION,
        desired_managed_revision=2,
    )
    node = report["nodes"][0]
    assert node["status"] == "stale"
    assert {issue["code"] for issue in node["issues"]} >= {
        "core_revision_behind",
        "managed_workflows_behind",
        "daily_overdue",
    }


def test_reconcile_warns_about_scheduler_lag_before_failing(tmp_path):
    registry = _registry(tmp_path)
    snapshot = _healthy_snapshot()
    snapshot["runs"][0] = _run(
        "data_daily_updating.yml", "2026-09-06T08:00:00Z"
    )
    report = reconcile(
        registry,
        FakeClient({"example/test-node": snapshot}),
        now=datetime(2026, 9, 7, 8, 15, tzinfo=timezone.utc),
        desired_sha=REVISION,
        desired_managed_revision=2,
    )
    node = report["nodes"][0]
    assert node["status"] == "degraded"
    assert {issue["code"] for issue in node["issues"]} == {"daily_delayed"}


def test_registry_rejects_warning_threshold_at_or_after_grace(tmp_path):
    registry = _registry(tmp_path)
    source = registry.read_text(encoding="utf-8").replace(
        "schedule_warning_minutes = 30", "schedule_warning_minutes = 60"
    )
    registry.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match="must be less than"):
        load_registry(registry)


def test_registry_derives_warning_threshold_for_legacy_policy(tmp_path):
    registry = _registry(tmp_path)
    source = registry.read_text(encoding="utf-8").replace(
        "schedule_warning_minutes = 30\n", ""
    )
    registry.write_text(source, encoding="utf-8")
    assert load_registry(registry).policy.schedule_warning_minutes == 30


def test_reconcile_marks_in_progress_runs_without_calling_them_stale(tmp_path):
    registry = _registry(tmp_path)
    snapshot = _healthy_snapshot()
    snapshot["runs"][0] = _run(
        "data_daily_updating.yml",
        "2026-09-07T09:30:00Z",
        conclusion=None,
        status="in_progress",
    )
    # The current cycle is still running after the schedule and grace period;
    # it must not be called overdue merely because it has not completed yet.
    snapshot["runs"].append(_run("data_daily_updating.yml", "2026-09-06T08:00:00Z"))
    report = reconcile(
        registry,
        FakeClient({"example/test-node": snapshot}),
        now=datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc),
        desired_sha=REVISION,
        desired_managed_revision=2,
    )
    assert report["nodes"][0]["status"] == "updating"


def test_registry_rejects_duplicate_repositories(tmp_path):
    registry = tmp_path / "registry.toml"
    registry.write_text(
        '''schema_version = 1
[[nodes]]
id = "first"
repository = "example/duplicate"
branch = "main"
role = "pilot"
enabled = true
rollout_wave = 0
pages_url = "https://example.github.io/first/"

[[nodes]]
id = "second"
repository = "example/duplicate"
branch = "main"
role = "production"
enabled = true
rollout_wave = 1
pages_url = "https://example.github.io/second/"
''',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="repositories must be unique"):
        load_registry(registry)


def test_fleet_workflows_are_parseable_and_secretless():
    status_source = (ROOT / ".github/workflows/fleet_status.yml").read_text()
    reusable_source = (
        ROOT / ".github/workflows/node_codebase_sync.yml"
    ).read_text()
    wrapper_source = (ROOT / "workflows/update_codebase.yml").read_text()
    assert yaml.safe_load(status_source) is not None
    assert yaml.safe_load(reusable_source) is not None
    assert yaml.safe_load(wrapper_source) is not None
    assert "workflow_call:" in reusable_source
    assert '[[ ! "$REVISION" =~ ^[0-9a-f]{40}$ ]]' in reusable_source
    assert "git add -- oswm_codebase\n" in reusable_source
    assert "uses: kauevestena/oswm_codebase/.github/workflows/node_codebase_sync.yml@main" in wrapper_source
    assert "contents: write" in wrapper_source
    assert "actions: write" in wrapper_source
    assert "create-github-app-token" not in reusable_source + wrapper_source
    assert "${{ secrets" not in reusable_source + wrapper_source
    assert "${{ secrets" not in status_source


def test_registry_toml_is_standard_library_parseable():
    data = tomllib.loads((ROOT / "fleet/registry.toml").read_text())
    assert data["schema_version"] == 1
