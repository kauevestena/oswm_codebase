from functions import *
import argparse

# create a --development flag:
parser = argparse.ArgumentParser()
parser.add_argument('--development', action='store_true')
args = parser.parse_args()

in_dev = args.development

# first, reading the parameters
params = read_json(webmap_params_original_path)

# then override: (TODO)

# # generating the "sources" and layernames:
params['sources'] = {}
for layername in paths_dict['map_layers']:
    params[f'{layername}_url'] = f'{node_homepage_url}data/tiles/{layername}.pmtiles'
    
    params['sources'][f'oswm_pmtiles_{layername}'] = {
        "type": "vector",
        "url": f"pmtiles://{params[f'{layername}_url']}",
        "promoteId":"id",
        "attribution": '© <a href="https://openstreetmap.org">OpenStreetMap Contributors</a>'}
    
params['boundaries_url'] = f'{node_homepage_url}data/boundaries.geojson'


# basemap:
params['sources']['osm'] = {
    "type": "raster",
    "tiles": [BASEMAP_URL],
}

# boundaries:
params['sources']['boundaries'] = {
    "type": "geojson",
    "data": params['boundaries_url']
}

# # # terrain:
# # params['sources']['terrain'] = {
# #     "type": "raster-dem",
# #     "url": "https://demotiles.maplibre.org/terrain-tiles/tiles.json",
# #     "tileSize": 256
# # }

# reading the base html
webmap_html = file_as_string(webmap_base_path)

# doing other stuff like insertions and nasty things (TODO):

# finally generate the files:
str_to_file(webmap_html,webmap_path)
dump_json(params,webmap_params_path)

# if we are in dev mode, also dump the original params:
if in_dev:
    dump_json(params,webmap_params_original_path)