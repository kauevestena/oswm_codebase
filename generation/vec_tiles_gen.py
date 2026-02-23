import sys
sys.path.append('oswm_codebase')
from functions import *
import subprocess
import shutil
import geopandas as gpd

docker_img = 'ghcr.io/osgeo/gdal:alpine-normal-latest'

create_folder_if_not_exists(tiles_folderpath)

layers_dict = paths_dict['map_layers'].copy()

# MAYBE: generate boundaries also as vectiles?
# layers_dict['boundaries'] = boundaries_geojson_path

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
            print(f"  WARNING: {input_path} has no features — skipping tile generation for '{layername}'")
            continue
        gdf.to_file(geojson_intermediate, driver='GeoJSON')
        ogr_input = geojson_intermediate
        print(f"  Converted {len(gdf)} features")
    else:
        ogr_input = input_path

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
        print(f"  ERROR generating tiles for '{layername}':")
        print(f"  stderr: {result.stderr}")
        print(f"  stdout: {result.stdout}")
    else:
        # Validate the output file
        if os.path.exists(outpath):
            filesize = os.path.getsize(outpath)
            if filesize < 1024:
                print(f"  WARNING: output file '{outpath}' is only {filesize} bytes — tiles may be empty")
            else:
                print(f"  OK: '{outpath}' generated ({filesize:,} bytes)")
        else:
            print(f"  ERROR: output file '{outpath}' was not created")

    # Clean up intermediate GeoJSON
    if geojson_intermediate and os.path.exists(geojson_intermediate):
        os.remove(geojson_intermediate)

# cleaning up any erroneously created mbtiles:
for filename in [f for f in os.listdir(tiles_folderpath) if f.endswith('.mbtiles')]:
    os.remove(os.path.join(tiles_folderpath, filename))

