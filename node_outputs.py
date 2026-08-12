#!/usr/bin/env python3
"""Canonical OSWM generated-output reset, validation, and staging contract."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


INITIALIZATION_RESET_PATHS = (
    "data",
    "metadata",
    "hub",
    "quality_check",
    "statistics",
    "statistics_specs",
    "map.html",
    "webmap_params.json",
    "global_params.json",
    "run_log.txt",
    "run_log_full.txt",
)

DERIVED_RESET_PATHS = (
    "data/processed",
    "data/tiles",
    "data/data_quality",
    "data/routing",
    "data/hazard_analysis",
    "data/snapshots",
    "data/vrts",
    "metadata",
    "hub",
    "quality_check",
    "statistics",
    "statistics_specs",
    "map.html",
    "webmap_params.json",
    "global_params.json",
)

PRESERVED_DURING_DERIVED_RESET = ("quality_check/keys_without_wiki.json",)

REQUIRED_DATA_OUTPUTS = (
    "data/index.json",
    "data/boundaries/infos.json",
    "data/boundaries/polygon.geojson",
    "data/boundaries/polygon.parquet",
    "data/raw/sidewalks.parquet",
    "data/raw/crossings.parquet",
    "data/raw/kerbs.parquet",
    "data/raw/other_footways.parquet",
    "data/processed/sidewalks.parquet",
    "data/processed/crossings.parquet",
    "data/processed/kerbs.parquet",
    "data/processed/other_footways.parquet",
    "data/tiles/sidewalks.pmtiles",
    "data/tiles/crossings.pmtiles",
    "data/tiles/kerbs.pmtiles",
    "data/tiles/tile_generation_report.json",
    "data/routing/profiles.json",
    "data/routing/metadata.json",
    "data/hazard_analysis/profiles.json",
    "data/hazard_analysis/metadata.json",
    "data/hazard_analysis/hazard.pmtiles",
    "data/snapshots/node_summary.json",
    "data/updates/index.html",
    "metadata/index.json",
    "statistics_specs/index.json",
    "global_params.json",
)

REQUIRED_QUALITY_OUTPUTS = (
    "quality_check/index.json",
    "quality_check/index.html",
    "quality_check/oswm_qc_main.html",
    "quality_check/oswm_qc_external.html",
    "quality_check/map.html",
    "quality_check/completeness/index.html",
    "quality_check/completeness/data.json",
)

REQUIRED_PUBLIC_PAGES = (
    "index.html",
    "map.html",
    "statistics/index.html",
    "hub/index.html",
    "hub/API/index.html",
    "hub/acquisition/index.html",
    "hub/watcher/index.html",
)

REQUIRED_HUB_OUTPUTS = (
    "hub/acquisition/results.json",
    "hub/watcher/feed.xml",
    "hub/watcher/changesets.xml",
)

# Canonical post-generation manifest used by runners, decisions, audits, and tests.
REQUIRED_OUTPUTS = (
    *REQUIRED_DATA_OUTPUTS,
    *REQUIRED_QUALITY_OUTPUTS,
    *REQUIRED_PUBLIC_PAGES,
    *REQUIRED_HUB_OUTPUTS,
    "webmap_params.json",
)

STAGE_PROFILES = {
    "setup": (
        ".github/workflows",
        ".oswm-managed-files.json",
        "README.md",
        "index.html",
        "metadata",
        "hub",
    ),
    "daily": (
        "data",
        "metadata",
        "hub",
        "quality_check",
        "statistics",
        "statistics_specs",
        "README.md",
        "index.html",
        "map.html",
        "webmap_params.json",
        "global_params.json",
    ),
    "weekly": (
        "data/updates",
        "metadata",
        "hub",
        "quality_check/keys_without_wiki.json",
        "index.html",
    ),
    "special": (".github/workflows", ".oswm-managed-files.json"),
    "custom": (
        "data",
        "metadata",
        "hub",
        "quality_check",
        "statistics",
        "statistics_specs",
        "README.md",
        "index.html",
        "map.html",
        "webmap_params.json",
        "global_params.json",
    ),
}


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def validate_node_root(root: Path) -> None:
    if root == Path(root.anchor):
        raise RuntimeError("Refusing to operate on a filesystem root")
    missing = [
        str(path)
        for path in (root / "config.py", root / "oswm_codebase")
        if not path.exists()
    ]
    if missing:
        raise RuntimeError(
            "Refusing to reset a directory that is not an OSWM node: "
            + ", ".join(missing)
        )


def reset_initialization(root: Path, *, apply: bool) -> dict[str, object]:
    """Remove all generated template state; dry-run unless *apply* is true."""

    validate_node_root(root)
    targets = [root / relative for relative in INITIALIZATION_RESET_PATHS]
    existing = [path for path in targets if path.exists() or path.is_symlink()]
    if apply:
        for path in existing:
            _remove(path)
        registry = root / "data/updates/registry.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text("{}\n", encoding="utf-8")
    return {
        "mode": "apply" if apply else "dry-run",
        "paths": [str(path.relative_to(root)) for path in existing],
    }


def reset_derived(root: Path) -> list[str]:
    """Remove derived state before a complete regeneration."""

    validate_node_root(root)
    preserved: dict[str, bytes] = {}
    for relative in PRESERVED_DURING_DERIVED_RESET:
        path = root / relative
        if path.is_file():
            preserved[relative] = path.read_bytes()
    removed: list[str] = []
    for relative in DERIVED_RESET_PATHS:
        path = root / relative
        if path.exists() or path.is_symlink():
            _remove(path)
            removed.append(relative)
    for relative, content in preserved.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return removed


def required_outputs(root: Path) -> tuple[str, ...]:
    """Return the fixed manifest plus chart pages declared by generated specs."""
    outputs = list(REQUIRED_OUTPUTS)
    specs_root = root / "statistics_specs"
    if specs_root.is_dir():
        for spec in sorted(specs_root.rglob("*.json")):
            if spec.name == "index.json":
                continue
            chart = Path("statistics") / spec.relative_to(specs_root).with_suffix(".html")
            relative = chart.as_posix()
            if relative not in outputs:
                outputs.append(relative)
    return tuple(outputs)


def missing_required(root: Path) -> list[str]:
    return [
        relative
        for relative in required_outputs(root)
        if not (root / relative).is_file() or (root / relative).stat().st_size == 0
    ]


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=check
    )


def stage_profile(root: Path, profile: str) -> list[str]:
    """Stage only existing or already tracked paths declared by *profile*."""

    if profile not in STAGE_PROFILES:
        raise ValueError(f"Unknown stage profile: {profile}")
    selected: list[str] = []
    for relative in STAGE_PROFILES[profile]:
        tracked = _git(root, "ls-files", "--", relative, check=False).stdout.strip()
        if (root / relative).exists() or tracked:
            selected.append(relative)
    if selected:
        _git(root, "add", "--", *selected)
    return selected


def oversized_staged_files(root: Path, max_mib: float) -> list[dict[str, object]]:
    limit = int(max_mib * 1024 * 1024)
    result = _git(
        root,
        "diff",
        "--cached",
        "--name-only",
        "--diff-filter=ACMR",
        "-z",
    ).stdout
    oversized: list[dict[str, object]] = []
    for relative in (item for item in result.split("\0") if item):
        path = root / relative
        if path.is_file() and path.stat().st_size >= limit:
            oversized.append({"path": relative, "bytes": path.stat().st_size})
    return oversized


def _root(value: str) -> Path:
    return Path(value).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", type=_root)
    subparsers = parser.add_subparsers(dest="command", required=True)
    reset_node = subparsers.add_parser("reset-node")
    reset_node.add_argument("--apply", action="store_true")
    subparsers.add_parser("reset-derived")
    subparsers.add_parser("manifest")
    subparsers.add_parser("require")
    stage = subparsers.add_parser("stage")
    stage.add_argument("profile", choices=sorted(STAGE_PROFILES))
    sizes = subparsers.add_parser("validate-sizes")
    sizes.add_argument("--max-mib", type=float, default=95)
    args = parser.parse_args(argv)

    if args.command == "reset-node":
        print(json.dumps(reset_initialization(args.root, apply=args.apply), indent=2))
    elif args.command == "reset-derived":
        print(json.dumps({"removed": reset_derived(args.root)}, indent=2))
    elif args.command == "manifest":
        print(json.dumps({"required_outputs": list(required_outputs(args.root))}, indent=2))
    elif args.command == "require":
        missing = missing_required(args.root)
        print(
            json.dumps(
                {
                    "required_outputs": list(required_outputs(args.root)),
                    "missing": missing,
                },
                indent=2,
            )
        )
        return 1 if missing else 0
    elif args.command == "stage":
        print(json.dumps({"staged_paths": stage_profile(args.root, args.profile)}, indent=2))
    elif args.command == "validate-sizes":
        oversized = oversized_staged_files(args.root, args.max_mib)
        print(json.dumps({"limit_mib": args.max_mib, "oversized": oversized}, indent=2))
        return 1 if oversized else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
