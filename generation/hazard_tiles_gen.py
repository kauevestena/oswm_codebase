"""Generate a single PMTiles archive for hazard analysis.

All four profiles are included as separate source-layers in one file so
the browser only needs a single ``pmtiles://`` source. Each profile layer
is named ``hazard_<profile>`` (e.g. ``hazard_pedestrian``).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from functions import *

from hazard_analysis.rules import HAZARD_PROFILES

# Check for ogr2ogr
docker_img = "ghcr.io/osgeo/gdal:alpine-normal-latest"
use_docker = shutil.which("docker") is not None
has_local_ogr2ogr = shutil.which("ogr2ogr") is not None

if not use_docker and not has_local_ogr2ogr:
    raise RuntimeError(
        "Neither Docker nor a local ogr2ogr installation found. "
        "Cannot generate hazard vector tiles."
    )

outpath = hazard_tiles_path
report = {}
has_errors = False

# Build a combined GeoJSON per profile, then merge into a single PMTiles.
# ogr2ogr can append layers with -append, so we create one layer per profile.

# First pass: verify all profile GeoJSONs exist
for profile_id in HAZARD_PROFILES:
    geojson_path = hazard_profile_features_path(profile_id)
    if not os.path.exists(geojson_path):
        msg = f"Missing {geojson_path} — run routing_demo_gen.py first"
        print(f"  ERROR: {msg}")
        report[profile_id] = {"status": "error", "reason": msg}
        has_errors = True

if has_errors:
    print("\n⚠ Cannot generate hazard tiles: missing input files.")
    sys.exit(1)

# Remove any existing output so we can build fresh
if os.path.exists(outpath):
    os.remove(outpath)

# Generate a VRT file to bundle all profiles into one ogr2ogr pass
vrt_path = os.path.join(hazard_analysis_folderpath, "hazard_layers.vrt")
with open(vrt_path, "w") as f:
    f.write("<OGRVRTDataSource>\n")
    for profile_id in HAZARD_PROFILES:
        layer_name = f"hazard_{profile_id}"
        geojson_name = f"features_{profile_id}.geojson"
        f.write(f'    <OGRVRTLayer name="{layer_name}">\n')
        f.write(f'        <SrcDataSource relativeToVRT="1">{geojson_name}</SrcDataSource>\n')
        f.write(f'        <SrcLayer>features_{profile_id}</SrcLayer>\n')
        f.write(f'    </OGRVRTLayer>\n')
    f.write("</OGRVRTDataSource>\n")

if use_docker:
    runstring = (
        f"docker run --rm -v ./data:/data {docker_img} "
        f"ogr2ogr -of PMTiles {outpath} {vrt_path} "
        f"-dsco MINZOOM={TILES_MIN_ZOOM} -dsco MAXZOOM={TILES_MAX_ZOOM} -progress"
    )
else:
    runstring = (
        f"ogr2ogr -of PMTiles {outpath} {vrt_path} "
        f"-dsco MINZOOM={TILES_MIN_ZOOM} -dsco MAXZOOM={TILES_MAX_ZOOM} -progress"
    )

print("Creating unified PMTiles layer from all profiles...")
result = subprocess.run(runstring, shell=True, capture_output=True, text=True)

if result.returncode != 0:
    msg = f"ogr2ogr failed (exit {result.returncode}): {result.stderr.strip()}"
    print(f"  ERROR: {msg}")
    report["_generation"] = {"status": "error", "reason": msg}
    has_errors = True
else:
    print("  OK: PMTiles generated successfully")
    report["_generation"] = {"status": "ok"}

# Final validation
if os.path.exists(outpath):
    filesize = os.path.getsize(outpath)
    if filesize < 1024:
        msg = f"output file is only {filesize} bytes — tiles may be empty or corrupt"
        print(f"  WARNING: {msg}")
        report["_output"] = {"status": "warning", "reason": msg, "filesize": filesize}
        has_errors = True
    else:
        print(f"\n✓ Hazard PMTiles generated: '{outpath}' ({filesize:,} bytes)")
        report["_output"] = {"status": "ok", "filesize": filesize}
else:
    msg = f"output file '{outpath}' was not created"
    print(f"  ERROR: {msg}")
    report["_output"] = {"status": "error", "reason": msg}
    has_errors = True

# Write report
report_path = os.path.join(hazard_analysis_folderpath, "tile_generation_report.json")
with open(report_path, "w") as f:
    json.dump(report, f, indent=2)
print(f"Tile generation report saved to {report_path}")

if has_errors:
    print("\n⚠ Hazard tile generation completed with errors/warnings!")
    sys.exit(1)
else:
    print("\n✓ All hazard tiles generated successfully.")
