from webmap_lib import *
import argparse

# create a --development flag:
parser = argparse.ArgumentParser()
parser.add_argument("--development", action="store_true")
args = parser.parse_args()

in_dev = args.development

# first, reading the parameters
params = read_json(webmap_params_original_path)

# then override and fill in with the stuff:
params["data_layers"] = MAP_DATA_LAYERS

# the layers that by type:
params["layer_types"] = layer_type_groups

# boundaries:
params["bounds"] = get_boundaries_bbox()

# updating the node's url:
params["node_url"] = node_homepage_url

# # generating the "sources" and layernames:
params.update(get_sources(only_urls=True))


# very temporary:
# params['sources'] = MAP_SOURCES

params["styles"] = {
    "footway_categories": create_base_style(),
    "crossings_and_kerbs": create_crossings_kerbs_style(),
}

interest_attributes = {
    # key is raw attribute name, value is label (human readable)
    "surface": "Surface",
    "smoothness": "Smoothness",
    "tactile_paving": "Tactile Paving",
    "lit": "Lighting",
    "traffic_calming": "Traffic Calming",
    "wheelchair": "wheelchair=* tag",
}

attribute_layers = {
    # default is "sidewalks", only specified if different:
    "traffic_calming": "crossings",
}

different_else_color = {
    # default is "gray", specifyed ony if different:
    "traffic_calming": "#63636366",
}

for attribute in interest_attributes:
    color_dict = get_color_dict(attribute, attribute_layers.get(attribute, "sidewalks"))
    color_schema = create_maplibre_color_schema(
        color_dict, attribute, different_else_color.get(attribute, "gray")
    )

    params["styles"][attribute] = create_simple_map_style(
        interest_attributes[attribute], color_schema, color_dict, attribute
    )

# reading the base html
webmap_html = file_as_string(webmap_base_path)

# doing other stuff like insertions and nasty things (TODO):

# finally generate the files:
str_to_file(webmap_html, webmap_path)
dump_json(params, webmap_params_path)

# if we are in dev mode, also dump the original params:
if in_dev:
    dump_json(params, webmap_params_original_path)
