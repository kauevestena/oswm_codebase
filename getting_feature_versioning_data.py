# from constants import *
from versioning_funcs import *
import geopandas as gpd
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import osmapi


"""

    This script stores the versioning info of the OSM Features.

    Uses batch API calls (WaysGet/NodesGet) with parallel execution
    for dramatically faster fetching (~100x vs sequential single calls).

"""

# --- Configuration ---
BATCH_SIZE = 200   # IDs per batch API request
MAX_WORKERS = 4   # concurrent batch requests

# default return for failed lookups
_DEFAULT_RET = GetDatetimeLastUpdate.default_return


def _parse_result(data):
    """Extract versioning tuple from a single API result dict."""
    if data and "timestamp" in data:
        dt = data["timestamp"]
        return (data["version"], dt.day, dt.month, dt.year)
    return _DEFAULT_RET


def _fetch_batch(ids_batch, is_node=False):
    """Fetch a batch of features using the multi-fetch OSM API endpoint."""
    api = osmapi.OsmApi()
    results = {}
    try:
        fetched = api.NodesGet(ids_batch) if is_node else api.WaysGet(ids_batch)
        for fid in ids_batch:
            results[fid] = _parse_result(fetched.get(fid))
    except Exception:
        # Fallback: individual fetches for the failed batch
        fetch_func = api.NodeGet if is_node else api.WayGet
        for fid in ids_batch:
            try:
                results[fid] = _parse_result(fetch_func(fid))
            except Exception:
                results[fid] = _DEFAULT_RET
    return results


def fetch_all_versioning(ids, is_node=False):
    """Fetch versioning data for all IDs using parallel batch requests."""
    ids_list = list(ids)
    batches = [ids_list[i : i + BATCH_SIZE] for i in range(0, len(ids_list), BATCH_SIZE)]

    all_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_batch, batch, is_node): batch
            for batch in batches
        }
        with tqdm(total=len(ids_list), desc="Features") as pbar:
            for future in as_completed(futures):
                batch_results = future.result()
                all_results.update(batch_results)
                pbar.update(len(batch_results))

    # preserve original order
    return [all_results.get(fid, _DEFAULT_RET) for fid in ids_list]


# --- Main ---
gdf_dicts = get_gdfs_dict()

for category in gdf_dicts:
    print(f"\ncategory: {category}")

    ids = list(gdf_dicts[category]["id"])
    is_node = category == "kerbs"

    results = fetch_all_versioning(ids, is_node)

    data = {
        "osmid": ids,
        "n_revs": [r[0] for r in results],
        "rev_day": [r[1] for r in results],
        "rev_month": [r[2] for r in results],
        "rev_year": [r[3] for r in results],
    }

    pd.DataFrame(data).to_json(paths_dict["versioning"][category])

# to record data aging:
record_datetime("Versioning Data")
sleep(0.1)

# generate the "report" of the updating info
gen_updating_infotable_page()
