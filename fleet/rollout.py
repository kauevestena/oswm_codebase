"""Dispatch one exact tested core revision to registered OSWM nodes."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from fleet.github import GitHubClient, GitHubError
from fleet.registry import load_registry


SHA = re.compile(r"^[0-9a-f]{40}$")


def rollout(
    registry_path: str | Path,
    client: GitHubClient,
    *,
    owner: str,
    revision: str,
    wave: int | None = None,
    dry_run: bool = False,
    wait_seconds: int = 0,
    poll_seconds: int = 10,
) -> list[dict[str, Any]]:
    registry = load_registry(registry_path)
    revision = revision.strip().lower()
    if not SHA.fullmatch(revision):
        raise ValueError("revision must be a full 40-character SHA")
    nodes = sorted(
        (
            node
            for node in registry.nodes
            if node.enabled
            and node.owner.lower() == owner.lower()
            and (wave is None or node.rollout_wave == wave)
        ),
        key=lambda node: (node.rollout_wave, node.id),
    )
    if not nodes:
        scope = f"owner {owner}" if wave is None else f"owner {owner} in wave {wave}"
        raise ValueError(f"no enabled fleet nodes are registered for {scope}")
    if wait_seconds < 0 or poll_seconds <= 0:
        raise ValueError("wait_seconds must be nonnegative and poll_seconds must be positive")

    results: list[dict[str, Any]] = []
    for node in nodes:
        record: dict[str, Any] = {
            "node": node.id,
            "repository": node.repository,
            "branch": node.branch,
            "revision": revision,
            "rollout_wave": node.rollout_wave,
            "status": "planned" if dry_run else "dispatched",
        }
        if not dry_run:
            try:
                client.dispatch_workflow(
                    node.repository,
                    "update_codebase.yml",
                    node.branch,
                    {"revision": revision},
                )
            except GitHubError as error:
                record["status"] = "failed"
                record["error"] = str(error)
        results.append(record)

    pending = {
        result["repository"]: result
        for result in results
        if result["status"] == "dispatched" and wait_seconds
    }
    if pending:
        deadline = time.monotonic() + wait_seconds
        while pending:
            for repository, record in list(pending.items()):
                try:
                    observed = client.get_submodule_sha(
                        repository, "oswm_codebase", str(record["branch"])
                    )
                    record["observed_revision"] = observed
                    record.pop("observation_error", None)
                    if observed == revision:
                        record["status"] = "deployed"
                        del pending[repository]
                except GitHubError as error:
                    record["observation_error"] = str(error)
            if not pending:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                for record in pending.values():
                    record["status"] = "failed"
                    record["error"] = (
                        f"node did not pin {revision} within {wait_seconds} seconds"
                    )
                break
            time.sleep(min(poll_seconds, remaining))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="fleet/registry.toml")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--wave", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args(argv)

    token = os.environ.get("GH_TOKEN")
    if not args.dry_run and not token:
        parser.error("GH_TOKEN must contain a GitHub App installation token")
    registry = load_registry(args.registry)
    client = GitHubClient(
        token=token,
        api_timeout_seconds=registry.policy.api_timeout_seconds,
        page_timeout_seconds=registry.policy.page_timeout_seconds,
    )
    results = rollout(
        args.registry,
        client,
        owner=args.owner,
        revision=args.revision,
        wave=args.wave,
        dry_run=args.dry_run,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
    )
    print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return 1 if any(result["status"] == "failed" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
