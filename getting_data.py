from constants import *
from oswm_codebase.functions import *
from time import sleep, time
import osmnx as ox
import logging
import geopandas as gpd
from oswm_codebase.functions import get_territory_polygon, save_geoparquet, bbox_geodataframe, dump_json, merge_list_of_dictionaries, record_datetime, gen_updating_infotable_page

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_boundary():
    """
    Gets the boundary polygon for the specified city.

    If the boundary file already exists, it is read from the file. Otherwise, it is
    downloaded from OSM and saved to a file. If downloading the polygon fails,
    it falls back to using the bounding box defined in the config.

    Returns:
        tuple: A tuple containing the boundary GeoDataFrame and the boundary polygon.
    """
    if os.path.exists(boundaries_geojson_path):
        logging.info("Boundary file already exists. Reading from file.")
        boundaries_gdf = gpd.read_file(boundaries_geojson_path)
        boundary_polygon = boundaries_gdf["geometry"].iloc[0]
        return boundaries_gdf, boundary_polygon

    try:
        logging.info(f"Downloading boundary polygon for {CITY_NAME}.")
        get_territory_polygon(CITY_NAME, boundaries_geojson_path, boundaries_md_path)
        boundaries_gdf = gpd.read_file(boundaries_geojson_path)
        boundary_polygon = boundaries_gdf["geometry"].iloc[0]

        if boundary_polygon.geom_type not in ["Polygon", "MultiPolygon"]:
            raise ValueError("The downloaded boundary is not a polygon.")

        save_geoparquet(boundaries_gdf, boundaries_path)
        logging.info("Boundary polygon saved to file.")
        return boundaries_gdf, boundary_polygon

    except Exception as e:
        logging.error(f"Failed to download boundary polygon: {e}")
        logging.info("Falling back to bounding box.")
        boundaries_gdf = bbox_geodataframe(BOUNDING_BOX)
        boundaries_gdf.to_file(boundaries_geojson_path)
        save_geoparquet(boundaries_gdf, boundaries_path)
        metadata = {"class": "bounding_box"}
        dump_json(metadata, boundaries_md_path)
        boundary_polygon = boundaries_gdf["geometry"].iloc[0]
        return boundaries_gdf, boundary_polygon


def generate_boundary_infos(boundaries_gdf):
    """
    Generates a JSON file with information about the boundary.

    Args:
        boundaries_gdf (GeoDataFrame): The boundary GeoDataFrame.
    """
    metric_bondary_polygon = boundaries_gdf.to_crs(boundaries_gdf.estimate_utm_crs())[
        "geometry"
    ].iloc[0]

    boundaries_infos = {
        "name": CITY_NAME,
        "area": round(metric_bondary_polygon.area, 3),
        "perimeter": round(metric_bondary_polygon.length, 3),
        "bbox": list(boundaries_gdf["geometry"].iloc[0].bounds),
        "center": list(boundaries_gdf["geometry"].iloc[0].centroid.coords[0]),
    }

    dump_json(boundaries_infos, boundaries_infos_path)
    logging.info("Boundary infos generated.")


def download_data(boundary_polygon):
    """
    Downloads data from OSM for the specified boundary polygon.

    Args:
        boundary_polygon (Polygon): The boundary polygon.

    Returns:
        GeoDataFrame: The downloaded data.
    """
    logging.info("Downloading all data.")
    t1 = time()
    tags = merge_list_of_dictionaries(layer_tags_dict.values())
    as_gdf = ox.features_from_polygon(boundary_polygon, tags)
    logging.info(f"Downloaded {len(as_gdf)} features in {time() - t1:.2f} seconds.")
    return as_gdf


def process_data(as_gdf):
    """
    Processes the downloaded data.

    This includes removing invalid values, converting columns to strings, and
    resetting the index.

    Args:
        as_gdf (GeoDataFrame): The downloaded data.

    Returns:
        GeoDataFrame: The processed data.
    """
    as_gdf = as_gdf[~as_gdf.isin(OTHER_FOOTWAY_EXCLUSION_RULES).any(axis=1)]
    logging.info(f"    now with {len(as_gdf)} features after filtering out with exclusion rules")

    for column in as_gdf.columns:
        if as_gdf[column].dtype == object:
            as_gdf[column] = as_gdf[column].astype(str)

    as_gdf = as_gdf.copy()
    as_gdf.reset_index(inplace=True)
    as_gdf.replace("nan", None, inplace=True)
    as_gdf.rename(columns={"osmid": "id"}, inplace=True)
    return as_gdf


def split_layers(as_gdf):
    """
    Splits the data into different layers and saves them to files.

    Args:
        as_gdf (GeoDataFrame): The data to split.
    """
    logging.info("Splitting layers:")
    for category, tags in layer_tags_dict.items():
        outpath = paths_dict["data_raw"][category]
        belonging = as_gdf.isin(tags).any(axis=1)
        to_save = as_gdf[belonging].copy()
        save_geoparquet(to_save, outpath)
        as_gdf = as_gdf[~belonging]
        logging.info(f"    - {category}: {len(to_save)} features")


def main():
    """
    Main function for getting data.
    """
    boundaries_gdf, boundary_polygon = get_boundary()
    generate_boundary_infos(boundaries_gdf)
    as_gdf = download_data(boundary_polygon)
    as_gdf = process_data(as_gdf)
    split_layers(as_gdf)

    logging.info("Finishing...")
    record_datetime("Data Fetching")
    sleep(0.1)
    gen_updating_infotable_page()


if __name__ == "__main__":
    main()
