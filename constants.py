import sys, os

sys.path.append(".")

from config import *

###############
# intended for common values and constants, to setup the node for your city, please go to config.py
###############

# global min zoom level
min_zoom = 10

# global max zoom level
max_zoom = 22

data_format = ".parquet"

# node archives general paths
map_page_name = "./map.html"
readme_path = "./README.md"
node_home_path = "./index.html"
boundaries_path = "./data/boundaries" + data_format
boundaries_geojson_path = "./data/boundaries.geojson"
boundaries_infos_path = "./data/boundary_infos.json"
boundaries_md_path = "./data/boundaries_md.json"
workflows_path = ".github/workflows"

# data folderpaths:
improper_geoms_folderpath = "data/improper_geoms"
disjointed_folderpath = "data/disjointed"
versioning_folderpath = "data/versioning"
other_footways_folderpath = "data/other_footways"
tiles_folderpath = "data/tiles"
vrts_folderpath = "data/vrts"

# declare, so we can reuse
stairways_layername = "stairways"
main_footways_layername = "main_footways"
potential_footways_layername = "potential_footways"
informal_footways_layername = "informal_footways"
pedestrian_areas_layername = "pedestrian_areas"

# establishing other footways geometry types, default is 'LineString'
other_footways_geometry_types = {
    k: "LineString" for k, v in other_footways_subcatecories.items()
}
other_footways_geometry_types["pedestrian_areas"] = "Polygon"

data_layer_descriptions = {
    "kerbs": "Access points in the kerb lane where the sidewalk and the road meet, along a crossing.",
    "sidewalks": "A footway that is juxtaposed to a road, a type of sidepath.",
    "crossings": "The line that allows pedestrians to cross some road.",
    "other_footways": {
        "stairways": "Pathways composed of steps.",
        "main_footways": "Pathways which main usage is pedestrian displacement.",
        "potential_footways": "Pathways with vague description, generally usable for pedestrians, but sometimes not as its main or sole purpose, such as some rural tracks.",
        "informal_footways": "Pathways that are not made for pedestrian usage, but they generally used due to the absence of proper footways.",
        "pedestrian_areas": "Areas where pedestrians can generally displace freely in normal circumstances.",
    },
}

# ogr2ogr path
OGR2OGR_PATH = "ogr2ogr"

layer_tags_dict = {
    "kerbs": {
        "kerb": ["lowered", "raised", "flush", "rolled", "no", "yes"],
        "barrier": ["kerb"],
    },
    "sidewalks": {"footway": ["sidewalk"]},
    "crossings": {"footway": ["crossing"]},
    "other_footways": OTHER_FOOTWAY_RULES,
}

# columns to keep in the parquet files
# TODO: complete and apply it
in_all = [
    "geometry",  # of course
    "id",
    "surface",
    "smoothness",
    "width",
    "incline",
    "tactile_paving",
    "incline:across",
    "osm_id",
    "last_update",
]
in_linear = in_all + ["highway"]

columns_to_keep = {}

for k, v in layer_tags_dict.items():
    columns_to_keep[k] = in_all.copy() if k == "kerbs" else in_linear.copy()
    columns_to_keep[k].extend(list(v.keys()))

layer_exclusion_tags = {
    "kerbs": {},
    "sidewalks": {},
    "crossings": {},
    "other_footways": OTHER_FOOTWAY_EXCLUSION_RULES,
}

bbox_as_list = ()

# data paths
sidewalks_path = "data/sidewalks" + data_format
crossings_path = "data/crossings" + data_format
kerbs_path = "data/kerbs" + data_format
other_footways_path = "data/other_footways" + data_format

sidewalks_path_raw = "data/sidewalks_raw" + data_format
crossings_path_raw = "data/crossings_raw" + data_format
kerbs_path_raw = "data/kerbs_raw" + data_format
other_footways_path_raw = "data/other_footways_raw" + data_format

sidewalks_path_versioning = "data/versioning/sidewalks_versioning.json"
crossings_path_versioning = "data/versioning/crossings_versioning.json"
kerbs_path_versioning = "data/versioning/kerbs_versioning.json"
other_footways_path_versioning = "data/versioning/other_footways_versioning.json"

# data quality jsons path
feat_keys_path = "quality_check/feature_keys.json"
keys_without_wiki_path = "quality_check/keys_without_wiki.json"
unique_values_path = "quality_check/unique_tag_values.json"
valid_values_path = "quality_check/valid_tag_values.json"

