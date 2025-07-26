from constants import *
from oswm_codebase.functions import *
import pandas as pd
import geopandas as gpd
from time import sleep
from shapely import unary_union
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def read_data():
    """Reads the raw data from the geoparquet files.

    Returns:
        dict: A dictionary of GeoDataFrames, with the category as the key.
    """
    logging.info("Reading data.")
    return get_gdfs_dict(raw_data=True)


def get_updating_info():
    """Fetches the updating info from the versioning files.

    Returns:
        dict: A dictionary of DataFrames, with the category as the key.
    """
    logging.info("Fetching updating info.")
    updating_dict = {}
    for category, path in paths_dict["versioning"].items():
        if os.path.exists(path):
            updating_dict[category] = pd.read_json(path)
        else:
            updating_dict[category] = pd.DataFrame()
    return updating_dict


def remove_unconnected_features(gdf, category, sidewalks_buffer, sidewalks_crossings_buffer):
    """Removes unconnected features from the GeoDataFrame.

    Args:
        gdf (GeoDataFrame): The GeoDataFrame to process.
        category (str): The category of the data.
        sidewalks_buffer (Polygon): The buffer around the sidewalks.
        sidewalks_crossings_buffer (Polygon): The buffer around the sidewalks and crossings.

    Returns:
        GeoDataFrame: The processed GeoDataFrame.
    """
    if category in ["sidewalks", "other_footways"]:
        return gdf

    logging.info(f"Removing unconnected features from {category}.")
    create_folder_if_not_exists(disjointed_folderpath)

    buffer = sidewalks_crossings_buffer if category == "kerbs" else sidewalks_buffer
    disjointed = gdf.disjoint(buffer)

    outfilepath = os.path.join(disjointed_folderpath, f"{category}{disjointed_geoms_suffix}{data_format}")
    save_geoparquet(gdf[disjointed], outfilepath)

    return gdf[~disjointed]


def remove_improper_geometries(gdf, category):
    """Removes features with improper geometry types from the GeoDataFrame.

    Args:
        gdf (GeoDataFrame): The GeoDataFrame to process.
        category (str): The category of the data.

    Returns:
        GeoDataFrame: The processed GeoDataFrame.
    """
    logging.info(f"Removing features with improper geometry type from {category}.")
    create_folder_if_not_exists(improper_geoms_folderpath)
    outpath_improper = os.path.join(improper_geoms_folderpath, f"{category}{improper_geoms_suffix}{data_format}")

    proper_geom = gdf.geometry.type.isin(geom_type_dict[category])
    if category != "other_footways":
        save_geoparquet(gdf[~proper_geom], outpath_improper)

    return gdf[proper_geom]


def clean_data(gdf, category):
    """Cleans the data in the GeoDataFrame.

    Args:
        gdf (GeoDataFrame): The GeoDataFrame to process.
        category (str): The category of the data.

    Returns:
        GeoDataFrame: The processed GeoDataFrame.
    """
    logging.info(f"Cleaning data for {category}.")
    gdf = gdf.fillna("?")
    for subkey, replacements in wrong_misspelled_values[category].items():
        gdf.loc[:, subkey] = gdf[subkey].replace(replacements)
    return gdf


def add_update_data(gdf, category, updating_dict):
    """Adds update data to the GeoDataFrame.

    Args:
        gdf (GeoDataFrame): The GeoDataFrame to process.
        category (str): The category of the data.
        updating_dict (dict): A dictionary of DataFrames with the updating info.

    Returns:
        GeoDataFrame: The processed GeoDataFrame.
    """
    logging.info(f"Adding update data to {category}.")
    if not updating_dict[category].empty:
        updating_df = updating_dict[category]
        updating_df["last_update"] = (
            updating_df["rev_day"].astype(str)
            + "-"
            + updating_df["rev_month"].astype(str)
            + "-"
            + updating_df["rev_year"].astype(str)
        )
        updating_df["age"] = updating_df.apply(create_date_age, axis=1)
        updating_df = updating_df.set_index("osmid")
        gdf = gdf.set_index("id").join(updating_df[["last_update", "age", "n_revs"]]).reset_index()
    else:
        gdf["last_update"] = "unavailable"
        gdf["age"] = -1
        gdf["n_revs"] = -1
    return gdf


def split_other_footways(gdf):
    """Splits the 'other_footways' GeoDataFrame into subcategories.

    Args:
        gdf (GeoDataFrame): The 'other_footways' GeoDataFrame.

    Returns:
        GeoDataFrame: The processed 'other_footways' GeoDataFrame with a new
                      'oswm_footway' column.
    """
    logging.info("Splitting Other_Footways into subcategories.")
    gdf[oswm_footway_fieldname] = None
    create_folder_if_not_exists(other_footways_folderpath)

    # Process pedestrian areas
    are_areas = gdf.geometry.type.isin(["Polygon", "MultiPolygon"])
    ped_areas_gdf = gdf[are_areas].copy()
    gdf.loc[are_areas, oswm_footway_fieldname] = pedestrian_areas_layername
    save_geoparquet(
        ped_areas_gdf,
        paths_dict["other_footways_subcategories"]["pedestrian_areas"],
    )

    # Process other subcategories
    other_footways_gdf = gdf[~are_areas].copy()
    for subcategory, query in other_footways_subcatecories.items():
        if subcategory == "pedestrian_areas":
            continue

        belonging = row_query(other_footways_gdf, query)
        belonging_gdf = other_footways_gdf[belonging].copy()
        original_rows = gdf["id"].isin(belonging_gdf["id"])
        gdf.loc[original_rows, oswm_footway_fieldname] = subcategory
        save_geoparquet(
            belonging_gdf, paths_dict["other_footways_subcategories"][subcategory]
        )
        other_footways_gdf = other_footways_gdf[~belonging].copy()

    return gdf


def main():
    """
    Main function for filtering and adapting data.
    """
    gdf_dict = read_data()
    updating_dict = get_updating_info()

    sidewalks_gdf = gdf_dict["sidewalks"]
    crossings_gdf = gdf_dict["crossings"]
    local_utm = sidewalks_gdf.estimate_utm_crs()

    sidewalks_buffer = sidewalks_gdf.to_crs(local_utm).buffer(max_radius_cutoff).to_crs("EPSG:4326").unary_union
    crossings_buffer = crossings_gdf.to_crs(local_utm).buffer(max_radius_cutoff).to_crs("EPSG:4326").unary_union
    sidewalks_crossings_buffer = unary_union([sidewalks_buffer, crossings_buffer])

    raw_data_keys = {}
    for category, curr_gdf in gdf_dict.items():
        logging.info(f"Processing {category}.")

        raw_data_keys[category] = [
            k for k in curr_gdf.keys() if k not in ["geometry", "osmid", "osm_type", "osm_key", "osm_value", "osm_id", "nodes", "element", "id", "ways"]
        ]

        curr_gdf = remove_unconnected_features(curr_gdf, category, sidewalks_buffer, sidewalks_crossings_buffer)
        curr_gdf = remove_improper_geometries(curr_gdf, category)
        curr_gdf = clean_data(curr_gdf, category)
        curr_gdf = add_update_data(curr_gdf, category, updating_dict)

        if category == "other_footways":
            curr_gdf = split_other_footways(curr_gdf)

        save_geoparquet(curr_gdf, f"data/{category}{data_format}")

    dump_json(raw_data_keys, feat_keys_path)

    logging.info("Finishing...")
    record_datetime("Data Pre-Processing")
    sleep(0.1)
    gen_updating_infotable_page()


if __name__ == "__main__":
    main()
