from functions import *

"""

    FILE TO STORE THE CATEGORIES FOR OSWM DATA QUALITY

"""

"""
template dict:

category = {
    'sidewalks': {},
    'crossings': {},
    'kerbs':     {},
    'other_footways': {},
}

"""

# Internal definition dicts for the functional part of categories:

improper_keys = {
    "sidewalks": {
        "kerb": "sidewalks are drawn at path axis, kerb acess points should be literally at the kerb",
        "opening_hours": "if it has opening hours it may be a private pathway, not a sidewalk",
        "paving_stones": 'paving stones is a value for "surface key"',
        "crossing": "It's inappropriate for Sidewalks, probably mistakenly tagged",
        "barrier": "if there's a barrier it may be a node in the sidewalk, but not the sidewalk itself",
        "building": "sidewalks are not buildings",
    },
    "crossings": {
        "kerb": "kerbs are points, crossings are lines",
        "barrier": "a crossing with a barrier may not be an actual crossing...",
        "name": "most crossings have no name",
        "building": "crossings are not buildings",
    },
    "kerbs": {
        "opening_hours": "a crossing may have opening hours (brigdes?), but not a kerb",
        "crossing": "It's inappropriate for Kerbs, it's for crossings",
        "crossing_ref": "It's inappropriate for Kerbs, it's for crossings",
        "name": "most kerbs have no name",
        "building": "kerbs are not buildings",
    },
    "other_footways": {
        "kerb": "kerbs are points, other footways are lines",
        "building": "footways are not buildings",
    },
}

uncanny_keys = {
    "sidewalks": {
        "traffic_signals": "may be used for crossings",
        "name": "most sidewalks don't have an actual name",
    },
    "crossings": {
        "level": "according to wiki it may be used only for indoor or if bound to a floor..."
    },
    "kerbs": {
        "button_operated": "it may be referring to the crossing, may be OK",
        "traffic_signals:sound": "it may be referring to the crossing, may be OK",
        "traffic_signals:vibration": "it may be referring to the crossing, may be OK",
        "crossing:island": "if in the middle of a crossing It's fine!! ",
    },
    "other_footways": {},
}

replaceable_values = {
    "sidewalks": {},
    "crossings": {
        "crossing": {
            "marked": "should use the tag 'crossing=uncontrolled' ",
            "zebra": "should use the tag 'crossing=uncontrolled' ",
            "island": "should use the tag 'crossing:island=yes' ",
        }
    },
    "kerbs": {},
    "other_footways": {},
}

invalid_characters = {
    "=": "The '=' character is used ONLY in textual representation of tags to separate the key from the value",
}

key_val_comm = "not appliable"

improper_geoms_dict = {
    "sidewalks": {
        "insertions": [key_val_comm, key_val_comm, "Sidewalks are meant to be lines"]
    },
    "crossings": {
        "insertions": [
            key_val_comm,
            key_val_comm,
            "crossings are generally lines, but some people also map them as points, so <b>watch out for false positives</b>",
        ]
    },
    "kerbs": {
        "insertions": [
            key_val_comm,
            key_val_comm,
            "kerbs are mostly points, but in few places people map also the whole 'kerb line' ",
        ]
    },
    "other_footways": {
        "insertions": [key_val_comm, key_val_comm, "check the feature in OSM"]
    },
}

disjointed_geoms_dict = {
    "sidewalks": {
        "insertions": [
            key_val_comm,
            key_val_comm,
            "sidewalks are part of a interconnected network, they should be connected to other linear features",
        ]
    },
    "crossings": {
        "insertions": [
            key_val_comm,
            key_val_comm,
            "Crossings are generally connected to a sidewalk, but some map them lines separately, so <b>watch out for false positives</b>. In general, crossings are designed to be part of a network, they should be connected to other features",
        ]
    },
    "kerbs": {
        "insertions": [
            key_val_comm,
            key_val_comm,
            "kerbs are generally drawn at the top of crossings, check the map",
        ]
    },
    "other_footways": {
        "insertions": [key_val_comm, key_val_comm, "check the feature in OSM"]
    },
}


# The dict for orchestration for the categories that are processed in the main pipeline:

