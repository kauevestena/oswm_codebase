"""Generate the lightweight PMTiles layer used to draw the routing network."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import constants


DOCKER_IMAGE = "ghcr.io/osgeo/gdal:alpine-normal-latest"
DISPLAY_LAYER = "routing"


def _ogr_command(source_path: Path, output_path: Path) -> list[str]:
    options = [
        "ogr2ogr",
        "-of",
        "PMTiles",
        str(output_path),
        str(source_path),
        "-nln",
        DISPLAY_LAYER,
        "-select",
        "edge_kind",
        "-dsco",
        f"MINZOOM={constants.TILES_MIN_ZOOM}",
        "-dsco",
        f"MAXZOOM={constants.TILES_MAX_ZOOM}",
        "-progress",
    ]
    if shutil.which("ogr2ogr"):
        return options
    if not shutil.which("docker"):
        raise RuntimeError(
            "Neither Docker nor a local ogr2ogr installation was found. "
            "Cannot generate routing vector tiles."
        )

    data_root = Path(constants.data_folderpath).resolve()
    source_in_container = Path("/data") / source_path.resolve().relative_to(data_root)
    output_in_container = Path("/data") / output_path.resolve().relative_to(data_root)
    options[3] = str(output_in_container)
    options[4] = str(source_in_container)
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{data_root}:/data",
        DOCKER_IMAGE,
        *options,
    ]


def main() -> None:
    source_path = Path(constants.routing_parquet_path)
    output_path = Path(constants.routing_tiles_path)
    report_path = Path(constants.routing_tiles_report_path)
    temporary_path = output_path.with_name(
        f".{output_path.stem}.tmp.{os.getpid()}{output_path.suffix}"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.is_file():
        raise FileNotFoundError(
            f"Missing {source_path}; run routing_demo_gen.py first"
        )

    report: dict[str, object] = {}
    try:
        with Path(constants.routing_metadata_path).open(encoding="utf-8") as source:
            feature_count = int(json.load(source)["feature_count"])
        if temporary_path.exists():
            temporary_path.unlink()
        result = subprocess.run(
            _ogr_command(source_path, temporary_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ogr2ogr failed with exit {result.returncode}: "
                f"{result.stderr.strip()}"
            )
        if not temporary_path.is_file() or temporary_path.stat().st_size < 1024:
            size = temporary_path.stat().st_size if temporary_path.exists() else 0
            raise RuntimeError(
                f"routing PMTiles output is missing or too small ({size} bytes)"
            )
        os.replace(temporary_path, output_path)
        report = {
            "status": "ok",
            "source": source_path.name,
            "source_layer": DISPLAY_LAYER,
            "input_features": feature_count,
            "filesize": output_path.stat().st_size,
        }
        print(
            f"Generated {output_path} from {feature_count:,} features "
            f"({output_path.stat().st_size:,} bytes)."
        )
    except Exception as error:
        report = {"status": "error", "reason": str(error)}
        raise
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
        report_path.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
