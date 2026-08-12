#!/usr/bin/env python3
"""Machine-readable daily pipeline decisions for cold, rebuild, and no-op runs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from node_outputs import missing_required
from time_utils import isoformat_utc


RAW_OUTPUTS = (
    "data/raw/sidewalks.parquet",
    "data/raw/crossings.parquet",
    "data/raw/kerbs.parquet",
    "data/raw/other_footways.parquet",
    "data/boundaries/polygon.geojson",
)
CODEBASE_REVISION_KEY = "OSWM Codebase Revision"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def current_codebase_revision(root: Path) -> str | None:
    override = os.environ.get("OSWM_CODEBASE_REVISION")
    if override:
        return override
    result = subprocess.run(
        ["git", "-C", str(root / "oswm_codebase"), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def decide(root: Path, *, watcher_status: int, force: bool = False) -> dict[str, Any]:
    registry_path = root / "data/updates/registry.json"
    registry = _load_json(registry_path)
    current_revision = current_codebase_revision(root)
    recorded_revision = registry.get(CODEBASE_REVISION_KEY)
    raw_missing = [item for item in RAW_OUTPUTS if not (root / item).is_file()]
    required_missing = missing_required(root)

    if force:
        mode, reason = "generate", "forced"
    elif raw_missing:
        mode, reason = "generate", "cold_start"
    elif current_revision and current_revision != recorded_revision:
        mode, reason = "rebuild", "codebase_revision_changed"
    elif required_missing:
        mode, reason = "rebuild", "derived_outputs_missing"
    elif watcher_status == 0:
        mode, reason = "skip", "no_osm_changes"
    else:
        mode, reason = "generate", "osm_changes_or_inconclusive_check"

    return {
        "schema_version": 1,
        "checked_at": isoformat_utc(),
        "mode": mode,
        "reason": reason,
        "watcher_status": watcher_status,
        "force": force,
        "current_codebase_revision": current_revision,
        "recorded_codebase_revision": recorded_revision,
        "missing_raw": raw_missing,
        "missing_required": required_missing,
    }


def record_success(root: Path) -> None:
    registry_path = root / "data/updates/registry.json"
    registry = _load_json(registry_path)
    revision = current_codebase_revision(root)
    if revision:
        registry[CODEBASE_REVISION_KEY] = revision
    registry["Pipeline Success"] = isoformat_utc()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(registry, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    subparsers = parser.add_subparsers(dest="command", required=True)
    decision = subparsers.add_parser("decide")
    decision.add_argument("--watcher-status", type=int, required=True)
    decision.add_argument("--force", action="store_true")
    decision.add_argument("--output", type=Path)
    subparsers.add_parser("record-success")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.command == "record-success":
        record_success(root)
        return 0
    payload = decide(root, watcher_status=args.watcher_status, force=args.force)
    rendered = json.dumps(payload, indent=2) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
