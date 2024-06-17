from webmap_lib import *
import argparse

# create a --development flag:
parser = argparse.ArgumentParser()
parser.add_argument('--development', action='store_true')
args = parser.parse_args()

in_dev = args.development

# first, reading the parameters
params = read_json(webmap_params_original_path)

# then override: (TODO)
params['data_layers'] = MAP_DATA_LAYERS

# # generating the "sources" and layernames:
params.update(get_sources(only_urls=True))
sources = get_sources()['sources']

# very temporary:
params['sources'] = sources


# reading the base html
webmap_html = file_as_string(webmap_base_path)

# doing other stuff like insertions and nasty things (TODO):

# finally generate the files:
str_to_file(webmap_html,webmap_path)
dump_json(params,webmap_params_path)

# if we are in dev mode, also dump the original params:
if in_dev:
    dump_json(params,webmap_params_original_path)