# node homepage:
user_basepage_url = f"https://{USERNAME}.github.io/"
node_homepage_url = f"https://{USERNAME}.github.io/{REPO_NAME}/"
data_folder_url = f"https://{USERNAME}.github.io/{REPO_NAME}/data/"
data_updating_url = f"https://{USERNAME}.github.io/{REPO_NAME}/data/data_updating.html"

# codebase as page:
codebase_homepage = "https://kauevestena.github.io/oswm_codebase/"

codebase_url = "https://github.com/kauevestena/oswm_codebase"
codebase_issues_url = "https://github.com/kauevestena/oswm_codebase/issues"

paths_dict = {
    "data": {
        "sidewalks": sidewalks_path,
        "crossings": crossings_path,
        "kerbs": kerbs_path,
        "other_footways": other_footways_path,
    },
    "data_raw": {
        "sidewalks": sidewalks_path_raw,
        "crossings": crossings_path_raw,
        "kerbs": kerbs_path_raw,
        "other_footways": other_footways_path_raw,
    },
    "versioning": {
        "sidewalks": sidewalks_path_versioning,
        "crossings": crossings_path_versioning,
        "kerbs": kerbs_path_versioning,
        "other_footways": other_footways_path_versioning,
    },
    "other_footways_subcategories": {},
    "map_layers": {
        "sidewalks": sidewalks_path,
        "crossings": crossings_path,
        "kerbs": kerbs_path,
    },
}

# paths for other_footways subcategories:
for subcategory in other_footways_subcatecories:
    subcategory_path = os.path.join(
        other_footways_folderpath, subcategory + data_format
    )
    paths_dict["other_footways_subcategories"][subcategory] = subcategory_path
    paths_dict["map_layers"][subcategory] = subcategory_path

versioning_dict = paths_dict["versioning"]

# max radius to cut off unconnected crossings and kerbs
max_radius_cutoff = 50

# default note for features without values (in order to be different from zero)
default_score = 0.5

