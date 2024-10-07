import sys

sys.path.append("oswm_codebase")
from copy import deepcopy
from standalone_legend import *


MAP_DATA_LAYERS = [l for l in paths_dict["map_layers"]]

# webmap stuff:
BASEMAP_URL = "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
webmap_params_original_path = "oswm_codebase/webmap/webmap_params.json"
webmap_params_path = "webmap_params.json"
webmap_base_path = "oswm_codebase/webmap/webmap_base.html"
webmap_path = "map.html"

assets_path = "oswm_codebase/assets/"
map_symbols_assets_path = os.path.join(assets_path, "map_symbols")

# mapping geometry types to maplibre style
map_geom_type_mapping = {
    "Polygon": "fill",
    "LineString": "line",
    "Point": "circle",
    "MultiPolygon": "fill",
    "MultiLineString": "line",
    "MultiPoint": "circle",
}

# types for each layer:
layertypes_dict = {
    k: map_geom_type_mapping[v] for k, v in all_layers_geom_types.items()
}


# the layers by type:
line_layers = [l for l in MAP_DATA_LAYERS if layertypes_dict[l] == "line"]
fill_layers = [l for l in MAP_DATA_LAYERS if layertypes_dict[l] == "fill"]
circle_layers = [l for l in MAP_DATA_LAYERS if layertypes_dict[l] == "circle"]

layer_type_groups = {
    # the order in this dict determines the order in the webmap:
    "fill": fill_layers,
    "line": line_layers,
    "circle": circle_layers,
}


# immutable layers, among different styles:
immutable_layers = [
    {
        "id": "osm-baselayer",
        "source": "osm",
        "type": "raster",
        "paint": {"raster-opacity": 0.9},
    },
    {
        "id": "boundaries",
        "type": "line",
        "source": "boundaries",
        "paint": {"line-color": "white", "line-opacity": 0.4},
    },
]

# base dict for a map style:
mapstyle_basedict = {"version": 8, "sources": {}, "layers": []}

# base_dicts for each layer type:
# "id": "pedestrian_areas",
# "source": "oswm_pmtiles_pedestrian_areas",
# "source-layer": "pedestrian_areas",
# "type": "fill",
# "paint": {
#     "fill-color": "gray",
#     "fill-opacity": 0.5
# }

layertypes_basedict = {
    "line": {
        "id": "",
        "source": "",
        "source-layer": "",
        "type": "line",
        "paint": {
            "line-color": "steelblue",
            "line-width": [
                "case",
                ["boolean", ["feature-state", "hover"], False],
                6,
                3,
            ],
        },
    },
    "fill": {
        "id": "",
        "source": "",
        "source-layer": "",
        "type": "fill",
        "paint": {
            "fill-color": "steelblue",
            "fill-opacity": [
                "case",
                ["boolean", ["feature-state", "hover"], False],
                0.8,
                0.5,
            ],
        },
    },
    "circle": {
        "id": "",
        "source": "",
        "source-layer": "",
        "type": "circle",
        "minzoom": 17,
        "paint": {
            "circle-color": "steelblue",
            "circle-opacity": 0.8,
            "circle-radius": [
                "case",
                ["boolean", ["feature-state", "hover"], False],
                7,
                4,
            ],
        },
    },
}

color_attribute = {"fill": "fill-color", "line": "line-color", "circle": "circle-color"}


def get_sources(terrain_url=None, only_urls=False):
    ret = {}
    ret["sources"] = {}

    for layername in paths_dict["map_layers"]:
        ret[f"{layername}_url"] = f"{node_homepage_url}data/tiles/{layername}.pmtiles"

        ret["sources"][f"oswm_pmtiles_{layername}"] = {
            "type": "vector",
            "url": f"pmtiles://{ret[f'{layername}_url']}",
            "promoteId": "id",
            "attribution": r'© <a href="https://openstreetmap.org">OpenStreetMap Contributors</a>',
        }

    ret["boundaries_url"] = f"{node_homepage_url}data/boundaries.geojson"

    # basemap:
    ret["sources"]["osm"] = {
        "type": "raster",
        "tiles": [BASEMAP_URL],
        "attribution": r'© <a href="https://openstreetmap.org">OpenStreetMap Contributors</a>; basemap by <a href="https://carto.com/attribution">CARTO</a>',
    }

    # boundaries:
    ret["sources"]["boundaries"] = {
        "type": "geojson",
        "data": ret["boundaries_url"],
        "attribution": r'© <a href="https://openstreetmap.org">OpenStreetMap Contributors</a>',
    }

    if terrain_url:
        # # # terrain:
        ret["sources"]["terrain"] = {
            "type": "raster-dem",
            "url": terrain_url,
            "tileSize": 256,
        }

    if only_urls:
        del ret["sources"]
        return ret
    else:
        return ret


MAP_SOURCES = get_sources()["sources"]


def intialize_style_dict(name, sources=MAP_SOURCES):
    style_dict = deepcopy(mapstyle_basedict)

    style_dict["sources"] = sources

    style_dict["name"] = name

    style_dict["layers"].extend(deepcopy(immutable_layers))

    return style_dict


