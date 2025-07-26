import geopandas as gpd
from shapely.geometry import Polygon

def get_territory_polygon(city_name, geojson_path, md_path):
    """
    Gets the territory polygon for a given city.

    Args:
        city_name (str): The name of the city.
        geojson_path (str): The path to save the GeoJSON file.
        md_path (str): The path to save the metadata file.
    """
    pass

def save_geoparquet(gdf, path):
    """
    Saves a GeoDataFrame to a GeoParquet file.

    Args:
        gdf (GeoDataFrame): The GeoDataFrame to save.
        path (str): The path to save the file.
    """
    pass

def bbox_geodataframe(bbox):
    """
    Creates a GeoDataFrame from a bounding box.

    Args:
        bbox (list): A list of four coordinates representing the bounding box.

    Returns:
        GeoDataFrame: A GeoDataFrame representing the bounding box.
    """
    return gpd.GeoDataFrame({'geometry': [Polygon([(0, 0), (1, 1), (1, 0)])]})

def dump_json(data, path):
    """
    Dumps data to a JSON file.

    Args:
        data (dict): The data to dump.
        path (str): The path to save the file.
    """
    pass

def merge_list_of_dictionaries(list_of_dicts):
    """
    Merges a list of dictionaries into a single dictionary.

    Args:
        list_of_dicts (list): A list of dictionaries.

    Returns:
        dict: The merged dictionary.
    """
    return {}

def record_datetime(event):
    """
    Records the date and time of an event.

    Args:
        event (str): The name of the event.
    """
    pass

def gen_updating_infotable_page():
    """
    Generates an HTML page with information about the data updating process.
    """
    pass

def get_gdfs_dict(raw_data=False):
    """
    Gets a dictionary of GeoDataFrames.

    Args:
        raw_data (bool, optional): Whether to read the raw data. Defaults to False.

    Returns:
        dict: A dictionary of GeoDataFrames.
    """
    return {"sidewalks": gpd.GeoDataFrame({'geometry': []}), "crossings": gpd.GeoDataFrame({'geometry': []}), "kerbs": gpd.GeoDataFrame({'geometry': []}), "other_footways": gpd.GeoDataFrame({'geometry': []})}

def create_folder_if_not_exists(path):
    """
    Creates a folder if it does not exist.

    Args:
        path (str): The path to the folder.
    """
    pass

def row_query(gdf, query):
    """
    Queries a GeoDataFrame using a row query.

    Args:
        gdf (GeoDataFrame): The GeoDataFrame to query.
        query (dict): The query to apply.

    Returns:
        GeoDataFrame: The queried GeoDataFrame.
    """
    return gdf.iloc[0:0]

def create_date_age(row):
    """
    Calculates the age of a feature based on its revision date.

    Args:
        row (Series): A row of a DataFrame.

    Returns:
        int: The age of the feature in days.
    """
    return 0
