import os
from datetime import datetime, timezone

from constants import updating_infos_path, paths_dict, layer_tags_dict
from functions import save_geoparquet
import geopandas as gpd
import requests
import pandas as pd

# ---------------------------------------------------------------------------
# OHSOME API Config
# ---------------------------------------------------------------------------

OHSOME_API_BASE = "https://api.ohsome.org/v1"

OHSOME_FILTER_MAP: dict[str, str] = {
    "sidewalks": "footway=sidewalk and type:way",
    "crossings": "footway=crossing and type:way",
    "kerbs": "(barrier=kerb or kerb=*) and type:node",
    "other_footways": (
        "(highway=footway or highway=steps or highway=living_street"
        " or highway=pedestrian or highway=track or highway=path"
        " or foot=yes or foot=designated or foot=permissive or foot=destination"
        " or footway=alley or footway=path or footway=yes) and type:way"
    ),
}

COMBINED_FILTER = (
    "(footway=sidewalk and type:way) or "
    "(footway=crossing and type:way) or "
    "((barrier=kerb or kerb=*) and type:node) or "
    "((highway=footway or highway=steps or highway=living_street or "
    "highway=pedestrian or highway=track or highway=path or "
    "foot=yes or foot=designated or foot=permissive or foot=destination or "
    "footway=alley or footway=path or footway=yes) and type:way)"
)

def get_ohsome_bboxes() -> str:
    # Use get_boundaries_bbox from functions, which returns [miny, minx, maxy, maxx] because resort=True by default
    # But wait, we need minlon,minlat,maxlon,maxlat.
    # Let's write a safe bounding box getter.
    from constants import boundaries_geojson_path
    try:
        gdf = gpd.read_file(boundaries_geojson_path)
        minx, miny, maxx, maxy = gdf.total_bounds
        return f"{minx:.6f},{miny:.6f},{maxx:.6f},{maxy:.6f}"
    except Exception:
        return ""

def _parse_iso_timestamp(ts_str: str) -> datetime | None:
    try:
        val = ts_str.replace("Z", "+00:00")
        if "+" in val:
            dt_part, tz_part = val.split("+")
            if dt_part.count(":") == 1:
                dt_part += ":00"
            val = f"{dt_part}+{tz_part}"
        return datetime.fromisoformat(val)
    except Exception:
        return None

def _ohsome_max_timestamp() -> datetime | None:
    """Fetch the maximum timestamp available in the OHSOME database."""
    try:
        resp = requests.get(f"{OHSOME_API_BASE}/metadata", timeout=10)
        resp.raise_for_status()
        meta = resp.json()
        to_ts = meta.get("extractRegion", {}).get("temporalExtent", {}).get("toTimestamp")
        if to_ts:
            return _parse_iso_timestamp(to_ts)
    except Exception as e:
        print(f"[incremental] Failed to fetch OHSOME metadata: {e}")
    return None