def initialize_layer_dict(layername):
    layer_type = layertypes_dict[layername]

    layer_dict = deepcopy(layertypes_basedict[layer_type])

    # now we can set the id and source:
    layer_dict["id"] = layername
    layer_dict["source"] = f"oswm_pmtiles_{layername}"
    layer_dict["source-layer"] = layername

    return layer_dict, layer_type


def sort_keys_by_order(input_dict, order_list):
    ordered_keys = []
    remaining_keys = list(input_dict.keys())

    for order in order_list:
        for key in list(remaining_keys):
            if input_dict[key] == order:
                ordered_keys.append(key)
                remaining_keys.remove(key)

    ordered_keys.extend(remaining_keys)

    return ordered_keys


ordered_map_layers = sort_keys_by_order(layertypes_dict, layer_type_groups.keys())


def create_base_style(sources=MAP_SOURCES, name="Footway Categories"):

    default_color = "steelblue"

    custom_layer_colors = {
        "stairways": "#8a7e2f",
        "main_footways": "#299077",
        "informal_footways": "#b0645a",
        "potential_footways": "#9569a4",
    }

    custom_layer_dash_patterns = {
        "crossings": [1, 0.5],
    }

    custom_legend_widths = {"kerbs": 8}

    style_dict = intialize_style_dict(name, sources)

    # declaring the legend:
    style_legend = StandaloneLegend()

    for layername in ordered_map_layers:
        layer_dict, layer_type = initialize_layer_dict(layername)

        if layername in custom_layer_colors:
            layer_dict["paint"]["line-color"] = custom_layer_colors[layername]

        if layername in custom_layer_dash_patterns:
            layer_dict["paint"]["line-dasharray"] = custom_layer_dash_patterns[
                layername
            ]

        # now the custom colors
        style_dict["layers"].append(layer_dict)

        # adding to the legend:
        style_legend.add_element(
            layer_type,
            layername,
            **{
                "color": custom_layer_colors.get(layername, default_color),
                "width": custom_legend_widths.get(layername, 4),
                "dashes": custom_layer_dash_patterns.get(layername),
            },
        )

    style_legend.export(
        os.path.join(map_symbols_assets_path, "footway_categories" + ".png")
    )

    return style_dict


def create_simple_map_style(
    name,
    color_dict,
    attribute_name,
    else_color="gray",
    sources=MAP_SOURCES,
    generate_shadow_layers=False,  # DEPRECATED
):
    style_dict = intialize_style_dict(name, sources)

    color_schema = create_maplibre_color_schema(color_dict, attribute_name, else_color)

    # creating "shadow layers" for line layers only:
    if generate_shadow_layers:
        for layername in ordered_map_layers:
            if layertypes_dict[layername] == "line":
                layer_dict = deepcopy(layertypes_basedict["line"])
                layer_dict["id"] = f"{layername}_shadow"
                layer_dict["source"] = f"oswm_pmtiles_{layername}"
                layer_dict["source-layer"] = layername
                layer_dict["paint"]["line-color"] = "black"
                layer_dict["paint"]["line-width"] = 4

                style_dict["layers"].append(layer_dict)

    for layername in ordered_map_layers:
        layer_dict, layer_type = initialize_layer_dict(layername)

        # layer_type = layertypes_dict[layername]

        layer_dict["paint"][color_attribute[layer_type]] = color_schema

        style_dict["layers"].append(layer_dict)

    # now generating the map symbols
    # TODO: check the hashing, otherwise no need to re-run
    style_legend = StandaloneLegend()

    custom_line_args = {
        "linewidth": 4,
    }

    for key in color_dict:
        style_legend.add_line(label=key, color=color_dict[key], **custom_line_args)

    style_legend.add_line(label="other", color=color_schema[-1], **custom_line_args)

    style_legend.export(os.path.join(map_symbols_assets_path, f"{attribute_name}.png"))

    return style_dict


def get_color_dict(columnname, layer="sidewalks", attribute="color"):
    """
    Given a columnname, layername and attribute, returns a dictionary mapping each value in the column to its corresponding attribute value.

    :param columnname: column name
    :param layer: layer name (default to 'sidewalks')
    :param attribute: attribute name (default to 'color')

    :return: a dictionary mapping each value in the column to its corresponding attribute value
    """
    colordict = {}

    base_dict = fields_values_properties[layer][columnname]

    for key in base_dict:
        colordict[key] = base_dict[key][attribute]

    return colordict


def create_maplibre_color_schema(attribute_dict, attribute_name, else_color="gray"):
    schema = ["case"]
    for key, value in attribute_dict.items():
        schema.extend([["==", ["get", attribute_name], key], value])
    schema.append(else_color)
    return schema


