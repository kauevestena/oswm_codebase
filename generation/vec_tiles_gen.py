import sys
sys.path.append('oswm_codebase')
from functions import *
import subprocess
import shutil
import geopandas as gpd
import json

docker_img = 'ghcr.io/osgeo/gdal:alpine-normal-latest'

create_folder_if_not_exists(tiles_folderpath)

layers_dict = paths_dict['map_layers'].copy()

# MAYBE: generate boundaries also as vectiles?
# layers_dict['boundaries'] = boundaries_geojson_path

# Track results for validation report
tile_report = {}
has_errors = False

# Check if Docker is available
use_docker = shutil.which('docker') is not None

# Check if ogr2ogr is available locally
has_local_ogr2ogr = shutil.which('ogr2ogr') is not None

if not use_docker and not has_local_ogr2ogr:
    raise RuntimeError("Neither Docker nor a local ogr2ogr installation found. Cannot generate vector tiles.")


for layername in layers_dict:

    input_path = layers_dict[layername]
    outpath = os.path.join(tiles_folderpath, layername + '.pmtiles')
    geojson_intermediate = None

    # Convert Parquet to GeoJSON as an intermediate step to avoid
    # GDAL Parquet driver issues that produce corrupted tiles
    if input_path.endswith('.parquet'):
        geojson_intermediate = input_path.replace('.parquet', '_tiles_tmp.geojson')
        print(f"[{layername}] Converting Parquet to intermediate GeoJSON...")
        gdf = gpd.read_parquet(input_path)
        if gdf.empty:
            msg = f"{input_path} has no features — skipping tile generation"
            print(f"  WARNING: {msg}")
            tile_report[layername] = {"status": "skipped", "reason": msg}
            has_errors = True
            continue
        gdf.to_file(geojson_intermediate, driver='GeoJSON')
        ogr_input = geojson_intermediate
        input_features = len(gdf)
        print(f"  Converted {input_features} features")
    else:
        ogr_input = input_path
        input_features = None

    # Build ogr2ogr command
    if use_docker:
        runstring = (
            f'docker run --rm -v ./data:/data {docker_img} '
            f'ogr2ogr -of PMTiles {outpath} {ogr_input} '
            f'-nln {layername} '
            f'-dsco MINZOOM={TILES_MIN_ZOOM} -dsco MAXZOOM={TILES_MAX_ZOOM} -progress'
        )
    else:
        runstring = (
            f'ogr2ogr -of PMTiles {outpath} {ogr_input} '
            f'-nln {layername} '
            f'-dsco MINZOOM={TILES_MIN_ZOOM} -dsco MAXZOOM={TILES_MAX_ZOOM} -progress'
        )

    print(f"[{layername}] Generating PMTiles...")
    result = subprocess.run(runstring, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        msg = f"ogr2ogr failed (exit {result.returncode}): {result.stderr.strip()}"
        print(f"  ERROR generating tiles for '{layername}':")
        print(f"  stderr: {result.stderr}")
        print(f"  stdout: {result.stdout}")
        tile_report[layername] = {"status": "error", "reason": msg}
        has_errors = True
    elif os.path.exists(outpath):
        filesize = os.path.getsize(outpath)
        if filesize < 1024:
            msg = f"output file is only {filesize} bytes — tiles may be empty or corrupt"
            print(f"  WARNING: {msg}")
            tile_report[layername] = {"status": "warning", "reason": msg, "filesize": filesize}
            has_errors = True
        else:
            print(f"  OK: '{outpath}' generated ({filesize:,} bytes)")
            tile_report[layername] = {"status": "ok", "filesize": filesize, "input_features": input_features}
    else:
        msg = f"output file '{outpath}' was not created"
        print(f"  ERROR: {msg}")
        tile_report[layername] = {"status": "error", "reason": msg}
        has_errors = True

    # Clean up intermediate GeoJSON
    if geojson_intermediate and os.path.exists(geojson_intermediate):
        os.remove(geojson_intermediate)

# cleaning up any erroneously created mbtiles:
for filename in [f for f in os.listdir(tiles_folderpath) if f.endswith('.mbtiles')]:
    os.remove(os.path.join(tiles_folderpath, filename))

# Write tile generation report for downstream validation
report_path = os.path.join(tiles_folderpath, 'tile_generation_report.json')
with open(report_path, 'w') as f:
    json.dump(tile_report, f, indent=2)
print(f"\nTile generation report saved to {report_path}")

if has_errors:
    print("\n\u26a0 Tile generation completed with errors/warnings!")
    sys.exit(1)
else:
    print("\n\u2713 All tiles generated successfully.")

