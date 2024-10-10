from statistics_funcs import *

gdfs_dict = get_gdfs_dict()
updating_dicts = {}


for category in paths_dict["data"]:

    if os.path.exists(paths_dict["versioning"].get(category)):
        updating_dicts[category] = pd.read_json(versioning_dict[category])
    else:
        updating_dicts[category] = pd.DataFrame()


charts_specs = {
    "sidewalks": {
        "sidewalks_smoothness_x_surface": {
            "function": double_scatter_bar,
            "params": {
                "input_df": gdfs_dict["sidewalks"],
                "title": "Surface x Smoothness (sidewalks)",
                "xs": "surface",
                "ys": "smoothness",
                "scolor": None,
                "xh": "count()",
                "yh1": "surface",
                "yh2": "smoothness",
                "hcolor": "length(km)",
                "fontsize": 24,
                "tooltip_fields": ["element_type", "id"],
            },
            "title": "Surface x Smoothness",
        },
        "sidewalks_surface": {
            "function": create_barchartV2,
            "params": {
                "input_gdf": gdfs_dict["sidewalks"],
                "fieldname": "surface",
                "title": "Sidewalks Surface Type",
                "str_to_append": " type",
                "title_fontsize": 24,
            },
            "title": "Surface Type",
        },
        "sidewalks_smoothness": {
            "function": create_barchartV2,
            "params": {
                "input_gdf": gdfs_dict["sidewalks"],
                "fieldname": "smoothness",
                "title": "Sidewalks Smoothness Condition",
                "str_to_append": " type",
                "title_fontsize": 24,
            },
            "title": "Smoothness Condition",
        },
        "sidewalks_tactile_paving": {
            "function": create_barchartV2,
            "params": {
                "input_gdf": gdfs_dict["sidewalks"],
                "fieldname": "tactile_paving",
                "title": "Sidewalks Tactile Paving Presence",
                "str_to_append": " type",
                "title_fontsize": 24,
            },
            "title": "Tactile Paving P.",
        },
        "sidewalks_width": {
            "function": create_barchartV2,
            "params": {
                "input_gdf": gdfs_dict["sidewalks"],
                "fieldname": "tactile_paving",
                "title": "Sidewalks Width Values",
                "str_to_append": " type",
                "title_fontsize": 24,
            },
            "title": "Width Values",
        },
        "sidewalks_incline": {
            "function": create_barchartV2,
            "params": {
                "input_gdf": gdfs_dict["sidewalks"],
                "fieldname": "incline",
                "title": "Sidewalks Incline Values",
                "str_to_append": " type",
                "title_fontsize": 24,
            },
            "title": "Incline Values",
        },
        "sidewalks_age": {
            "function": create_linked_boxplot_histogram,
            "params": {
                "df": gdfs_dict["sidewalks"],
                "column": "age",
                "boxplot_title": "Sidewalks Age",
                "tooltip_fields": ["element_type", "id"],
            },
            "title": "Sidewalks Age",
        },
        "sidewalks_length": {
            "function": create_linked_boxplot_histogram,
            "params": {
                "df": gdfs_dict["sidewalks"],
                "column": "length(km)",
                "boxplot_title": "Sidewalks Length (km)",
                "tooltip_fields": ["element_type", "id"],
            },
            "title": "Sidewalks Length (km)",
        },
        "sidewalks_yr_moth_update": {
            "function": create_barchart,
            "params": {
                "input_df": updating_dicts["sidewalks"],
                "fieldname": "year_month",
                "title": "Year and Month Of Update (Sidewalks)",
            },
            "title": "Year and Month Of Update",
        },
        "sidewalks_number_revisions": {
            "function": create_barchart,
            "params": {
                "input_df": updating_dicts["sidewalks"],
                "fieldname": "n_revs",
                "title": "Year and Month Of Update (Sidewalks)",
            },
            "title": "Number Of Revisions",
        },
    },
    "crossings": {
        "crossing_types": {
            "function": create_barchart,
            "params": {
                "input_df": gdfs_dict["crossings"],
                "fieldname": "crossing",
                "title": "Crossing Type",
            },
            "title": "Crossing Type",
        },
        "crossing_surface": {
            "function": create_barchart,
            "params": {
                "input_df": gdfs_dict["crossings"],
                "fieldname": "surface",
                "title": "Crossing Surface",
            },
            "title": "Crossing Surface",
        },
        "crossings_smoothness_x_surface": {
            "function": double_scatter_bar,
            "params": {
                "input_df": gdfs_dict["crossings"],
                "title": "Surface x Smoothness (crossings)",
                "xs": "surface",
                "ys": "smoothness",
                "scolor": None,
                "xh": "count()",
                "yh1": "surface",
                "yh2": "smoothness",
                "hcolor": "crossing",
                "fontsize": 24,
                "tooltip_fields": ["element_type", "id"],
            },
            "title": "Surface x Smoothness",
        },
        "crossings_yr_moth_update": {
            "function": create_barchart,
            "params": {
                "input_df": updating_dicts["crossings"],
                "fieldname": "year_month",
                "title": "Year and Month Of Update (Crossings)",
            },
            "title": "Year and Month Of Update",
        },
        "crossings_number_revisions": {
            "function": create_barchart,
            "params": {
                "input_df": updating_dicts["crossings"],
                "fieldname": "n_revs",
                "title": "Year and Month Of Update (crossings)",
            },
            "title": "Number Of Revisions",
        },
    },
    "kerbs": {
        "kerbs_x_paving_x_wheelchair": {
            "function": double_scatter_bar,
            "params": {
                "input_df": gdfs_dict["kerbs"],
                "title": "Kerb x Tactile Paving x Wheelchair Acess.",
                "xs": "kerb",
                "ys": "tactile_paving",
                "scolor": None,
                "xh": "count()",
                "yh1": "kerb",
                "yh2": "tactile_paving",
                "hcolor": "wheelchair",
                "fontsize": 24,
                "tooltip_fields": ["element_type", "id"],
            },
            "title": "Surface x Smoothness",
        },
        "kerb_types": {
            "function": create_barchart,
            "params": {
                "input_df": gdfs_dict["kerbs"],
                "fieldname": "kerb",
                "title": "Kerb Type",
            },
            "title": "Kerb Type",
        },
        "kerb_tactile_paving": {
            "function": create_barchart,
            "params": {
                "input_df": gdfs_dict["kerbs"],
                "fieldname": "tactile_paving",
                "title": "Kerb Tactile Paving Presence",
            },
            "title": "Tactile Paving Presence",
        },
        "kerb_wheelchair_access": {
            "function": create_barchart,
            "params": {
                "input_df": gdfs_dict["kerbs"],
                "fieldname": "wheelchair",
                "title": "Kerb Wheelchair Acessibility",
            },
            "title": "Wheelchair Acessibility",
        },
        "kerbs_yr_moth_update": {
            "function": create_barchart,
            "params": {
                "input_df": updating_dicts["kerbs"],
                "fieldname": "year_month",
                "title": "Year and Month Of Update (Kerbs)",
            },
            "title": "Year and Month Of Update",
        },
        "kerbs_number_revisions": {
            "function": create_barchart,
            "params": {
                "input_df": updating_dicts["kerbs"],
                "fieldname": "n_revs",
                "title": "Number Of Revisions (Kerbs)",
            },
            "title": "Number Of Revisions",
        },
    },
    "other_footways": {
        "other_footways_subcategory": {
            "function": create_barchartV2,
            "params": {
                "input_gdf": gdfs_dict["other_footways"],
                "fieldname": oswm_footway_fieldname,
                "title": "Sub-category (Layer)",
            },
            "title": "Incline Values",
        },
        "other_footways_surface": {
            "function": create_barchart,
            "params": {
                "input_df": gdfs_dict["other_footways"],
                "fieldname": "surface",
                "title": "other_footways Surface",
            },
            "title": "Other Footways Surface",
        },
        "other_footways_smoothness_x_surface": {
            "function": double_scatter_bar,
            "params": {
                "input_df": gdfs_dict["other_footways"],
                "title": "Surface x Smoothness (other_footways)",
                "xs": "surface",
                "ys": "smoothness",
                "scolor": None,
                "xh": "count()",
                "yh1": "surface",
                "yh2": "smoothness",
                "hcolor": "crossing",
                "fontsize": 24,
                "tooltip_fields": ["element_type", "id"],
            },
            "title": "Surface x Smoothness",
        },
        "other_footways_yr_moth_update": {
            "function": create_barchart,
            "params": {
                "input_df": updating_dicts["other_footways"],
                "fieldname": "year_month",
                "title": "Year and Month Of Update (other_footways)",
            },
            "title": "Year and Month Of Update",
        },
        "other_footways_number_revisions": {
            "function": create_barchart,
            "params": {
                "input_df": updating_dicts["other_footways"],
                "fieldname": "n_revs",
                "title": "Number Of Revisions (other_footways)",
            },
            "title": "Number Of Revisions",
        },
    },
}

global_insertions = {
    "<head>": """

    <head>

    <link rel="stylesheet" href="https://kauevestena.github.io/oswm_codebase/assets/styles/stats_styles.css">
    <script src="https://kauevestena.github.io/oswm_codebase/assets/webscripts/stats_funcs.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">

    
    <title>OSWM Dashboard</title>

    """,
}

global_exclusions = [{"points": ["<style>", "</style>"], "multiline": True}]