fields_values_properties = {
    "sidewalks": {
        "surface": {
            # colorscheme 12-class Set3 from colorbrewer (thx!!), avaliiable at:
            # https://colorbrewer2.org/?type=qualitative&scheme=Set3&n=12
            "asphalt": {
                "score_default": 100,
                "color": "#fb8072",  #
            },
            "concrete": {
                "score_default": 100,
                "color": "#80b1d3",
            },
            "concrete:plates": {
                "score_default": 70,
                "color": "#fccde5",  #
            },
            "paving_stones": {
                "score_default": 90,
                "color": "#bebada",  #
            },
            "sett": {
                "score_default": 60,
                "color": "#ffed6f",  #
            },
            "cobblestone": {
                "score_default": 60,
                "color": "#ffed6f",  #
            },
            "unhewn_cobblestone": {
                "score_default": 50,
                "color": "#ffffb3",  # black
            },
            "ground": {"score_default": 30, "color": "#fdb462"},  #
            "dirt": {"score_default": 30, "color": "#fdb462"},  #
            "earth": {
                "score_default": 30,
                "color": "#fdb462",  #
            },
            "sand": {
                "score_default": 30,
                "color": "#fdb462",  #
            },
            "grass": {
                "score_default": 30,
                "color": "#b3de69",  #
            },
            # 'grass_paver':{
            #     'score_default' : 3,
            #     'color' : '#000000', #black
            # },
            "paved": {
                "score_default": 60,  # equals to worst paved: sett
                "color": "#ffffff",  # white
            },
            "unpaved": {
                "score_default": 30,
                "color": "#d9d9d9",  #
            },
            # a sample for uncommon values:
            "gravel": {
                "score_default": 30,
                "color": "#bc80bd",  #
            },
            "compacted": {
                "score_default": 30,
                "color": "#bc80bd",  #
            },
            "ceramic:tiles": {
                "score_default": 70,
                "color": "#bc80bd",  #
            },
            "wood": {
                "score_default": 50,
                "color": "#bc80bd",  #
            },
            "metal": {
                "score_default": 100,
                "color": "#bc80bd",  #
            },
            # 'Petit_Pavê':{
            #     'score_default' : 65,
            #     'color' : '#bc80bd', #
            # },
            # for the filled ones:
            "?": {
                "score_default": 10,
                "color": "#434343",  #
            },
        },
        "wheelchair": {
            "yes": {
                "score_default": 0,  # equivalent to "very horrible"
                "color": "#91bfdb",  #
            },
            "designated": {
                "score_default": 0,  # equivalent to "very horrible"
                "color": "#91bfdb",  #
            },
            "limited": {
                "score_default": 0,  # equivalent to "very horrible"
                "color": "#ffffbf",  #
            },
            "no": {
                "score_default": 0,  # equivalent to "very horrible"
                "color": "#fc8d59",  #
            },
            "?": {
                "score_default": 0,  # equivalent to "very horrible"
                "color": "#434343",  #
            },
        },
        "smoothness": {
            # color scheme: ColorBrewer (thx!!) 11-class RdYlBu
            # valid:
            "excellent": {
                "score_default": 10,
                "color": "#4575b4",  #
            },
            "good": {
                "score_default": 90,
                "color": "#abd9e9",  #
            },
            "intermediate": {
                "score_default": 70,
                "color": "#ffffbf",  #
            },
            "bad": {
                "score_default": 50,
                "color": "#fdae61",  #
            },
            "very_bad": {
                "score_default": 40,
                "color": "#fdae61",  #
            },
            "horrible": {
                "score_default": 20,
                "color": "#f46d43",  #
            },
            "very_horrible": {
                "score_default": 10,
                "color": "#f46d43",  #
            },
            "impassable": {
                "score_default": 0,
                "color": "#a50026",  #
            },
            # for absence:
            "?": {
                "score_default": 40,  # equivalent to "very horrible"
                "color": "#434343",  #
            },
            # invalid values must be handled individually
        },
        "lit": {
            "yes": {
                "score_default": 10,
                "color": "#ffff99",  #
            },
            "automatic": {
                "score_default": 10,
                "color": "#ffff99",  #
            },
            "24/7": {
                "score_default": 10,
                "color": "#ffff99",  #
            },
            "no": {
                "score_default": 10,
                "color": "#6a3d9a",  #
            },
            "disused": {
                "score_default": 10,
                "color": "#6a3d9a",  #
            },
            "?": {
                "score_default": 10,
                "color": "#434343",  #
            },
        },
        "width": {
            "?": {
                "score_default": 10,
                "color": "#434343",  #
            },
            # in a future...
        },
        "incline": {
            "?": {
                "score_default": 10,
                "color": "#434343",  #
            },
            # in a future...
        },
        "tactile_paving": {
            # CHECK KERBS
        },
        "incline:across": {
            "?": {
                "score_default": 10,
                "color": "#434343",  #
            },
            # in a future...
        },
    },
    "kerbs": {
        "kerb": {
            "flush": {
                "score_default": 60,
                "color": "#ffffff",  # white
            },
            "lowered": {
                "score_default": 50,
                "color": "#ffffff",  # white
            },
            "rolled": {
                "score_default": 0,
                "color": "#808080",  # 50% gray
            },
            "no": {
                "score_default": 10,
                "color": "#bebebe",  # 75% hray
            },
            "raised": {
                "score_default": -30,
                "color": "#000000",  # black
            },
            "?": {
                "score_default": -10,  # equivalent to "raised"
                "color": "#d9d9d9",  #
            },
        },
        "tactile_paving": {
            "yes": {
                "score_default": 100,
                "color": "#6146d0",
                "opacity": 1,
            },
            "contrasted": {
                "score_default": 100,
                "color": "#6146d0",
                "opacity": 1,
            },
            "no": {
                "score_default": 0,
                "color": "#bd1006",
                "opacity": 0,
            },
            "?": {
                "score_default": 0,  # equivalent to "no"
                "color": "#717171",  # "#434343", #
                "opacity": 0,
            },
        },
    },
    "crossings": {
        # default scores should be what was named "bonus"
        "crossing": {
            # base color-scheme: ColorBrewer (thx!!) 12-class Paired
            "traffic_signals": {
                # 'score_default' : 100,
                # 'bonus' : 30,
                "score_default": 30,
                "dasharray": "0",
                "dashoffset": "0",
                "color": "#1f78b4",
            },
            "marked": {
                # 'score_default' : 90,
                # 'bonus' : 20,
                "score_default": 20,
                "dasharray": "0",
                "dashoffset": "0",
                "color": "#a6cee3",
            },
            "zebra": {
                # 'score_default' : 90,
                # 'bonus' : 20,
                "score_default": 20,
                "dasharray": "0",
                "dashoffset": "0",
                "color": "#a6cee3",
            },
            "uncontrolled": {
                # 'score_default' : 100,
                # 'bonus' : 30,
                "score_default": 30,
                "dasharray": "0",
                "dashoffset": "0",
                "color": "#a6cee3",
            },
            "unmarked": {
                # 'score_default' : 70,
                # 'bonus' : 0,
                "score_default": 0,
                # may get help on: https://gigacore.github.io/demos/svg-stroke-dasharray-generator/
                "dasharray": "5,10",
                "dashoffset": "0",
                "color": "#ffff99",
            },
            "no": {
                # 'score_default' : 0,
                # 'bonus' : -100,
                "score_default": -100,
                "dasharray": "0",
                "dashoffset": "0",
                "color": "#e31a1c",  # RED
            },
            "?": {
                # 'score_default' : 10,
                # 'bonus' : 0,
                "score_default": 0,
                "dasharray": "0",
                "dashoffset": "0",
                "color": "gray",  #
            },
        },
        "surface": {
            # CHECK SIDEWALKS
        },
        "smoothness": {
            # CHECK SIDEWALKS
        },
        "traffic_calming": {
            "table": {
                # 'score_default' : 100,
                "score_default": 20,
                # 'bonus' : 20,
                "color": "#ffff99",
            },
            "bump": {
                # 'score_default' : 100,
                "score_default": 20,
                # 'bonus' : 20,
                "color": "#ffff99",
            },
            "hump": {
                # 'score_default' : 100,
                "score_default": 20,
                # 'bonus' : 20,
                "color": "#ffff99",
            },
            "?": {
                "score_default": 0,
                "color": "#63636399",  #
            },
        },
    },
    "other_footways": {
        # by now just a copy of sidewalks, since mostly the same
    },
}


