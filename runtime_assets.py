#!/usr/bin/env python3
"""Publish the immutable runtime files required by generated OSWM node pages."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

RUNTIME_DIR = "oswm_runtime"
RUNTIME_CONTRACT = 1
COPY_TREES = (
    ("assets", "assets"),
    ("routing", "routing"),
    ("hazard_analysis", "hazard_analysis"),
)
SNAPSHOT_FILES = (
    "snapshot_charts.js",
    "snapshot_composer.js",
    "snapshot_control.js",
    "snapshot_i18n.js",
    "snapshot_qrcode.js",
    "snapshot_stats.js",
)


def publish_runtime(node_root: Path, core_root: Path) -> dict[str, object]:
    target = node_root / RUNTIME_DIR
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    copied: list[str] = []
    for source_rel, dest_rel in COPY_TREES:
        source = core_root / source_rel
        destination = target / dest_rel
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        copied.append(dest_rel)

    snapshot_target = target / "webmap" / "snapshot"
    snapshot_target.mkdir(parents=True, exist_ok=True)
    for name in SNAPSHOT_FILES:
        shutil.copy2(core_root / "webmap" / "snapshot" / name, snapshot_target / name)
    copied.append("webmap/snapshot")

    shutil.copy2(core_root / "webmap/oswm_legend_control.js", target / "webmap/oswm_legend_control.js")
    copied.append("webmap/oswm_legend_control.js")
    charts_target = target / "webmap/theme_charts"
    charts_target.mkdir()
    for source in sorted((core_root / "webmap/theme_charts").glob("*.js")):
        shutil.copy2(source, charts_target / source.name)
    copied.append("webmap/theme_charts")

    manifest = {
        "schema_version": 1,
        "runtime_contract": RUNTIME_CONTRACT,
        "source": "kauevestena/oswm_codebase",
        "paths": copied,
    }
    (target / "runtime_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    core_root = Path(__file__).resolve().parent
    node_root = Path.cwd().resolve()
    print(json.dumps(publish_runtime(node_root, core_root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
