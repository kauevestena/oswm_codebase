#!/usr/bin/env python3
"""Synchronize only core-managed node files, preserving node customizations."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


STATE_FILE = ".oswm-managed-files.json"
CRON_TOKENS = {
    "__OSWM_DAILY_CRON__": ("NODE_DAILY_CRON", "30 7 * * *"),
    "__OSWM_WEEKLY_CRON__": ("NODE_WEEKLY_CRON", "5 8 * * 0"),
}
CRON_FIELD = re.compile(r"^[A-Za-z0-9*/?,#LW-]+$")


def literal_config(path: Path) -> dict[str, Any]:
    """Read literal top-level assignments without executing node code."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                values[target.id] = ast.literal_eval(node.value)
            except (TypeError, ValueError):
                continue
    return values


def validate_cron(value: object, setting: str) -> str:
    cron = str(value).strip()
    fields = cron.split()
    if len(fields) != 5 or any(not CRON_FIELD.fullmatch(field) for field in fields):
        raise ValueError(f"{setting} must be a safe five-field cron expression")
    return " ".join(fields)


def codebase_sync_cron(config: dict[str, Any]) -> str:
    """Return an explicit sync cron or derive daily minus two hours."""

    explicit = config.get("NODE_CODEBASE_SYNC_CRON")
    if explicit is not None:
        return validate_cron(explicit, "NODE_CODEBASE_SYNC_CRON")

    daily = validate_cron(
        config.get("NODE_DAILY_CRON", "30 7 * * *"), "NODE_DAILY_CRON"
    )
    minute, hour, day, month, weekday = daily.split()
    if not minute.isdigit() or not hour.isdigit() or (day, month, weekday) != (
        "*",
        "*",
        "*",
    ):
        raise ValueError(
            "NODE_DAILY_CRON must be a fixed daily UTC time to derive the "
            "codebase synchronization schedule; set NODE_CODEBASE_SYNC_CRON "
            "explicitly for another cron shape"
        )
    if not 0 <= int(minute) <= 59 or not 0 <= int(hour) <= 23:
        raise ValueError("NODE_DAILY_CRON contains an invalid UTC time")
    return f"{int(minute)} {(int(hour) - 2) % 24} * * *"


def render_managed_file(source: str, config: dict[str, Any]) -> str:
    rendered = source
    for token, (setting, default) in CRON_TOKENS.items():
        if token in rendered:
            rendered = rendered.replace(
                token, validate_cron(config.get(setting, default), setting)
            )
    if "__OSWM_CODEBASE_SYNC_CRON__" in rendered:
        rendered = rendered.replace(
            "__OSWM_CODEBASE_SYNC_CRON__", codebase_sync_cron(config)
        )
    return rendered


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _revision(codebase_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=codebase_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def synchronize(node_root: Path, codebase_root: Path) -> dict[str, Any]:
    manifest_path = codebase_root / "workflows/manifest.json"
    manifest = _load_json(manifest_path, None)
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Invalid managed workflow manifest: {manifest_path}")
    managed = manifest.get("managed", [])
    retired = manifest.get("retired", [])
    if not all(isinstance(item, str) for item in (*managed, *retired)):
        raise RuntimeError("Managed workflow paths must be strings")

    config = literal_config(node_root / "config.py")
    state_path = node_root / STATE_FILE
    previous = _load_json(state_path, {})
    previous_files = previous.get("managed_files", []) if isinstance(previous, dict) else []

    written: list[str] = []
    for relative in managed:
        source_path = codebase_root / relative
        if not source_path.is_file():
            raise FileNotFoundError(f"Managed source is missing: {source_path}")
        content = render_managed_file(source_path.read_text(encoding="utf-8"), config)
        destination = node_root / ".github/workflows" / Path(relative).name
        _write_text_atomic(destination, content)
        written.append(str(destination.relative_to(node_root)))

    current_destinations = set(written)
    removable = {
        str(Path(".github/workflows") / Path(item).name)
        for item in retired
    }
    removable.update(
        item for item in previous_files if isinstance(item, str)
    )
    removed: list[str] = []
    for relative in sorted(removable - current_destinations):
        path = node_root / relative
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed.append(relative)

    state = {
        "schema_version": 1,
        "source_revision": _revision(codebase_root),
        "managed_files": sorted(written),
    }
    _write_text_atomic(state_path, json.dumps(state, indent=2) + "\n")
    return {"written": sorted(written), "removed": removed, "state": state}


def main() -> int:
    node_root = Path.cwd().resolve()
    codebase_root = Path(__file__).resolve().parent
    report = synchronize(node_root, codebase_root)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