def create_crossings_kerbs_style(
    filename="crossings_and_kerbs",
    sources=MAP_SOURCES,
    name="Crossings and Kerbs",
    else_color="#63636380",
):

    style_dict = intialize_style_dict(name, sources)

    interest_layers = {
        # layername : tag key
        "crossings": "crossing",
        "kerbs": "kerb",
    }

    legend_basenames = {
        "crossings": "Crossings",
        "kerbs": "Kerbs",
    }

    legend_widths = {
        "crossings": 4,
        "kerbs": 8,
    }

    # instantiating the legend:
    style_legend = StandaloneLegend()

    for layername in ordered_map_layers:
        layer_type = layertypes_dict[layername]

        layer_dict = deepcopy(layertypes_basedict[layer_type])

        if layername in interest_layers:
            # layer_dict.update(custom_crossing_kerbs_dict[layername])
            color_dict = get_color_dict(interest_layers[layername], layername)
            color_schema = create_maplibre_color_schema(
                color_dict, interest_layers[layername], "gray"
            )
            layer_dict["paint"][color_attribute[layer_type]] = color_schema

            # making kerbs a little bigger
            if layername == "kerbs":
                layer_dict["paint"]["circle-radius"] = [
                    "case",
                    ["boolean", ["feature-state", "hover"], False],
                    8,
                    5,
                ]

            color_dict[r"other/none"] = else_color

            for key in color_dict:
                style_legend.add_element(
                    layer_type,
                    f"{legend_basenames[layername]} - {key}",
                    **{
                        "color": color_dict[key],
                        "width": legend_widths[layername],
                    },
                )

        else:
            # all other layers will be a very faded gray:
            layer_dict["paint"][color_attribute[layer_type]] = else_color

        # now we can set the id and source:
        layer_dict["id"] = layername
        layer_dict["source"] = f"oswm_pmtiles_{layername}"
        layer_dict["source-layer"] = layername

        style_dict["layers"].append(layer_dict)

    style_legend.export(os.path.join(map_symbols_assets_path, f"{filename}.png"))

    return style_dict


def create_simple_numeric_style(
    name,
    color_dict,
    attribute_name,
    default_color,
    default_value=0,
    invalid_color="#808080",
    invalid_threshold=0,
    invalid_operator="<",
    n_digits=2,
    sources=MAP_SOURCES,
    invalid_value_above=False,
):
    """
    Creates a simple style for numeric values, where values in the color_dict are mapped to their corresponding colors.

    :param name: name of the style
    :param color_dict: a dictionary mapping each value to its corresponding color
    :param attribute_name: name of the attribute to style
    :param default_color: default color
    :param invalid_color: color for invalid values
    :param invalid_threshold: threshold for invalid values
    :param invalid_operator: operator for invalid values
    :param sources: sources for the style
    :param invalid_value_above: if True, values above the threshold are invalid
    :return: the style dictionary

    To generate discretized good styles, use: https://waldyrious.net/viridis-palette-generator/

    """
    style_dict = intialize_style_dict(name, sources)

    color_schema = [
        "case",
        [invalid_operator, ["get", attribute_name], invalid_threshold],
        invalid_color,  #
        [
            "step",
            ["get", attribute_name],
            default_color,
            # 2,
            # "#7CFC00",  # // Age >= 2
            # 4,
            # "#ADFF2F",  # // Age >= 4
            # 6,
            # "#FFD700",  # // Age >= 6
            # 8,
            # "#FF8C00",  # // Age >= 8
            # 10,
            # "#FF0000",  # // Age >= 10
        ],
    ]

    # to make it easier to read, we sort the keys:
    sorted_keys = list(sorted(color_dict.keys(), key=float))

    for key in sorted_keys:
        value = color_dict[key]
        color_schema[3].append(float(key))
        color_schema[3].append(value)

    for layername in ordered_map_layers:
        # seems that all layers will have the same style:
        layer_dict, layer_type = initialize_layer_dict(layername)

        layer_dict["paint"][color_attribute[layer_type]] = color_schema

        style_dict["layers"].append(layer_dict)

    # instantiating the legend:
    style_legend = StandaloneLegend()

    custom_line_args = {
        "linewidth": 4,
    }

    # the invalid, if above:
    if invalid_value_above:
        style_legend.add_line(label="n.a.", color=invalid_color, **custom_line_args)

    # adding regular values
    style_legend.add_line(
        # label=f"{default_value}{get_spaces(default_value)}-  {sorted_keys[0]}",
        label=get_formatted_interval_string(default_value, sorted_keys[0], n_digits),
        color=default_color,
        **custom_line_args,
    )

    last_position = len(sorted_keys) - 1
    for i, key in enumerate(sorted_keys):

        if i == last_position:
            label_name = f"{key} +"

        else:  # avoiding invalid positions at the call
            # label_name = f"{key} - {sorted_keys[i+1]}"
            label_name = get_formatted_interval_string(
                key, sorted_keys[i + 1], n_digits
            )

        style_legend.add_line(
            label=label_name, color=color_dict[key], **custom_line_args
        )

    # the invalid, if below:
    if not invalid_value_above:
        style_legend.add_line(label="n.a.", color=invalid_color, **custom_line_args)

    # exporting
    style_legend.export(os.path.join(map_symbols_assets_path, f"{attribute_name}.png"))

    return style_dict


# call just once:
create_folderlist([map_symbols_assets_path])
