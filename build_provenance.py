#!/usr/bin/env python3
"""Write machine-readable provenance for the complete published OSWM node build."""

from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

from time_utils import isoformat_utc

BUILD_CONTRACT = 1


def _core_revision(root: Path) -> str | None:
    override = os.environ.get("OSWM_CORE_REVISION")
    if override:
        return override.strip()
    result = subprocess.run(
        ["git", "-C", str(root / "oswm_codebase"), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _city_name(root: Path) -> str | None:
    config = root / "config.py"
    try:
        tree = ast.parse(config.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CITY_NAME":
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        return None
                    return str(value)
    return None


def _json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def write_manifest(root: Path, *, mode: str) -> dict[str, object]:
    basemap = _json(root / "data/basemaps/generation_report.json")
    payload: dict[str, object] = {
        "schema_version": 1,
        "build_contract": BUILD_CONTRACT,
        "node": _city_name(root),
        "generated_at": isoformat_utc(),
        "mode": mode,
        "core": {
            "repository": "kauevestena/oswm_codebase",
            "sha": _core_revision(root),
        },
        "runtime": _json(root / "oswm_runtime/runtime_manifest.json"),
        "products": {
            "webmap": (root / "map.html").is_file() and (root / "webmap_params.json").is_file(),
            "vector_tiles": (root / "data/tiles/tile_generation_report.json").is_file(),
            "routing": (root / "data/routing/metadata.json").is_file(),
            "hazards": (root / "data/hazard_analysis/metadata.json").is_file(),
            "basemaps": {
                "available": bool(basemap),
                "renderer_version": basemap.get("renderer_version"),
                "style_basis": basemap.get("style_basis")
                    or (basemap.get("source", {}) if isinstance(basemap.get("source"), dict) else {}).get("style_basis"),
            },
        },
    }
    (root / "oswm-build.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--mode", default="daily")
    args = parser.parse_args()
    print(json.dumps(write_manifest(args.root.resolve(), mode=args.mode), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
