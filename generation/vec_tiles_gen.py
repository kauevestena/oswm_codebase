import sys
sys.path.append('oswm_codebase')
from functions import *
import subprocess

docker_img = 'ghcr.io/osgeo/gdal:alpine-normal-latest'

create_folder_if_not_exists(tiles_folderpath)

layers_dict = paths_dict['map_layers'].copy()

# MAYBE: generate boundaries also as vectiles?
# layers_dict['boundaries'] = boundaries_geojson_path

for layername in layers_dict:

    outpath = os.path.join(tiles_folderpath,layername+'.pmtiles')

    runstring = f'docker run --rm -v ./data:/data {docker_img} ogr2ogr -skipfailures -of PMTiles {outpath} {layers_dict[layername]} -dsco MINZOOM={TILES_MIN_ZOOM} -dsco MAXZOOM={TILES_MAX_ZOOM} -progress'

    subprocess.run(runstring,shell=True)

# cleaning up any errouneously created mbtiles:
for filename in [f for f in os.listdir(tiles_folderpath) if f.endswith('.mbtiles')]:
    os.remove(os.path.join(tiles_folderpath, filename))

