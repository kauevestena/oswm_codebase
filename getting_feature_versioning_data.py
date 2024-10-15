# from constants import *
from versioning_funcs import *
import geopandas as gpd
import pandas as pd
from tqdm import tqdm
from random import shuffle


"""

    As separate script as long it's really much more slow compared to the other processes...

    This is script was created to store the versioning info of the OSM Features 

"""


# reading as geodataframes:
# sidewalks_gdf = gpd.read_parquet(sidewalks_path)
# crossings_gdf = gpd.read_parquet(crossings_path)
# kerbs_gdf = gpd.read_parquet(kerbs_path)

# gdf_dicts = {
#     'sidewalks':sidewalks_gdf,
#     'crossings':crossings_gdf,
#     'kerbs':kerbs_gdf,
#     }

gdf_dicts = get_gdfs_dict()

# instantiate the object for datetiming:
updates_obj = GetDatetimeLastUpdate()


for category in gdf_dicts:

    data = {
        "osmid": [],
        "rev_day": [],
        "rev_month": [],
        "rev_year": [],
        "n_revs": [],
    }

    data["osmid"] = gdf_dicts[category]["id"]

    print("category: ", category, "\n")

    ids = tuple(gdf_dicts[category]["id"])

    if category != "kerbs":
        # to_include = list(tqdm(map(get_datetime_last_update, ids), total=len(ids)))
        to_include = tuple(
            tqdm(map(updates_obj.get_datetime_last_update_way, ids), total=len(ids))
        )
    else:
        # to_include = list(tqdm(map(get_datetime_last_update_node, ids), total=len(ids)))
        to_include = tuple(
            tqdm(map(updates_obj.get_datetime_last_update_node, ids), total=len(ids))
        )

    data["n_revs"] = [entry[0] for entry in to_include]
    data["rev_day"] = [entry[1] for entry in to_include]
    data["rev_month"] = [entry[2] for entry in to_include]
    data["rev_year"] = [entry[3] for entry in to_include]

    as_df = pd.DataFrame(data)

    # as_df.to_json(f"data/{category}_versioning.json")

    as_df.to_json(paths_dict["versioning"][category])

# to record data aging:
record_datetime("Versioning Data")
sleep(0.1)

# generate the "report" of the updating info
gen_updating_infotable_page()