def fetch_incremental_data(start_dt: datetime, end_dt: datetime = None, is_simulation: bool = False):
    """
    Fetches the incremental updates from OHSOME and updates the local parquet files.
    """
    from datetime import timedelta
    
    # Check if OHSOME is lagging behind yesterday
    max_ts = _ohsome_max_timestamp()
    now_dt = datetime.now(tz=timezone.utc)
    yesterday_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    
    if max_ts:
        if max_ts < yesterday_start:
            print(f"[incremental] OHSOME is lagging (temporal extent: {max_ts.isoformat()}, yesterday: {yesterday_start.isoformat()}). Aborting incremental fetch to trigger full download fallback.")
            return False

    if end_dt is None:
        end_dt = min(now_dt, max_ts) if max_ts else now_dt
    elif end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt <= start_dt:
        print("[incremental] No provider watermark newer than the recorded timestamp.")
        return True
        
    bboxes = get_ohsome_bboxes()
    if not bboxes:
        print("[incremental] Cannot find bboxes. Aborting.")
        return False
        
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_param = f"{start_iso},{end_iso}"
    
    url = f"{OHSOME_API_BASE}/contributions/geometry"
    
    pending_updates: dict[str, gpd.GeoDataFrame] = {}
    
    for layer, filter_str in OHSOME_FILTER_MAP.items():
        print(f"[incremental] Updating layer '{layer}' from {start_iso} to {end_iso}...")
        try:
            resp = requests.post(
                url,
                data={
                    "bboxes": bboxes,
                    "filter": filter_str,
                    "time": time_param,
                    "properties": "tags,metadata"
                },
                timeout=120
            )
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                print(f"[incremental] No changes for '{layer}'.")
                continue
                
            print(f"[incremental] Found {len(features)} contributions for '{layer}'.")
            
            # Identify changes
            to_delete_ids = []
            new_features_list = []
            
            for f in features:
                props = f.get("properties", {})
                osm_id_str = props.get("@osmId")
                if not osm_id_str:
                    continue
                
                parts = osm_id_str.split("/")
                if len(parts) != 2:
                    continue
                
                elem_type = parts[0]
                try:
                    num_id = int(parts[1])
                except ValueError:
                    continue
                
                # Check contribution type
                is_del = props.get("@deletion", False)
                is_mod_geom = props.get("@geometryChange", False)
                is_mod_tag = props.get("@tagChange", False)
                is_crea = props.get("@creation", False)
                
                if is_del or is_mod_geom or is_mod_tag:
                    to_delete_ids.append((elem_type, num_id))
                    
                if is_crea or is_mod_geom or is_mod_tag:
                    clean_props = {}
                    for k, v in props.items():
                        if not k.startswith("@"):
                            clean_props[k] = v
                    clean_props["id"] = num_id
                    clean_props["element"] = elem_type
                    
                    new_feat = {
                        "type": "Feature",
                        "geometry": f.get("geometry"),
                        "properties": clean_props
                    }
                    new_features_list.append(new_feat)
                    
            if not is_simulation:
                raw_path = paths_dict["data_raw"][layer]
                if not os.path.exists(raw_path):
                    print(f"[incremental] Required input {raw_path} is missing.")
                    return False
                    
                gdf = gpd.read_parquet(raw_path)
                original_len = len(gdf)
                
                if to_delete_ids:
                    # Filter out rows where (element, id) is in to_delete_ids
                    # We can use a set of tuples for faster lookup
                    to_del_set = set(to_delete_ids)
                    mask = gdf.apply(lambda row: (row.get("element"), row.get("id")) in to_del_set, axis=1)
                    gdf = gdf[~mask]
                    
                if new_features_list:
                    new_gdf = gpd.GeoDataFrame.from_features(new_features_list)
                    new_gdf.crs = "EPSG:4326"
                    if gdf.crs is None:
                        gdf.crs = "EPSG:4326"
                    
                    gdf = gpd.GeoDataFrame(
                        pd.concat([gdf, new_gdf], ignore_index=True),
                        geometry="geometry",
                        crs=gdf.crs or "EPSG:4326",
                    )

                if "element" in gdf.columns and "id" in gdf.columns:
                    gdf = gdf.drop_duplicates(
                        subset=["element", "id"], keep="last"
                    )
                    
                print(f"[incremental] Layer '{layer}': {original_len} -> {len(gdf)} features.")
                pending_updates[layer] = gdf
            else:
                print(f"[incremental] SIMULATION Layer '{layer}': would delete {len(set(to_delete_ids))} elements and append {len(new_features_list)} features.")
            
        except Exception as e:
            print(f"[incremental] Failed to fetch or process incremental data for '{layer}': {e}")
            return False
            
    if not is_simulation:
        try:
            for layer, gdf in pending_updates.items():
                save_geoparquet(gdf, paths_dict["data_raw"][layer])
            from functions import record_datetime
            record_datetime("Data Fetching", value=end_dt)
            print(
                "[incremental] Recorded the successfully applied provider "
                f"watermark {end_dt.isoformat()}."
            )
        except Exception as e:
            print(f"[incremental] Failed to update registry timestamp: {e}")
            return False

    return True

