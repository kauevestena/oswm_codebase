from webmap_lib import *
import argparse

# create a --development flag:
parser = argparse.ArgumentParser()
parser.add_argument('--development', action='store_true')
args = parser.parse_args()

in_dev = args.development

# first, reading the parameters
params = read_json(webmap_params_original_path)

# then override and fill in with the stuff:
params['data_layers'] = MAP_DATA_LAYERS

# the layers that by type:
params['layer_types'] = layer_type_groups

# # generating the "sources" and layernames:
params.update(get_sources(only_urls=True))


# very temporary:
# params['sources'] = MAP_SOURCES

# getting colors
interest_attributes = {
    # key is raw attribute name, value is label (human readable)
    "surface" : "Surface",
    "smoothness" : "Smoothness",
}

params['styles'] = {
    "footway_categories" : create_base_style()
}

for attribute in interest_attributes:
    color_dict = get_color_dict(attribute)
    color_schema = create_maplibre_color_schema(color_dict,attribute)
    
    params['styles'][attribute] = create_simple_map_style(interest_attributes[attribute],color_schema)
    
# reading the base html
webmap_html = file_as_string(webmap_base_path)

# doing other stuff like insertions and nasty things (TODO):

# finally generate the files:
str_to_file(webmap_html,webmap_path)
dump_json(params,webmap_params_path)

# if we are in dev mode, also dump the original params:
if in_dev:
    dump_json(params,webmap_params_original_path)