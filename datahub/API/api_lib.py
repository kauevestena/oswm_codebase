import sys

# Ensure the parent `datahub` directory is on sys.path so `dh_lib` can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dh_lib import *


# produtct files or variables that are meant to be provided as API responses:
single_products_index = {
    "boundary_infos": {
        "boundary": "data/boundaries.geojson",
        "boundary_properties": "data/boundary_infos.json",
    },
    "data_quality": {"available_categories": "quality_check/categories.json"},
    "data": {
        "schema": {"included": layer_tags_dict, "excluded": layer_exclusion_tags},
        "metadata": data_layer_descriptions,
    },
}


# variables that

# product folders whose files are meant to be provided as API responses:
product_folders_index = {
    "data": {
        "tiles": tiles_folderpath,
        "vrt": vrts_folderpath,
    },
    "charts": {
        "chart_specifications": "statistics_specs",
    },
    "data_quality": {
        "csv": "quality_check/tables",
        "json": "quality_check/json",
    },
    "data_aging": {
        "versioning": versioning_folderpath,
    },
}