# values to be copied:
fields_values_properties["sidewalks"]["tactile_paving"] = fields_values_properties[
    "kerbs"
]["tactile_paving"]

fields_values_properties["crossings"]["surface"] = fields_values_properties[
    "sidewalks"
]["surface"]

fields_values_properties["crossings"]["smoothness"] = fields_values_properties[
    "sidewalks"
]["smoothness"]

# adding fields for 'other_footways':
fields_values_properties["other_footways"] = fields_values_properties["sidewalks"]

# for the map:
numeric_themes = {
    "age": {
        "name": "DQ - Update Age (Y)",
        "invalid_color": "#808080",
        "invalid_threshold": 0,
        "invalid_operator": "<",
        "invalid_value_above": False,
        "default_color": "#90d743",
        "default_value": 0,
        "n_digits": 2,
        "color_dict": {
            "2": "#35b779",
            "4": "#21918c",
            "6": "#31688e",
            "8": "#443983",
            "10": "#440154",
        },
    },
    "n_revs": {
        "name": "DQ - N. of Revs.",
        "invalid_color": "#808080",
        "invalid_threshold": 0,
        "invalid_operator": "<",
        "invalid_value_above": False,
        "default_color": "#1d1147",
        "default_value": 0,
        "n_digits": 2,
        "color_dict": {
            "5": "#51127c",
            "10": "#832681",
            "15": "#b73779",
            "20": "#e75263",
            "25": "#fc8961",
            "30": "#fec488",
        },
    },
}

# layernames = [key for key in fields_values_properties] # DEPRECATED


# required_fields:
req_fields = {
    "sidewalks": [
        "surface",
        "smoothness",
        "width",
        "incline",
        "tactile_paving",
        "incline:across",
        "osm_id",
        "last_update",
    ],
    "kerbs": ["kerb", "tactile_paving", "osm_id", "last_update"],
    "crossings": [
        "crossing",
        "surface",
        "smoothness",
        "traffic_calming",
        "osm_id",
        "last_update",
    ],
}

# a case of "smoothness=concrete:pĺates" demanded this
wrong_misspelled_values = {
    "sidewalks": {
        "smoothness": {"concrete:plates": "?"},
        "surface": {
            "betão": "?",
            "Petit_Pavê": "sett",
            "porcelain tiles": "ceramic:tiles",
        },
    },
    "kerbs": {},
    "crossings": {},
    "other_footways": {},
}

geom_type_dict = {
    "sidewalks": ["LineString"],
    "crossings": ["LineString"],
    "kerbs": ["Point"],
    "other_footways": ["LineString", "Polygon", "MultiPolygon"],
}

# basic geometry mapping, generally just to build feature links:
geom_mapping = {
    "Point": "node",
    "LineString": "way",
    "Polygon": "way",
    "MultiPolygon": "relation",
    "MultiLineString": "way",
}


all_layers_geom_types = {k: v[0] for k, v in geom_type_dict.items()}
del all_layers_geom_types["other_footways"]
for subcategory in other_footways_geometry_types:
    all_layers_geom_types[subcategory] = other_footways_geometry_types[subcategory]


statistics_basepath = "statistics"
statistcs_specs_path = "statistics_specs"


# defined here to avoid circular importing problems
def get_url(relative_url, base_url=node_homepage_url):
    return os.path.join(base_url, relative_url)


# to fill in default values for dates:
default_missing_day = 9
default_missing_month = 8
default_missing_year = 2004
# OSM's foundation date :-)

# Footway types fieldname
oswm_footway_fieldname = "oswm_footway"
