from statistics_funcs import *


# to avoid issues with circular imports it was encapsulated in a function:
def get_charts_specs(gdfs_dict):
    return {
        "sidewalks": {
            "sidewalks_smoothness_x_surface": {
                "function": create_double_mat_and_bar,
                "params": {
                    "input_df": gdfs_dict.get("sidewalks"),
                    "title": "Surface x Smoothness (sidewalks)",
                    "xs": "surface",
                    "ys": "smoothness",
                    "scolor": None,
                    "xh": "count()",
                    "yh1": "surface",
                    "yh2": "smoothness",
                    "hcolor": "age",
                    "fontsize": 24,
                },
                "title": "Surface x Smoothness",
            },
            "sidewalks_surface": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("sidewalks"),
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
                    "input_gdf": gdfs_dict.get("sidewalks"),
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
                    "input_gdf": gdfs_dict.get("sidewalks"),
                    "fieldname": "tactile_paving",
                    "title": "Sidewalks Tactile Paving Presence",
                    "str_to_append": " type",
                    "title_fontsize": 24,
                },
                "title": "Tactile Paving Presence",
            },
            "sidewalks_width": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("sidewalks"),
                    "fieldname": "width",
                    "title": "Sidewalks Width Values",
                    "str_to_append": " type",
                    "title_fontsize": 24,
                },
                "title": "Width Values",
            },
            "sidewalks_incline": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("sidewalks"),
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
                    "df": gdfs_dict.get("sidewalks"),
                    "column": "age",
                    "boxplot_title": "Sidewalks Update Age (Years)",
                    "color_field": "smoothness",
                    "height": 200,
                    # "tooltip_fields": ["id"],
                },
                "title": "Update Age",
            },
            "sidewalks_length": {
                "function": create_linked_boxplot_histogram,
                "params": {
                    "df": gdfs_dict.get("sidewalks"),
                    "column": "length(km)",
                    "boxplot_title": "Sidewalks Length (km)",
                    # "tooltip_fields": ["id"],
                    "maxbins": 50,
                },
                "title": "Length (km)",
            },
            "sidewalks_n_revs": {
                "function": create_linked_boxplot_histogram,
                "params": {
                    "df": gdfs_dict.get("sidewalks"),
                    "column": "n_revs",
                    "boxplot_title": "Sidewalks Number of Revisions",
                    "color_field": "smoothness",
                    "height": 200,
                    # "tooltip_fields": ["id"],
                },
                "title": "Number of Revisions",
            },
        },
        "crossings": {
            "crossing_types": {
                "function": create_barchart,
                "params": {
                    "input_df": gdfs_dict.get("crossings"),
                    "fieldname": "crossing",
                    "title": "Crossing Type",
                },
                "title": "Crossing Type",
            },
            "crossing_surface": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("crossings"),
                    "fieldname": "surface",
                    "title": "Crossings Surface Type",
                    "str_to_append": " type",
                    "title_fontsize": 24,
                },
                "title": "Surface Type",
            },
            "crossings_smoothness_x_surface": {
                "function": create_double_mat_and_bar,
                "params": {
                    "input_df": gdfs_dict.get("crossings"),
                    "title": "Surface x Smoothness (crossings)",
                    "xs": "surface",
                    "ys": "smoothness",
                    "scolor": None,
                    "xh": "count()",
                    "yh1": "surface",
                    "yh2": "smoothness",
                    "hcolor": "crossing",
                    "fontsize": 24,
                },
                "title": "Surface x Smoothness",
            },
            "crossings_length": {
                "function": create_linked_boxplot_histogram,
                "params": {
                    "df": gdfs_dict.get("crossings"),
                    "column": "length(km)",
                    "boxplot_title": "Crossings Length (km)",
                    "color_field": "crossing",
                    # "tooltip_fields": ["id"],
                    "maxbins": 50,
                },
                "title": "Length (km)",
            },
            "crossings_age": {
                "function": create_linked_boxplot_histogram,
                "params": {
                    "df": gdfs_dict.get("crossings"),
                    "column": "age",
                    "boxplot_title": "Crossings Update Age (Years)",
                    "color_field": "crossing",
                    "height": 200,
                    # "tooltip_fields": ["id"],
                },
                "title": "Update Age",
            },
            "crossings_n_revs": {
                "function": create_linked_boxplot_histogram,
                "params": {
                    "df": gdfs_dict.get("crossings"),
                    "column": "n_revs",
                    "color_field": "crossing",
                    "height": 200,
                    "boxplot_title": "Crossings Number of Revisions",
                    # "tooltip_fields": ["id"],
                },
                "title": "Number of Revisions",
            },
        },
        "kerbs": {
            "kerbs_x_paving_x_wheelchair": {
                "function": create_double_mat_and_bar,
                "params": {
                    "input_df": gdfs_dict.get("kerbs"),
                    "title": "Kerb x Tactile Paving x Wheelchair Acess.",
                    "xs": "kerb",
                    "ys": "tactile_paving",
                    "scolor": None,
                    "xh": "count()",
                    "yh1": "kerb",
                    "yh2": "tactile_paving",
                    "hcolor": "wheelchair",
                    "fontsize": 24,
                },
                "title": "Surface x Smoothness",
            },
            "kerb_types": {
                "function": create_barchart,
                "params": {
                    "input_df": gdfs_dict.get("kerbs"),
                    "fieldname": "kerb",
                    "title": "Kerb Type",
                },
                "title": "Kerb Type",
            },
            "kerb_tactile_paving": {
                "function": create_barchart,
                "params": {
                    "input_df": gdfs_dict.get("kerbs"),
                    "fieldname": "tactile_paving",
                    "title": "Kerb Tactile Paving Presence",
                },
                "title": "Tactile Paving Presence",
            },
            "kerb_wheelchair_access": {
                "function": create_barchart,
                "params": {
                    "input_df": gdfs_dict.get("kerbs"),
                    "fieldname": "wheelchair",
                    "title": "Kerb Wheelchair Acessibility",
                },
                "title": "Wheelchair Acessibility",
            },
            "kerbs_surface": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("kerbs"),
                    "fieldname": "surface",
                    "title": "Kerbs Surface Type",
                    "str_to_append": " type",
                    "title_fontsize": 24,
                    "len_field": None,
                },
                "title": "Surface Type",
            },
            "kerbs_age": {
                "function": create_linked_boxplot_histogram,
                "params": {
                    "df": gdfs_dict.get("kerbs"),
                    "column": "age",
                    "boxplot_title": "Kerbs Update Age (Years)",
                    # "tooltip_fields": ["id"],
                    "color_field": "wheelchair",
                    "height": 200,
                },
                "title": "Update Age",
            },
            "kerbs_n_revs": {
                "function": create_linked_boxplot_histogram,
                "params": {
                    "df": gdfs_dict.get("kerbs"),
                    "column": "n_revs",
                    "boxplot_title": "Kerbs Number of Revisions",
                    "color_field": "smoothness",
                    "height": 200,
                    # "tooltip_fields": ["id"],
                },
                "title": "Number of Revisions",
            },
        },
        "other_footways": {
            "other_footways_subcategory": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("other_footways"),
                    "fieldname": oswm_footway_fieldname,
                    "title": "Sub-category (Layer)",
                },
                "title": "Subcategory",
            },
            "other_footways_smoothness_x_surface": {
                "function": create_double_mat_and_bar,
                "params": {
                    "input_df": gdfs_dict.get("other_footways"),
                    "title": "Surface x Smoothness (other_footways)",
                    "xs": "surface",
                    "ys": "smoothness",
                    "scolor": oswm_footway_fieldname,
                    "xh": "count()",
                    "yh1": "surface",
                    "yh2": "smoothness",
                    "hcolor": oswm_footway_fieldname,
                    "fontsize": 24,
                },
                "title": "Surface x Smoothness",
            },
            "other_footways_surface": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("other_footways"),
                    "fieldname": "surface",
                    "title": "Other Footways Surface Type",
                    "str_to_append": " type",
                    "title_fontsize": 24,
                },
                "title": "Surface Type",
            },
            "other_footways_smoothness": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("other_footways"),
                    "fieldname": "smoothness",
                    "title": "Other Footways Smoothness",
                    "str_to_append": " type",
                    "title_fontsize": 24,
                },
                "title": "Smoothness",
            },
            "other_footways_length": {
                "function": create_linked_boxplot_histogram,
                "params": {
                    "df": gdfs_dict.get("other_footways"),
                    "column": "length(km)",
                    "boxplot_title": "Other Footways Length (km)",
                    "color_field": oswm_footway_fieldname,
                    "height": 200,
                    # "tooltip_fields": ["id"],
                    "maxbins": 50,
                },
                "title": "Length (km)",
            },
            "other_footways_age": {
                "function": create_linked_boxplot_histogram,
                "params": {
                    "df": gdfs_dict.get("other_footways"),
                    "column": "age",
                    "boxplot_title": "Other Footways Update Age (Years)",
                    "color_field": oswm_footway_fieldname,
                    "height": 200,
                },
                "title": "Update Age",
            },
            "other_footways_n_revs": {
                "function": create_linked_boxplot_histogram,
                "params": {
                    "df": gdfs_dict.get("other_footways"),
                    "column": "n_revs",
                    "boxplot_title": "Other Footways Number of Revisions",
                    "color_field": oswm_footway_fieldname,
                    "height": 200,
                    # "tooltip_fields": ["id"],
                },
                "title": "Number of Revisions",
            },
        },
        "all_data": {
            "all_data_category": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("all_data"),
                    "fieldname": "category",
                    "title": "All-Category Layers Feature Count",
                    "str_to_append": " type",
                    "title_fontsize": 24,
                    "len_field": None,  # it works for count
                    "color_field": "length(km)",
                    "filter_out_opt": None,
                    # "excluding_categories": ["kerbs"],  # include "pedestrian_areas" ?
                    # TODO:
                },
                "title": "Layer Feature Count",
            },
            "all_data_surface": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("all_data"),
                    "fieldname": "surface",
                    "title": "All-Category Surface Type",
                    "str_to_append": " type",
                    "title_fontsize": 24,
                },
                "title": "Surface Type",
            },
            "all_data_smoothness": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("all_data"),
                    "fieldname": "smoothness",
                    "title": "All-Category Smoothness Condition",
                    "str_to_append": " type",
                    "title_fontsize": 24,
                },
                "title": "Smoothness Condition",
            },
            "all_data_tactile_paving": {
                "function": create_barchartV2,
                "params": {
                    "input_gdf": gdfs_dict.get("all_data"),
                    "fieldname": "tactile_paving",
                    "title": "All-Category Tactile Paving Presence",
                    "str_to_append": " type",
                    "title_fontsize": 24,
                },
                "title": "Tactile Paving Presence",
            },
        },
    }
