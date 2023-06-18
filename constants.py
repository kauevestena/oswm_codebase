import sys
sys.path.append('.')

from config import *

###############
# intended for common values and constants, to setup the node for your city, please go to config.py
###############

# Wheter to use OSMNX or to use the 'osm_fetch.py' functions
USE_OSMNX = True

# global min zoom level
min_zoom = 10

# global max zoom level
max_zoom = 22

# node archives general paths
map_page_name = "./map.html"
readme_path = "./README.md"
node_home_path = "./index.html"


# ogr2ogr path
OGR2OGR_PATH = 'ogr2ogr'

# data paths
sidewalks_path = 'data/sidewalks.geojson'
crossings_path = 'data/crossings.geojson'
kerbs_path = 'data/kerbs.geojson'

sidewalks_path_raw = 'data/sidewalks_raw.geojson'
crossings_path_raw = 'data/crossings_raw.geojson'
kerbs_path_raw = 'data/kerbs_raw.geojson'


sidewalks_path_versioning = 'data/sidewalks_versioning.json'
crossings_path_versioning = 'data/crossings_versioning.json'
kerbs_path_versioning = 'data/kerbs_versioning.json'

# node homepage:
user_basepage_url = f'https://{USERNAME}.github.io/'
node_homepage_url = f'https://{USERNAME}.github.io/{REPO_NAME}/'
data_updating_utl = f'https://{USERNAME}.github.io/{REPO_NAME}/data/data_updating.html'

paths_dict = {
    'data' :{
        'sidewalks': sidewalks_path,
        'crossings': crossings_path,
        'kerbs': kerbs_path,
    },
    'data_raw' : {
        'sidewalks': sidewalks_path_raw,
        'crossings': crossings_path_raw,
        'kerbs': kerbs_path_raw,
    },
        'versioning' : {
        'sidewalks': sidewalks_path_versioning,
        'crossings': crossings_path_versioning,
        'kerbs': kerbs_path_versioning,
    }
}

# max radius to cut off unconnected crossings and kerbs
max_radius_cutoff = 50

# default note for features without values (in order to be different from zero)
default_score = 0.5




