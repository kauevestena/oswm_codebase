import sys
sys.path.append('oswm_codebase')
from functions import *
import subprocess

docker_img = 'ghcr.io/osgeo/gdal:alpine-normal-latest'

create_folder_if_not_exists(tiles_folderpath)


print(paths_dict)

layers_dict = paths_dict['map_layers']

for layername in layers_dict:

    outpath = os.path.join(tiles_folderpath,layername+'.pmtiles')

    runstring = f'docker run --rm -v ./data:/data {docker_img} ogr2ogr -f PMTiles {outpath} {layers_dict[layername]} -dsco MINZOOM={TILES_MIN_ZOOM} -dsco MAXZOOM={TILES_MAX_ZOOM} -progress'

    subprocess.run(runstring,shell=True)

