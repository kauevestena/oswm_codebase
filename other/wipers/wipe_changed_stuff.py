#!/usr/bin/env python3
"""Remove legacy node outputs that predate the current directory layout."""

from __future__ import annotations

import shutil
from pathlib import Path


def wipe_changed_stuff(root: Path) -> None:
    """Remove top-level GeoJSON leftovers and migrate versioning records."""

    data = root / "data"
    if not data.is_dir():
        return

    for path in data.iterdir():
        if path.is_file() and path.suffix == ".geojson":
            path.unlink()

    versioning = data / "updates" / "versioning"
    versioning.mkdir(parents=True, exist_ok=True)
    for path in data.glob("*_versioning.json"):
        shutil.move(str(path), versioning / path.name)


if __name__ == "__main__":
    wipe_changed_stuff(Path.cwd())
