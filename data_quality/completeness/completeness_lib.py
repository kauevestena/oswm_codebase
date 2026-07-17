"""
Completeness analysis library for OSWM.

Hybrid approach:
- Current month: local GeoParquet data + OSMnx roads (fully offline)
- Historical months: OHSOME API at Z15, disaggregated to Z17 offline

Query Z15 once, disaggregate to Z17, aggregate upward to Z12.
"""

import os
import sys
import time
import json
from datetime import datetime, timezone, timedelta

import mercantile
import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box
from tqdm import tqdm

# Setup path for project imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from functions import get_boundaries_infos, create_folder_if_not_exists, dump_json
from constants import (
    CITY_NAME,
    boundaries_geojson_path,
    sidewalks_path,
    processed_folderpath,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_ZOOM = 12
MAX_ZOOM = 17
QUERY_ZOOM = 15  # Primary computation zoom

OHSOME_API_BASE = "https://api.ohsome.org/v1"
OHSOME_FILTERS = {
    "roads": (
        "(highway in (motorway, trunk, primary, secondary, tertiary, "
        "residential, unclassified, motorway_link, trunk_link, primary_link, "
        "secondary_link, tertiary_link)) and type:way"
    ),
    "footways": "highway=footway and type:way",
    "sidewalks": "footway=sidewalk and type:way",
}

OHSOME_BATCH_SIZE = 50
MAX_RETRIES = 3
RETRY_DELAY = 5

ROADS_CACHE_PATH = os.path.join(processed_folderpath, "roads_for_completeness.parquet")

ROAD_HIGHWAY_TYPES = [
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "residential", "unclassified",
    "motorway_link", "trunk_link", "primary_link",
    "secondary_link", "tertiary_link",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def fetch_or_load_roads(bounds, cache_path=ROADS_CACHE_PATH, silent=False):
    """Load roads from cache or fetch via OSMnx."""
    if os.path.exists(cache_path):
        if not silent:
            print("[completeness] Loading cached road network...")
        return gpd.read_parquet(cache_path)

    if not silent:
        print("[completeness] Fetching road network via OSMnx (one-time download)...")

    import osmnx as ox

    # osmnx v2: bbox = (left, bottom, right, top) = (west, south, east, north)
    tags = {"highway": ROAD_HIGHWAY_TYPES}
    roads = ox.features_from_bbox(bbox=(bounds[0], bounds[1], bounds[2], bounds[3]), tags=tags)

    # Keep only line geometries
    roads = roads[roads.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    roads = roads[["geometry"]].copy()
    roads = roads.reset_index(drop=True)

    create_folder_if_not_exists(os.path.dirname(cache_path))
    roads.to_parquet(cache_path)

    if not silent:
        print(f"[completeness] Cached {len(roads)} road features to {cache_path}")

    return roads


def load_pedestrian_layers(silent=False):
    """
    Load pedestrian data layers from local GeoParquet.

    Returns dict: {"footways": GeoDataFrame, "sidewalks": GeoDataFrame}
    """
    if not silent:
        print("[completeness] Loading pedestrian layers from GeoParquet...")

    sidewalks = gpd.read_parquet(sidewalks_path)

    # Footways = ALL highway=footway (sidewalks + non-sidewalk footways)
    main_fw_path = os.path.join(
        processed_folderpath, "other_footways", "main_footways.parquet"
    )
    if os.path.exists(main_fw_path):
        main_fw = gpd.read_parquet(main_fw_path)
        fw_only = main_fw[main_fw.get("highway") == "footway"]
        footways = pd.concat(
            [sidewalks[["geometry"]], fw_only[["geometry"]]], ignore_index=True
        )
        footways = gpd.GeoDataFrame(footways, crs=sidewalks.crs)
    else:
        footways = sidewalks[["geometry"]].copy()

    if not silent:
        print(f"[completeness]   Sidewalks: {len(sidewalks)} features")
        print(f"[completeness]   Footways:  {len(footways)} features")

    return {
        "footways": footways[["geometry"]],
        "sidewalks": sidewalks[["geometry"]],
    }


# ---------------------------------------------------------------------------
# Tile grid utilities
# ---------------------------------------------------------------------------

def _build_tile_grid(bounds, zoom):
    """Build a GeoDataFrame of tile polygons at the given zoom level."""
    rows = []
    for tile in mercantile.tiles(bounds[0], bounds[1], bounds[2], bounds[3], zooms=zoom):
        tb = mercantile.bounds(tile)
        rows.append({
            "tile_id": f"{tile.z}/{tile.x}/{tile.y}",
            "geometry": box(tb.west, tb.south, tb.east, tb.north),
        })
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def generate_tile_bboxes(bounds, zoom):
    """Dict mapping tile_id -> 'w,s,e,n' string (for OHSOME compat)."""
    d = {}
    for tile in mercantile.tiles(bounds[0], bounds[1], bounds[2], bounds[3], zooms=zoom):
        tb = mercantile.bounds(tile)
        d[f"{tile.z}/{tile.x}/{tile.y}"] = f"{tb.west},{tb.south},{tb.east},{tb.north}"
    return d


def _tile_id_parts(tile_id):
    """Parse 'z/x/y' into mercantile.Tile."""
    z, x, y = [int(v) for v in tile_id.split("/")]
    return mercantile.Tile(x, y, z)


def _get_children_at_zoom(tile_id, target_zoom):
    """Get all descendant tile IDs at target_zoom from a parent tile."""
    tile = _tile_id_parts(tile_id)
    current_z = tile.z
    if target_zoom <= current_z:
        return [tile_id]

    tiles = [tile]
    for _ in range(target_zoom - current_z):
        next_tiles = []
        for t in tiles:
            next_tiles.extend(mercantile.children(t))
        tiles = next_tiles
    return [f"{t.z}/{t.x}/{t.y}" for t in tiles]


# ---------------------------------------------------------------------------
# Local length computation
# ---------------------------------------------------------------------------

def compute_clipped_lengths_z15(gdf, tile_grid_z15, utm_crs, label="", silent=False):
    """
    Compute total length of features within each Z15 tile.
    Uses spatial join + clip for accuracy.
    Returns dict {tile_id: length_meters}.
    """
    if gdf.empty:
        return {row["tile_id"]: 0.0 for _, row in tile_grid_z15.iterrows()}

    results = {}
    gdf_reset = gdf.reset_index(drop=True)

    # Spatial join: find candidate features per tile
    joined = gpd.sjoin(
        gdf_reset,
        tile_grid_z15,
        how="inner",
        predicate="intersects",
    )

    # Build tile_id -> geometry lookup
    tile_geom_lookup = dict(zip(tile_grid_z15["tile_id"], tile_grid_z15["geometry"]))

    grouped = joined.groupby("tile_id")

    for tile_id in tqdm(
        tile_grid_z15["tile_id"], desc=f"  Z15 tiles ({label})", leave=False, disable=silent
    ):
        if tile_id not in grouped.groups:
            results[tile_id] = 0.0
            continue

        feat_indices = joined.loc[grouped.groups[tile_id]].index.unique()
        subset = gdf_reset.loc[feat_indices]
        tile_geom = tile_geom_lookup[tile_id]

        clipped = gpd.clip(subset, tile_geom)
        if clipped.empty:
            results[tile_id] = 0.0
        else:
            results[tile_id] = float(clipped.to_crs(utm_crs).length.sum())

    return results


def disaggregate_z15_to_children(
    gdf, z15_lengths, tile_grid_z15, target_zoom, utm_crs, label="", silent=False
):
    """
    Disaggregate Z15 lengths to finer zoom by clipping features within
    each Z15 parent tile to its child tiles at target_zoom.

    Returns dict {child_tile_id: length_meters} for the target zoom.
    """
    results = {}

    # Pre-join features to Z15 tiles
    if gdf.empty:
        for _, row in tile_grid_z15.iterrows():
            for child_id in _get_children_at_zoom(row["tile_id"], target_zoom):
                results[child_id] = 0.0
        return results

    gdf_reset = gdf.reset_index(drop=True)
    joined = gpd.sjoin(
        gdf_reset,
        tile_grid_z15,
        how="inner",
        predicate="intersects",
    )
    grouped = joined.groupby("tile_id")

    z15_iter = tqdm(
        tile_grid_z15["tile_id"],
        desc=f"  Disaggregate→Z{target_zoom} ({label})",
        leave=False,
        disable=silent,
    )

    for z15_tid in z15_iter:
        child_ids = _get_children_at_zoom(z15_tid, target_zoom)

        # If parent has zero length, all children are zero
        if z15_lengths.get(z15_tid, 0.0) == 0.0:
            for cid in child_ids:
                results[cid] = 0.0
            continue

        # Get features in this Z15 tile
        if z15_tid not in grouped.groups:
            for cid in child_ids:
                results[cid] = 0.0
            continue

        feat_indices = joined.loc[grouped.groups[z15_tid]].index.unique()
        subset = gdf_reset.loc[feat_indices]

        # Clip each child tile
        for cid in child_ids:
            child_tile = _tile_id_parts(cid)
            cb = mercantile.bounds(child_tile)
            child_box = box(cb.west, cb.south, cb.east, cb.north)
            clipped = gpd.clip(subset, child_box)

            if clipped.empty:
                results[cid] = 0.0
            else:
                results[cid] = float(clipped.to_crs(utm_crs).length.sum())

    return results


def aggregate_upward(z_lengths, bounds, source_zoom, target_zoom):
    """
    Aggregate lengths from source_zoom to target_zoom (coarser).
    Returns dict of dicts: {zoom_str: {tile_id: length}}.
    """
    all_lengths = {str(source_zoom): z_lengths}

    for z in range(source_zoom - 1, target_zoom - 1, -1):
        parent_lengths = {}
        bboxes = generate_tile_bboxes(bounds, z)

        for tile_id in bboxes:
            tile = _tile_id_parts(tile_id)
            children = mercantile.children(tile)
            total = 0.0
            child_zoom = str(z + 1)
            for child in children:
                cid = f"{child.z}/{child.x}/{child.y}"
                total += all_lengths.get(child_zoom, {}).get(cid, 0.0)
            parent_lengths[tile_id] = total

        all_lengths[str(z)] = parent_lengths

    return all_lengths


# ---------------------------------------------------------------------------
# OHSOME querying at Z15
# ---------------------------------------------------------------------------

def _batch_bboxes(bboxes_dict, batch_size=OHSOME_BATCH_SIZE):
    items = list(bboxes_dict.items())
    for i in range(0, len(items), batch_size):
        yield dict(items[i : i + batch_size])


def query_ohsome_z15(bboxes_z15, filter_str, timestamp, silent=False):
    """Query OHSOME at Z15 for a single timestamp. Returns {tile_id: length}."""
    results = {}
    url = f"{OHSOME_API_BASE}/elements/length/groupBy/boundary"

    batches = list(_batch_bboxes(bboxes_z15))
    for batch in tqdm(batches, desc="    OHSOME batches", leave=False, disable=silent):
        bboxes_param = "|".join(f"{tid}:{bbox}" for tid, bbox in batch.items())
        params = {
            "bboxes": bboxes_param,
            "filter": filter_str,
            "format": "json",
            "time": timestamp,
        }

        data = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.post(url, data=params, timeout=120)
                resp.raise_for_status()
                data = resp.json()
                break
            except (requests.RequestException, ValueError) as e:
                if hasattr(e, "response") and e.response is not None and e.response.status_code == 404:
                    if not silent:
                        tqdm.write(f"    [ohsome] 404: ts={timestamp} out of bounds")
                    break
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (2 ** attempt)
                    if not silent:
                        tqdm.write(f"    [ohsome] Retry {attempt+1}/{MAX_RETRIES} after {wait}s: {e}")
                    time.sleep(wait)
                else:
                    if not silent:
                        tqdm.write(f"    [ohsome] Failed after {MAX_RETRIES} attempts: {e}")

        if data is None:
            for tid in batch:
                results[tid] = 0.0
            continue

        for group in data.get("groupByResult", []):
            tid = group.get("groupByObject", "")
            entries = group.get("result", [])
            results[tid] = entries[-1].get("value", 0.0) if entries else 0.0

        time.sleep(0.3)

    # Fill missing
    for tid in bboxes_z15:
        if tid not in results:
            results[tid] = 0.0

    return results


def ohsome_disaggregate_z15_to_z17(z15_lengths, local_z17_lengths, bounds):
    """
    Distribute OHSOME Z15 lengths to Z17 using local geometry proportions.

    For each Z15 tile, the total length is distributed among its Z17 children
    proportionally to the local (current) Z17 lengths. If local lengths are
    all zero, distribute uniformly.
    """
    z15_bboxes = generate_tile_bboxes(bounds, QUERY_ZOOM)
    result = {}

    for z15_tid in z15_bboxes:
        z17_children = _get_children_at_zoom(z15_tid, MAX_ZOOM)
        ohsome_total = z15_lengths.get(z15_tid, 0.0)

        if ohsome_total == 0.0:
            for cid in z17_children:
                result[cid] = 0.0
            continue

        # Get local proportions
        local_vals = [local_z17_lengths.get(cid, 0.0) for cid in z17_children]
        local_total = sum(local_vals)

        if local_total > 0:
            for cid, lv in zip(z17_children, local_vals):
                result[cid] = ohsome_total * (lv / local_total)
        else:
            # Uniform distribution
            share = ohsome_total / len(z17_children)
            for cid in z17_children:
                result[cid] = share

    return result


# ---------------------------------------------------------------------------
# Timestamp generation
# ---------------------------------------------------------------------------

def generate_kickstart_timestamps(n_months=3):
    """Generate N prior month-start timestamps for OHSOME kickstart."""
    now = datetime.now(tz=timezone.utc)
    timestamps = []
    for i in range(n_months, 0, -1):
        dt = now.replace(day=1) - timedelta(days=i * 30)
        first_of_month = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ts = first_of_month.strftime("%Y-%m-%d")
        if ts not in timestamps:
            timestamps.append(ts)
    return timestamps


def get_next_historical_timestamp(existing_timestamps):
    """Get the month before the earliest existing timestamp."""
    if not existing_timestamps:
        return None
    earliest = min(existing_timestamps)
    dt = datetime.strptime(earliest, "%Y-%m-%d")
    # Go to previous month's 1st
    first_of_prev = (dt.replace(day=1) - timedelta(days=1)).replace(day=1)
    return first_of_prev.strftime("%Y-%m-%d")


def get_current_timestamp():
    """Get today's date as timestamp string."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Result structure building
# ---------------------------------------------------------------------------

def _init_results_structure(bounds, timestamps):
    """Initialize the JSON results structure with empty tile grids."""
    results = {
        "metadata": {
            "city": CITY_NAME,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "bounds": bounds,
            "method": "hybrid_local_ohsome",
        },
        "timestamps": sorted(timestamps),
        "zoom_levels": {},
    }

    for z in range(MIN_ZOOM, MAX_ZOOM + 1):
        bboxes = generate_tile_bboxes(bounds, z)
        zoom_data = {"tiles": {}}
        for tile_id, bbox_str in bboxes.items():
            w, s, e, n = [float(v) for v in bbox_str.split(",")]
            zoom_data["tiles"][tile_id] = {
                "bbox": [w, s, e, n],
                "center": [(w + e) / 2, (s + n) / 2],
                "data": [],
            }
        results["zoom_levels"][str(z)] = zoom_data

    return results


def _add_timestamp_data(results, timestamp, z17_roads, z17_footways, z17_sidewalks, bounds):
    """
    Add one timestamp's worth of data to the results structure.
    Computes ratios at Z17, then aggregates upward.
    """
    # Build per-layer aggregation for all zoom levels
    roads_all = aggregate_upward(z17_roads, bounds, MAX_ZOOM, MIN_ZOOM)
    foots_all = aggregate_upward(z17_footways, bounds, MAX_ZOOM, MIN_ZOOM)
    sides_all = aggregate_upward(z17_sidewalks, bounds, MAX_ZOOM, MIN_ZOOM)

    for z in range(MIN_ZOOM, MAX_ZOOM + 1):
        z_str = str(z)
        roads_z = roads_all.get(z_str, {})
        foots_z = foots_all.get(z_str, {})
        sides_z = sides_all.get(z_str, {})

        for tile_id in results["zoom_levels"][z_str]["tiles"]:
            road_len = roads_z.get(tile_id, 0.0)
            foot_len = foots_z.get(tile_id, 0.0)
            side_len = sides_z.get(tile_id, 0.0)

            fr = (foot_len / road_len) if road_len > 0 else None
            sr = (side_len / road_len) if road_len > 0 else None

            results["zoom_levels"][z_str]["tiles"][tile_id]["data"].append({
                "timestamp": timestamp,
                "road_length": round(road_len, 1),
                "footway_length": round(foot_len, 1),
                "sidewalk_length": round(side_len, 1),
                "footway_ratio": round(fr, 4) if fr is not None else None,
                "sidewalk_ratio": round(sr, 4) if sr is not None else None,
            })


# ---------------------------------------------------------------------------
# Main analysis entry points
# ---------------------------------------------------------------------------

def compute_local_snapshot(bounds, silent=False):
    """
    Compute current lengths using local data.
    Returns (z17_roads, z17_footways, z17_sidewalks) dicts.
    """
    roads = fetch_or_load_roads(bounds, silent=silent)
    ped = load_pedestrian_layers(silent=silent)
    utm_crs = roads.estimate_utm_crs()

    if not silent:
        print(f"[completeness] UTM CRS: {utm_crs}")

    tile_grid_z15 = _build_tile_grid(bounds, QUERY_ZOOM)
    if not silent:
        print(f"[completeness] Z{QUERY_ZOOM} grid: {len(tile_grid_z15)} tiles")

    # Step 1: Compute at Z15
    if not silent:
        print(f"\n[completeness] Step 1: Computing lengths at Z{QUERY_ZOOM}...")

    layers = {"roads": roads, "footways": ped["footways"], "sidewalks": ped["sidewalks"]}
    z15 = {}
    for name, gdf in layers.items():
        if not silent:
            print(f"[completeness]   Layer: {name} ({len(gdf)} features)")
        z15[name] = compute_clipped_lengths_z15(gdf, tile_grid_z15, utm_crs, label=name, silent=silent)

    # Step 2: Disaggregate Z15 → Z17
    if not silent:
        print(f"\n[completeness] Step 2: Disaggregating Z{QUERY_ZOOM} → Z{MAX_ZOOM}...")

    z17 = {}
    for name, gdf in layers.items():
        z17[name] = disaggregate_z15_to_children(
            gdf, z15[name], tile_grid_z15, MAX_ZOOM, utm_crs, label=name, silent=silent
        )

    return z17["roads"], z17["footways"], z17["sidewalks"]


def compute_ohsome_historical(bounds, timestamps, local_z17, silent=False):
    """
    Compute historical lengths using OHSOME at Z15, disaggregated to Z17
    using local geometry proportions.

    local_z17: dict {layer_name: {tile_id: length}} from local snapshot.
    Returns list of (timestamp, z17_roads, z17_footways, z17_sidewalks).
    """
    bboxes_z15 = generate_tile_bboxes(bounds, QUERY_ZOOM)
    layer_names = ["roads", "footways", "sidewalks"]

    results_list = []

    ts_iter = tqdm(timestamps, desc="OHSOME timestamps", leave=False, disable=silent)
    for ts in ts_iter:
        ts_iter.set_postfix({"ts": ts})

        z15_lengths = {}
        layer_iter = tqdm(
            zip(layer_names, [OHSOME_FILTERS[n] for n in layer_names]),
            total=len(layer_names),
            desc="  Layers",
            leave=False,
            disable=silent,
        )
        for lname, filt in layer_iter:
            layer_iter.set_postfix({"layer": lname})
            z15_lengths[lname] = query_ohsome_z15(bboxes_z15, filt, ts, silent=silent)

        # Disaggregate each layer's Z15 → Z17 using local proportions
        z17_ts = {}
        for lname in layer_names:
            z17_ts[lname] = ohsome_disaggregate_z15_to_z17(
                z15_lengths[lname], local_z17[lname], bounds
            )

        results_list.append((ts, z17_ts["roads"], z17_ts["footways"], z17_ts["sidewalks"]))

    return results_list


def run_completeness_analysis(
    bounds,
    existing_data=None,
    silent=False,
):
    """
    Main entry point for the completeness analysis.

    If existing_data is None (first run):
      - OHSOME kickstart for 3 prior months
      - Local snapshot for current month

    If existing_data is provided (incremental):
      - Local snapshot for current month
      - OHSOME for one more historical month
    """
    current_ts = get_current_timestamp()

    # Step 1: Local snapshot (always)
    if not silent:
        print("=" * 60)
        print("[completeness] Computing local snapshot...")
        print("=" * 60)

    z17_roads, z17_footways, z17_sidewalks = compute_local_snapshot(bounds, silent=silent)
    local_z17 = {"roads": z17_roads, "footways": z17_footways, "sidewalks": z17_sidewalks}

    # Step 2: Determine OHSOME timestamps
    if existing_data is None:
        # First run: kickstart with 3 prior months
        ohsome_timestamps = generate_kickstart_timestamps(n_months=3)
        all_timestamps = ohsome_timestamps + [current_ts]
    else:
        existing_ts = existing_data.get("timestamps", [])
        all_timestamps = list(existing_ts)
        if current_ts not in all_timestamps:
            all_timestamps.append(current_ts)
        # Extend one month backwards
        next_hist = get_next_historical_timestamp(existing_ts)
        if next_hist and next_hist not in all_timestamps:
            ohsome_timestamps = [next_hist]
            all_timestamps.append(next_hist)
        else:
            ohsome_timestamps = []

    all_timestamps = sorted(set(all_timestamps))

    if not silent:
        print(f"\n[completeness] All timestamps: {all_timestamps}")
        print(f"[completeness] OHSOME timestamps: {ohsome_timestamps if existing_data is None or ohsome_timestamps else 'kickstart: ' + str(ohsome_timestamps)}")

    # Step 3: Query OHSOME for historical timestamps
    ohsome_results = []
    if ohsome_timestamps:
        if not silent:
            print("\n" + "=" * 60)
            print(f"[completeness] Querying OHSOME for {len(ohsome_timestamps)} historical timestamp(s)...")
            print("=" * 60)
        ohsome_results = compute_ohsome_historical(
            bounds, ohsome_timestamps, local_z17, silent=silent
        )

    # Step 4: Build results structure
    if not silent:
        print("\n[completeness] Building results...")

    results = _init_results_structure(bounds, all_timestamps)

    # Add OHSOME historical data
    for ts, z17_r, z17_f, z17_s in ohsome_results:
        _add_timestamp_data(results, ts, z17_r, z17_f, z17_s, bounds)

    # Add local current snapshot
    _add_timestamp_data(results, current_ts, z17_roads, z17_footways, z17_sidewalks, bounds)

    # If merging, carry forward existing data for timestamps we didn't recompute
    if existing_data:
        recomputed_ts = set([current_ts] + ohsome_timestamps)
        for ts in existing_ts:
            if ts not in recomputed_ts:
                # Copy data from existing
                for z_str in results["zoom_levels"]:
                    for tid in results["zoom_levels"][z_str]["tiles"]:
                        old_tile = existing_data["zoom_levels"].get(z_str, {}).get("tiles", {}).get(tid, {})
                        old_entries = old_tile.get("data", [])
                        entry = next((d for d in old_entries if d["timestamp"] == ts), None)
                        if entry:
                            results["zoom_levels"][z_str]["tiles"][tid]["data"].append(entry)

    # Sort all data entries by timestamp
    for z_str in results["zoom_levels"]:
        for tid in results["zoom_levels"][z_str]["tiles"]:
            results["zoom_levels"][z_str]["tiles"][tid]["data"].sort(
                key=lambda d: d["timestamp"]
            )

    return results


# ---------------------------------------------------------------------------
# Map generation
# ---------------------------------------------------------------------------

def generate_completeness_map(data, output_dir, silent=False):
    """
    Generate a standalone MapLibre GL JS choropleth map.

    Outputs index.html at output_dir/index.html.
    """
    create_folder_if_not_exists(output_dir)

    # Build GeoJSON features for each zoom level
    # We use the last timestamp's data for the initial view
    timestamps = data.get("timestamps", [])
    all_features = []

    for zoom_str, zoom_data in data["zoom_levels"].items():
        zoom = int(zoom_str)
        for tile_id, tile_info in zoom_data["tiles"].items():
            bbox = tile_info["bbox"]
            west, south, east, north = bbox

            coords = [
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]

            # Flatten all timestamp data into properties
            props = {
                "tile_id": tile_id,
                "zoom": zoom,
            }

            for i, entry in enumerate(tile_info.get("data", [])):
                suffix = f"_t{i}"
                props[f"road_length{suffix}"] = entry.get("road_length", 0)
                props[f"footway_length{suffix}"] = entry.get("footway_length", 0)
                props[f"sidewalk_length{suffix}"] = entry.get("sidewalk_length", 0)
                props[f"footway_ratio{suffix}"] = entry.get("footway_ratio")
                props[f"sidewalk_ratio{suffix}"] = entry.get("sidewalk_ratio")

            feature = {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": props,
            }
            all_features.append(feature)

    geojson = {"type": "FeatureCollection", "features": all_features}

    # Get map center from metadata
    bounds_meta = data["metadata"]["bounds"]
    center_lon = (bounds_meta[0] + bounds_meta[2]) / 2
    center_lat = (bounds_meta[1] + bounds_meta[3]) / 2
    city_name = data["metadata"].get("city", "City")

    timestamp_labels_js = json.dumps(timestamps)

    html = _build_map_html(
        geojson_str=json.dumps(geojson),
        center_lon=center_lon,
        center_lat=center_lat,
        city_name=city_name,
        timestamps_js=timestamp_labels_js,
        n_timestamps=len(timestamps),
    )

    outpath = os.path.join(output_dir, "index.html")
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)

    if not silent:
        print(f"[completeness] Map written to {outpath}")


def _build_map_html(geojson_str, center_lon, center_lat, city_name, timestamps_js, n_timestamps):
    """Build the standalone MapLibre GL HTML string."""

    last_idx = n_timestamps - 1

    return f"""<!--
  Generated automatically by oswm_codebase/data_quality/completeness/completeness_lib.py
  Do not edit this file directly.
-->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OSWM Completeness Analysis — {city_name}</title>
<link rel="icon" type="image/x-icon" href="../../oswm_codebase/assets/favicon_homepage.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Outfit', sans-serif; background: #0f172a; color: #f8fafc; }}
  #map {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; }}

  .top-bar {{
    position: absolute; top: 0; left: 0; width: 100%; z-index: 10;
    background: rgba(15, 23, 42, 0.88); backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding: 10px 20px; display: flex; align-items: center; justify-content: space-between;
    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
  }}
  .top-bar a.back-btn {{
    background: rgba(255,255,255,0.05); border: 1px solid rgba(0,242,254,0.3);
    color: #00f2fe; padding: 6px 12px; border-radius: 6px; text-decoration: none;
    font-size: 0.9rem; font-weight: 500;
  }}
  .top-bar h3 {{
    color: #f8fafc; font-size: 1.15rem; font-weight: 600; letter-spacing: 0.5px;
    text-shadow: 0 2px 4px rgba(0,0,0,0.3);
  }}
  .top-bar h3 img {{ height: 1.5em; vertical-align: middle; margin-right: 10px; }}

  .controls {{
    position: absolute; top: 62px; right: 12px; z-index: 10;
    background: rgba(15, 23, 42, 0.92); backdrop-filter: blur(14px);
    border: 1px solid rgba(255,255,255,0.1); border-radius: 10px;
    padding: 14px 16px; min-width: 220px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
  }}
  .controls h4 {{ color: #00f2fe; font-size: 0.85rem; margin-bottom: 10px; font-weight: 600; }}
  .controls label {{
    display: flex; align-items: center; gap: 8px; cursor: pointer;
    padding: 4px 0; font-size: 0.85rem; color: #cbd5e1;
  }}
  .controls label:hover {{ color: #f8fafc; }}
  .controls input[type="radio"] {{ accent-color: #00f2fe; }}
  .controls .divider {{
    border-top: 1px solid rgba(255,255,255,0.08); margin: 10px 0;
  }}
  .controls .slider-group {{ margin-top: 6px; }}
  .controls .slider-group .label-row {{
    display: flex; justify-content: space-between; align-items: center;
    font-size: 0.8rem; color: #94a3b8; margin-bottom: 4px;
  }}
  .controls input[type="range"] {{
    width: 100%; accent-color: #00f2fe; cursor: pointer;
  }}

  .legend {{
    position: absolute; bottom: 30px; left: 12px; z-index: 10;
    background: rgba(15, 23, 42, 0.92); backdrop-filter: blur(14px);
    border: 1px solid rgba(255,255,255,0.1); border-radius: 10px;
    padding: 12px 16px; box-shadow: 0 8px 24px rgba(0,0,0,0.25);
  }}
  .legend h4 {{ color: #00f2fe; font-size: 0.8rem; margin-bottom: 8px; font-weight: 600; }}
  .legend .bar {{
    width: 180px; height: 14px; border-radius: 4px;
    background: linear-gradient(to right, #d73027, #fc8d59, #fee08b, #d9ef8b, #66bd63, #1a9850);
  }}
  .legend .labels {{
    display: flex; justify-content: space-between; font-size: 0.7rem;
    color: #94a3b8; margin-top: 3px;
  }}
  .legend .no-data {{
    display: flex; align-items: center; gap: 6px; margin-top: 6px;
    font-size: 0.7rem; color: #94a3b8;
  }}
  .legend .no-data .swatch {{
    width: 14px; height: 14px; border-radius: 3px; background: #475569;
  }}
</style>
</head>
<body>

<div id="map"></div>

<div class="top-bar">
  <a class="back-btn" href="../oswm_qc_main.html">← Back to QC Main</a>
  <h3>
    <img src="../../oswm_codebase/assets/homepage/project_logo.png" alt="OSWM">
    Pedestrian Network Completeness — {city_name}
  </h3>
  <div style="width:120px"></div>
</div>

<div class="controls">
  <h4>Ratio Layer</h4>
  <label><input type="radio" name="metric" value="footway" checked> Footway / Road</label>
  <label><input type="radio" name="metric" value="sidewalk"> Sidewalk / Road</label>
  <div class="divider"></div>
  <div class="slider-group" id="time-slider-group" style="display:{{'block' if n_timestamps > 1 else 'none'}}">
    <div class="label-row">
      <span>Timestamp</span>
      <span id="ts-label"></span>
    </div>
    <input type="range" id="ts-slider" min="0" max="{last_idx}" value="{last_idx}" step="1">
  </div>
</div>

<div class="legend">
  <h4 id="legend-title">Footway / Road Ratio</h4>
  <div class="bar"></div>
  <div class="labels"><span>0</span><span>0.25</span><span>0.5</span><span>0.75</span><span>1.0+</span></div>
  <div class="no-data"><div class="swatch"></div><span>No road data</span></div>

  <div style="border-top: 1px solid rgba(255,255,255,0.08); margin: 12px 0 8px;"></div>
  <label style="display:flex; align-items:center; gap:8px; font-size:0.8rem; color:#cbd5e1; cursor:pointer;">
    <input type="checkbox" id="auto-scale-cb" checked style="accent-color: #00f2fe;"> Auto-scale zoom
  </label>
  <div id="manual-zoom-group" style="display:none; margin-top:8px;">
    <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:#94a3b8; margin-bottom:4px;">
      <span>Manual Zoom</span>
      <span id="manual-zoom-label">Z12</span>
    </div>
    <input type="range" id="manual-zoom-slider" min="{MIN_ZOOM}" max="{MAX_ZOOM}" value="{MIN_ZOOM}" step="1" style="width:100%; accent-color:#00f2fe; cursor:pointer;">
  </div>
</div>

<script>
const TIMESTAMPS = {timestamps_js};
const GEOJSON = {geojson_str};

const map = new maplibregl.Map({{
  container: 'map',
  style: {{
    version: 8,
    sources: {{
      'carto': {{
        type: 'raster',
        tiles: ['https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}@2x.png'.replace('{{s}}', 'a')],
        tileSize: 256,
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
      }}
    }},
    layers: [{{ id: 'carto-tiles', type: 'raster', source: 'carto' }}]
  }},
  center: [{center_lon}, {center_lat}],
  zoom: 12,
  minZoom: 10,
  maxZoom: 18
}});

map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
map.addControl(new maplibregl.ScaleControl({{ unit: 'metric' }}), 'bottom-right');

let currentMetric = 'footway';
let currentTsIdx = {last_idx};

// Color stops for ratio: 0 -> red, 0.25 -> orange, 0.5 -> yellow, 0.75 -> light green, 1.0 -> green
function ratioToColor(ratio) {{
  if (ratio === null || ratio === undefined) return 'rgba(71, 85, 105, 0.5)';
  const r = Math.min(ratio, 1.0);
  const stops = [
    [0.0, [215, 48, 39]],
    [0.15, [252, 141, 89]],
    [0.3, [254, 224, 139]],
    [0.5, [217, 239, 139]],
    [0.75, [102, 189, 99]],
    [1.0, [26, 152, 80]]
  ];
  let lower = stops[0], upper = stops[stops.length - 1];
  for (let i = 0; i < stops.length - 1; i++) {{
    if (r >= stops[i][0] && r <= stops[i+1][0]) {{
      lower = stops[i]; upper = stops[i+1]; break;
    }}
  }}
  const t = upper[0] === lower[0] ? 1 : (r - lower[0]) / (upper[0] - lower[0]);
  const c = lower[1].map((v, j) => Math.round(v + t * (upper[1][j] - v)));
  return `rgba(${{c[0]}}, ${{c[1]}}, ${{c[2]}}, 0.55)`;
}}

function updateFeatureColors() {{
  const suffix = '_t' + currentTsIdx;
  const prop = currentMetric === 'footway' ? 'footway_ratio' : 'sidewalk_ratio';
  const key = prop + suffix;

  GEOJSON.features.forEach(f => {{
    f.properties._color = ratioToColor(f.properties[key]);
  }});

  if (map.getSource('tiles')) {{
    map.getSource('tiles').setData(GEOJSON);
  }}

  document.getElementById('legend-title').textContent =
    currentMetric === 'footway' ? 'Footway / Road Ratio' : 'Sidewalk / Road Ratio';
}}

function updateTimestampLabel() {{
  document.getElementById('ts-label').textContent = TIMESTAMPS[currentTsIdx] || '';
}}

let autoScale = true;
let manualZoom = {MIN_ZOOM};

function getActiveZoomLevel() {{
  if (autoScale) {{
    let z = Math.round(map.getZoom());
    if (z < {MIN_ZOOM}) z = {MIN_ZOOM};
    if (z > {MAX_ZOOM}) z = {MAX_ZOOM};
    return z;
  }} else {{
    return manualZoom;
  }}
}}

function updateLayerVisibility() {{
  const activeZ = getActiveZoomLevel();
  for (let z = {MIN_ZOOM}; z <= {MAX_ZOOM}; z++) {{
    const layerId = 'tiles-z' + z;
    if (map.getLayer(layerId)) {{
      map.setLayoutProperty(layerId, 'visibility', z === activeZ ? 'visible' : 'none');
    }}
  }}
}}

map.on('zoom', () => {{
  if (autoScale) updateLayerVisibility();
}});

map.on('load', () => {{
  updateFeatureColors();
  updateTimestampLabel();

  map.addSource('tiles', {{ type: 'geojson', data: GEOJSON }});

  // One layer per zoom level for zoom-dependent visibility
  for (let z = {MIN_ZOOM}; z <= {MAX_ZOOM}; z++) {{
    map.addLayer({{
      id: 'tiles-z' + z,
      type: 'fill',
      source: 'tiles',
      filter: ['==', ['get', 'zoom'], z],
      paint: {{
        'fill-color': ['get', '_color'],
        'fill-opacity': 0.7,
        'fill-outline-color': 'rgba(255,255,255,0.25)'
      }}
    }});
  }}

  updateLayerVisibility();

  // Popup on click
  for (let z = {MIN_ZOOM}; z <= {MAX_ZOOM}; z++) {{
    map.on('click', 'tiles-z' + z, (e) => {{
      const f = e.features[0];
      const p = f.properties;
      const suffix = '_t' + currentTsIdx;
      const roadLen = (p['road_length' + suffix] || 0).toFixed(0);
      const footLen = (p['footway_length' + suffix] || 0).toFixed(0);
      const swLen = (p['sidewalk_length' + suffix] || 0).toFixed(0);
      const fRatio = p['footway_ratio' + suffix];
      const sRatio = p['sidewalk_ratio' + suffix];

      const chartData = [];
      for (let i = 0; i < TIMESTAMPS.length; i++) {{
        const r = p[(currentMetric === 'footway' ? 'footway_ratio' : 'sidewalk_ratio') + '_t' + i];
        chartData.push(r !== null && r !== undefined ? (r * 100).toFixed(1) : null);
      }}

      const html = `
        <div style="font-family:Outfit,sans-serif;width:100%;">
          <h4 style="margin:0 0 6px;color:#00f2fe;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:4px">
            Tile ${{p.tile_id}}</h4>
          <div style="font-size:12px;color:#cbd5e1;line-height:1.6">
            <b>Roads:</b> ${{Number(roadLen).toLocaleString()}} m<br>
            <b>Footways:</b> ${{Number(footLen).toLocaleString()}} m<br>
            <b>Sidewalks:</b> ${{Number(swLen).toLocaleString()}} m<br>
            <b>Footway ratio:</b> ${{fRatio != null ? (fRatio * 100).toFixed(1) + '%' : 'N/A'}}<br>
            <b>Sidewalk ratio:</b> ${{sRatio != null ? (sRatio * 100).toFixed(1) + '%' : 'N/A'}}
          </div>
          <div style="margin-top:12px; height:120px; width:100%; position:relative;">
            <canvas></canvas>
          </div>
        </div>`;
      
      const popup = new maplibregl.Popup({{ className: 'dark-popup' }})
        .setLngLat(e.lngLat).setHTML(html).addTo(map);

      const canvas = popup.getElement().querySelector('canvas');
      if (canvas) {{
        const ctx = canvas.getContext('2d');
        new Chart(ctx, {{
          type: 'line',
          data: {{
            labels: TIMESTAMPS,
            datasets: [{{
              label: currentMetric === 'footway' ? 'Footway Ratio (%)' : 'Sidewalk Ratio (%)',
              data: chartData,
              borderColor: '#00f2fe',
              backgroundColor: 'rgba(0, 242, 254, 0.1)',
              borderWidth: 2,
              pointBackgroundColor: '#0f172a',
              pointBorderColor: '#00f2fe',
              pointRadius: 3,
              fill: true,
              tension: 0.2
            }}]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
              legend: {{ display: false }},
              tooltip: {{
                backgroundColor: 'rgba(15, 23, 42, 0.9)',
                titleColor: '#00f2fe',
                bodyColor: '#f8fafc',
                borderColor: 'rgba(255,255,255,0.1)',
                borderWidth: 1
              }}
            }},
            scales: {{
              x: {{
                ticks: {{ color: '#94a3b8', font: {{ size: 9 }}, maxRotation: 45, minRotation: 45 }},
                grid: {{ color: 'rgba(255,255,255,0.05)' }}
              }},
              y: {{
                beginAtZero: true,
                ticks: {{ color: '#94a3b8', font: {{ size: 9 }} }},
                grid: {{ color: 'rgba(255,255,255,0.05)' }}
              }}
            }}
          }}
        }});
      }}
    }});

    map.on('mouseenter', 'tiles-z' + z, () => {{ map.getCanvas().style.cursor = 'pointer'; }});
    map.on('mouseleave', 'tiles-z' + z, () => {{ map.getCanvas().style.cursor = ''; }});
  }}
}});

document.getElementById('auto-scale-cb').addEventListener('change', (e) => {{
  autoScale = e.target.checked;
  document.getElementById('manual-zoom-group').style.display = autoScale ? 'none' : 'block';
  updateLayerVisibility();
}});

document.getElementById('manual-zoom-slider').addEventListener('input', (e) => {{
  manualZoom = parseInt(e.target.value);
  document.getElementById('manual-zoom-label').textContent = 'Z' + manualZoom;
  updateLayerVisibility();
}});

document.querySelectorAll('input[name="metric"]').forEach(radio => {{
  radio.addEventListener('change', (e) => {{
    currentMetric = e.target.value;
    updateFeatureColors();
  }});
}});

document.getElementById('ts-slider').addEventListener('input', (e) => {{
  currentTsIdx = parseInt(e.target.value);
  updateTimestampLabel();
  updateFeatureColors();
}});
</script>

<style>
  .maplibregl-popup-content {{
    background: rgba(15, 23, 42, 0.95) !important;
    border: 1px solid rgba(0, 242, 254, 0.3) !important;
    border-radius: 8px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.3) !important;
    padding: 12px !important;
    width: 270px !important;
    max-width: none !important;
  }}
  .maplibregl-popup-tip {{ border-top-color: rgba(15, 23, 42, 0.95) !important; }}
  .maplibregl-popup-close-button {{ color: #94a3b8 !important; font-size: 18px !important; }}
</style>
</body>
</html>
"""