categories_dict_keys = {
    "improper_keys": {
        "about": "Keys that (almost certainly) shouldn't be used at that feature type",
        "dict": improper_keys,
        "type": "keys",
        "invert_geomtype": False,
        "occurrences": {
            "sidewalks": {},
            "crossings": {},
            "kerbs": {},
            "other_footways": {},
        },
        "occ_count": {
            "sidewalks": 0,
            "crossings": 0,
            "kerbs": 0,
            "other_footways": 0,
        },
    },
    "uncanny_keys": {
        "about": "Keys that may be OK in some specific situations, but may be a mistake",
        "dict": uncanny_keys,
        "type": "keys",
        "invert_geomtype": False,
        "occurrences": {
            "sidewalks": {},
            "crossings": {},
            "kerbs": {},
            "other_footways": {},
        },
        "occ_count": {
            "sidewalks": 0,
            "crossings": 0,
            "kerbs": 0,
            "other_footways": 0,
        },
    },
    "keys_without_wiki": {
        "about": "Keys that may be wrong, because there's no wiki article for it",
        "dict": "quality_check/keys_without_wiki.json",
        "type": "keys",
        "invert_geomtype": False,
        "occurrences": {
            "sidewalks": {},
            "crossings": {},
            "kerbs": {},
            "other_footways": {},
        },
        "occ_count": {
            "sidewalks": 0,
            "crossings": 0,
            "kerbs": 0,
            "other_footways": 0,
        },
    },
    "replaceable_values": {
        "about": "values that are not wrong, but there's a better  option that is in the commentary",
        "dict": replaceable_values,
        "type": "values",
        "invert_geomtype": False,
        "occurrences": {
            "sidewalks": {},
            "crossings": {},
            "kerbs": {},
            "other_footways": {},
        },
        "occ_count": {
            "sidewalks": 0,
            "crossings": 0,
            "kerbs": 0,
            "other_footways": 0,
        },
    },
    "wrong_mispelled_or_unlisted_values": {
        "about": "Values that are probably wrong, but they may be mispelled or just unlisted",
        "dict": "quality_check/valid_tag_values.json",
        "type": "values",
        "invert_geomtype": False,
        "occurrences": {
            "sidewalks": {},
            "crossings": {},
            "kerbs": {},
            "other_footways": {},
        },
        "occ_count": {
            "sidewalks": 0,
            "crossings": 0,
            "kerbs": 0,
            "other_footways": 0,
        },
    },
    "invalid_characters": {
        "about": "characters that should not be in the value or in the key",
        "dict": invalid_characters,
        "type": "tags",
        "invert_geomtype": False,
        "occurrences": {
            "sidewalks": {},
            "crossings": {},
            "kerbs": {},
            "other_footways": {},
        },
        "occ_count": {
            "sidewalks": 0,
            "crossings": 0,
            "kerbs": 0,
            "other_footways": 0,
        },
    },
    # "missing_value": {
    #     'about':"tags with only a key, no value",
    #     'dict' : None,
    #     'type':'tags',
    #     'occurrences': {
    #                         'sidewalks': {},
    #                         'crossings': {},
    #                         'kerbs':     {},
    #                     },
    #     'occ_count': {
    #                 'sidewalks': 0,
    #                 'crossings': 0,
    #                 'kerbs':     0,
    #             },
    # },
}


# the geometric categories:
geom_dict_keys = {
    "disjointed_geometries": {
        "about": "Features with geometries that are not connected to others, i.e. disjointed. This is generally a special matter of concern for crossings, kerbs and sidewalks",
        "dict": disjointed_geoms_dict,
        "path": disjointed_folderpath,
        "suffix": disjointed_geoms_suffix,
        "type": "geometries",
        "invert_geomtype": False,
        "occurrences": {
            "sidewalks": {},
            "crossings": {},
            "kerbs": {},
            "other_footways": {},
        },
        "occ_count": {
            "sidewalks": 0,
            "crossings": 0,
            "kerbs": 0,
            "other_footways": 0,
        },
    },
    "improper_geometries": {
        "about": "Features with geometries (more specifically geometry types) that are incompatible with the main tags",
        "dict": improper_geoms_dict,
        "path": improper_geoms_folderpath,
        "suffix": improper_geoms_suffix,
        "type": "geometries",
        "invert_geomtype": True,
        "occurrences": {
            "sidewalks": {},
            "crossings": {},
            "kerbs": {},
            "other_footways": {},
        },
        "occ_count": {
            "sidewalks": 0,
            "crossings": 0,
            "kerbs": 0,
            "other_footways": 0,
        },
    },
}
