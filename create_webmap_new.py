from functions import *

# first reading parameters
params = read_json(webmap_params_original_path)

# # then override: (TODO)
# layernames: 
for layername in paths_dict['map_layers']:
    params[f'{layername}_url'] = f'/{REPO_NAME}/data/tiles/{layername}.pmtiles'

# reading the base html
webmap_html = file_as_string(webmap_base_path)

# doing other stuff like insertions and nasty stuff (TODO):

# finally generate the files:
str_to_file(webmap_html,webmap_path)
dump_json(params,webmap_params_path)