fields_values_properties = {
    'sidewalks':{
        'surface': {
            # colorscheme 12-class Set3 from colorbrewer (thx!!), avaliiable at:
            # https://colorbrewer2.org/?type=qualitative&scheme=Set3&n=12

            'asphalt':{
                'score_default' : 100,
                'color' : '#fb8072', #
            },
            'concrete':{
                'score_default' : 100,
                'color' : '#80b1d3', 
            },
            'concrete:plates':{
                'score_default' : 70,
                'color' : '#fccde5', #
            },
            'paving_stones':{
                'score_default' : 90,
                'color' : '#bebada', #
            },
            'sett':{
                'score_default' : 60,
                'color' : '#ffed6f', #
            },

            'cobblestone':{
                'score_default' : 60,
                'color' : '#ffed6f', #
            },
            
            'unhewn_cobblestone':{
                'score_default' : 50,
                'color' : '#ffffb3', #black
            },

            'ground':{
                'score_default' : 30,
                'color' : '#fdb462' }, #
            'dirt':{
                'score_default' : 30,
                'color' : '#fdb462' }, #
            'earth':{
                'score_default' : 30,
                'color' : '#fdb462', #
            },
            'sand':{
                'score_default' : 30,
                'color' : '#fdb462', #
            },
            'grass':{
                'score_default' : 30,
                'color' : '#b3de69', #
            },
            # 'grass_paver':{
            #     'score_default' : 3,
            #     'color' : '#000000', #black
            # },

            'paved':{
                'score_default' : 60, # equals to worst paved: sett
                'color' : '#ffffff', # white
            },
            'unpaved':{
                'score_default' : 30,
                'color' : '#d9d9d9', #
            },

            # a sample for uncommon values:

            'gravel':{
                'score_default' : 30,
                'color' : '#bc80bd', #
            },

            'compacted':{
                'score_default' : 30,
                'color' : '#bc80bd', #
            },


            'ceramic:tiles':{
                'score_default' : 70,
                'color' : '#bc80bd', #
            },

            'wood':{
                'score_default' : 50,
                'color' : '#bc80bd', #
            },

            'metal':{
                'score_default' : 100,
                'color' : '#bc80bd', #
            },

            # 'Petit_Pavê':{
            #     'score_default' : 65,
            #     'color' : '#bc80bd', #
            # },

            # for the filled ones:
            '?':{
                'score_default' : 10,
                'color' : '#434343', #
            },




        },
        'smoothness' : {
            # for absence:
            '?':{
                'score_default' : 40, # equivalent to "very horrible"
                'color' : '#434343', #
            },

            # color scheme: ColorBrewer (thx!!) 11-class RdYlBu

            # valid:
            'excellent':{
                'score_default' : 10, 
                'color' : '#4575b4', #
            },
            'good':{
                'score_default' : 90, 
                'color' : '#abd9e9', #
            },
            'intermediate':{
                'score_default' : 70, 
                'color' : '#ffffbf', #
            },
            'bad':{
                'score_default' : 50, 
                'color' : '#fdae61', #
            },
            'very_bad':{
                'score_default' : 40, 
                'color' : '#fdae61', #
            },
            'horrible':{
                'score_default' : 20, 
                'color' : '#f46d43', #
            },
            'very_horrible':{
                'score_default' : 10, 
                'color' : '#f46d43', #
            },
            'impassable':{
                'score_default' : 0, 
                'color' : '#a50026', #
            },


        # invalid values must be handled individually
                                                                                                 

        },
        'width':{
            '?':{
                'score_default' : 10,
                'color' : '#434343', #
            },
            # in a future...
        },
        'incline':{
            '?':{
                'score_default' : 10,
                'color' : '#434343', #
            },
            # in a future...
        },
        'tactile_paving':{
            #CHECK KERBS
        },
        'incline:across':{
            '?':{
                'score_default' : 10,
                'color' : '#434343', #
            },
            # in a future...
        }
    },

    'kerbs':{
        'kerb':{
            'raised':{
                'score_default' : -30,
                'color' : '#000000', #black
            },
            'rolled':{
                'score_default' : 0,
                'color' : '#808080', #50% gray
            },
            'no':{
                'score_default' : 10,
                'color' : '#bebebe', #75% hray
            },
            'lowered':{
                'score_default' : 50,
                'color' : '#ffffff', #white
            },
            'flush':{
                'score_default' : 60,
                'color' : '#ffffff', #white
            },

            '?':{
                'score_default' : -10, # equivalent to "raised"
                'color' : '#d9d9d9', #
            },

        },
        'tactile_paving':{
            'yes':{
                'score_default' : 100,
                'color' : '#000000', #black

                'opacity' : 1, 
            },
            'contrasted':{
                'score_default' : 100,
                'color' : '#000000', #black

                'opacity' : 1, 

            },
            'no':{
                'score_default' : 0,
                'color' : 'rgba(0, 0, 0, 1)', # transparent

                'opacity' : 0, 

            },

            '?':{
                'score_default' : 0, # equivalent to "no"
                'color' : 'rgba(0, 0, 0, 1)', #

                'opacity' : 0, 

            },

        }
        },
    'crossings':{
        # default scores should be what was named "bonus"
        'crossing': {
            'no':{
                # 'score_default' : 0,
                # 'bonus' : -100,
                'score_default' : -100,

                'dasharray' :"0",
                'dashoffset': '0',

                'color' : '#ff0000', # RED

            },
            'unmarked':{
                # 'score_default' : 70,
                # 'bonus' : 0,
                'score_default' : 0,

                # may get help on: https://gigacore.github.io/demos/svg-stroke-dasharray-generator/

                'dasharray' :"5,10",
                'dashoffset': '0',


                'color' : '#000000', #black
            },
            'marked':{
                # 'score_default' : 90,
                # 'bonus' : 20,

                'score_default' : 20,

                'dasharray' :"0",
                'dashoffset': '0',


                'color' : '#000000', #black
            },

            'zebra':{
                # 'score_default' : 90,
                # 'bonus' : 20,

                'score_default' : 20,

                'dasharray' :"0",
                'dashoffset': '0',


                'color' : '#000000', #black
            },

            'uncontrolled':{
                # 'score_default' : 100,
                # 'bonus' : 30,

                'score_default' : 30,

                'dasharray' :"0",
                'dashoffset': '0',


                'color' : '#ffffff', #white
            },

            'traffic_signals':{
                # 'score_default' : 100,
                # 'bonus' : 30,

                'score_default' : 30,

                'dasharray' :"0",
                'dashoffset': '0',

                'color' : '#ffffff', #white
            },

            '?':{
                # 'score_default' : 10,
                # 'bonus' : 0,

                'score_default' : 0,

                'dasharray' :"0",
                'dashoffset': '0',


                'color' : '#d9d9d9', #
            },


        },
        'surface':{
            # CHECK SIDEWALKS

        },
        'smoothness':{
            # CHECK SIDEWALKS


        },
        'traffic_calming':{
            'table':{
                # 'score_default' : 100,
                'score_default' : 20,

                # 'bonus' : 20,
                'color' : '#ffffff',
            },

            'bump':{
                # 'score_default' : 100,
                'score_default' : 20,

                # 'bonus' : 20,
                'color' : '#ffffff',
            },

            'hump':{
                # 'score_default' : 100,
                'score_default' : 20,

                # 'bonus' : 20,
                'color' : '#ffffff',
            },

            '?':{
                'score_default' : 0,
                'color' : '#d9d9d9', #
            },

        }
}
}

layernames = [key for key in fields_values_properties]


# values to be copied:
fields_values_properties['sidewalks']['tactile_paving'] = fields_values_properties['kerbs']['tactile_paving']

fields_values_properties['crossings']['surface'] = fields_values_properties['sidewalks']['surface']

fields_values_properties['crossings']['smoothness'] = fields_values_properties['sidewalks']['smoothness']


# required_fields:
req_fields = {
    'sidewalks':['surface','smoothness','width','incline','tactile_paving','incline:across','osm_id','last_update'],
    'kerbs':['kerb','tactile_paving','osm_id','last_update'],
    'crossings':['crossing','surface','smoothness','traffic_calming','osm_id','last_update'],
}

# a case of "smoothness=concrete:pĺates" demanded this
wrong_misspelled_values ={
    'sidewalks':{
        'smoothness':{'concrete:plates':'?'},
        'surface':{'betão':'?','Petit_Pavê':'sett','porcelain tiles':'ceramic:tiles'}
    },
    'kerbs':{

    },
    'crossings':{

    },
}