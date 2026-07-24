"""Generate the static, accessibility-aware OSWM routing dataset.

The current output remains GeoJSON so existing nodes can adopt profiles before
the planned compact binary graph format lands. All expensive policy decisions
are nevertheless precomputed here: the browser receives small directional
grades rather than raw OSM accessibility tags.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

# The generator runs from a node repository while this file lives inside the
# oswm_codebase submodule.
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
oswm_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if oswm_dir not in sys.path:
    sys.path.insert(0, oswm_dir)

import constants
from routing.elevation import (
    ElevationResolver,
    SlopeEstimate,
    load_slope_cache,
    save_slope_cache,
    slope_cache_key,
)
from routing.grading import (
    compact_grade_properties,
    grade_feature,
    is_unknown,
    parse_incline_percent,
)
from routing.profile_rules import (
    DEFAULT_ELEVATION_CONFIG,
    PROFILE_RULESET_VERSION,
    ROUTING_PROFILES,
)
from routing.profile_validation import (
    profile_ruleset_hash,
    public_profile_metadata,
    validate_profiles,
)


def _edge_kind(row: pd.Series, source_layer: str) -> str:
    if source_layer == "crossings":
        return "crossing"
    if source_layer == "sidewalks":
        return "sidewalk"
    highway = str(row.get("highway", "")).strip().lower()
    oswm_footway = str(row.get("oswm_footway", "")).strip().lower()
    if highway == "steps" or oswm_footway == "stairways":
        return "stairs"
    return "footway"


def _prepare_lines(gdf: gpd.GeoDataFrame, source_layer: str) -> gpd.GeoDataFrame:
    valid = gdf[gdf.geometry.notnull() & ~gdf.geometry.is_empty].copy()
    valid = valid[valid.geometry.type.isin(["LineString", "MultiLineString"])]
    if valid.empty:
        return valid
    if valid.crs is None:
        valid = valid.set_crs("EPSG:4326")
    elif str(valid.crs).upper() != "EPSG:4326":
        valid = valid.to_crs("EPSG:4326")
    valid = valid.explode(index_parts=False, ignore_index=True)
    valid = valid[valid.geometry.type == "LineString"].copy()
    valid["source_layer"] = source_layer
    valid["edge_kind"] = valid.apply(
        lambda row: _edge_kind(row, source_layer), axis=1
    )
    return valid


def _associate_kerbs(
    crossings: gpd.GeoDataFrame,
    kerbs: gpd.GeoDataFrame | None,
    radius_m: float = 2.0,
) -> gpd.GeoDataFrame:
    """Attach nearby kerb/tactile values without committing source attributes."""

    crossings = crossings.copy()
    crossing_kerbs = (
        crossings["kerb"].tolist()
        if "kerb" in crossings
        else [None] * len(crossings)
    )
    crossing_tactile = (
        crossings["tactile_paving"].tolist()
        if "tactile_paving" in crossings
        else [None] * len(crossings)
    )
    crossings["associated_kerbs"] = [
        [] if is_unknown(value) else [value] for value in crossing_kerbs
    ]
    crossings["associated_tactile_paving"] = [
        [] if is_unknown(value) else [value] for value in crossing_tactile
    ]
    if crossings.empty or kerbs is None or kerbs.empty:
        return crossings

    kerbs = kerbs[kerbs.geometry.notnull() & ~kerbs.geometry.is_empty].copy()
    if kerbs.empty:
        return crossings
    if kerbs.crs is None:
        kerbs = kerbs.set_crs("EPSG:4326")
    elif str(kerbs.crs).upper() != "EPSG:4326":
        kerbs = kerbs.to_crs("EPSG:4326")
    metric_crs = crossings.estimate_utm_crs()
    if metric_crs is None:
        return crossings

    crossing_metric = crossings.to_crs(metric_crs).reset_index(drop=True)
    kerb_metric = kerbs.to_crs(metric_crs).reset_index(drop=True)
    spatial_index = kerb_metric.sindex

    kerb_lists: list[list[Any]] = []
    tactile_lists: list[list[Any]] = []
    for position, geometry in enumerate(crossing_metric.geometry):
        candidate_positions = list(
            spatial_index.query(geometry.buffer(radius_m), predicate="intersects")
        )
        nearby = kerb_metric.iloc[candidate_positions]
        kerb_lists.append(
            crossings.iloc[position]["associated_kerbs"]
            + [
                value
                for value in nearby.get("kerb", pd.Series(dtype=object)).tolist()
                if not is_unknown(value)
            ]
        )
        tactile_lists.append(
            crossings.iloc[position]["associated_tactile_paving"]
            + [
                value
                for value in nearby.get(
                    "tactile_paving", pd.Series(dtype=object)
                ).tolist()
                if not is_unknown(value)
            ]
        )

    crossings["associated_kerbs"] = kerb_lists
    crossings["associated_tactile_paving"] = tactile_lists
    return crossings


def _json_dump(payload: dict[str, Any], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def _profile_audit(
    properties: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    audit: dict[str, dict[str, Any]] = {}
    for profile_id in ROUTING_PROFILES:
        grades = [
            min(
                int(item[f"{profile_id}_grade_fwd"]),
                int(item[f"{profile_id}_grade_bwd"]),
            )
            for item in properties
        ]
        limits = Counter(
            item.get(f"{profile_id}_limit", "none") for item in properties
        )
        audit[profile_id] = {
            "minimum_grade": min(grades) if grades else None,
            "maximum_grade": max(grades) if grades else None,
            "mean_grade": round(sum(grades) / len(grades), 2) if grades else None,
            "grade_bands": {
                "0": sum(grade == 0 for grade in grades),
                "1-19": sum(1 <= grade <= 19 for grade in grades),
                "20-39": sum(20 <= grade <= 39 for grade in grades),
                "40-59": sum(40 <= grade <= 59 for grade in grades),
                "60-79": sum(60 <= grade <= 79 for grade in grades),
                "80-100": sum(80 <= grade <= 100 for grade in grades),
            },
            "most_common_limiting_factors": dict(limits.most_common(10)),
        }
    return audit


def main() -> None:
    print("Generating accessibility-aware routing data...")
    validate_profiles(ROUTING_PROFILES)

    required = [
        (constants.sidewalks_path, "sidewalks"),
        (constants.crossings_path, "crossings"),
        (constants.other_footways_path, "other_footways"),
    ]
    for path, name in required:
        if not os.path.exists(path):
            raise FileNotFoundError(f"processed {name} data not found at {path}")

    sidewalks = _prepare_lines(
        gpd.read_parquet(constants.sidewalks_path), "sidewalks"
    )
    crossings = _prepare_lines(
        gpd.read_parquet(constants.crossings_path), "crossings"
    )
    other_footways = _prepare_lines(
        gpd.read_parquet(constants.other_footways_path), "other_footways"
    )

    kerbs = (
        gpd.read_parquet(constants.kerbs_path)
        if os.path.exists(constants.kerbs_path)
        else None
    )
    crossings = _associate_kerbs(crossings, kerbs)

    nonempty = [
        frame for frame in (sidewalks, crossings, other_footways) if not frame.empty
    ]
    if not nonempty:
        raise RuntimeError("no routable LineString features were found")
    combined = gpd.GeoDataFrame(
        pd.concat(nonempty, ignore_index=True, sort=False),
        geometry="geometry",
        crs=nonempty[0].crs,
    )
    if combined.crs is None:
        combined = combined.set_crs("EPSG:4326")
    elif str(combined.crs).upper() != "EPSG:4326":
        combined = combined.to_crs("EPSG:4326")

    metric_crs = combined.estimate_utm_crs()
    if metric_crs is None:
        raise RuntimeError("could not determine a metric CRS for edge lengths")
    lengths_m = combined.to_crs(metric_crs).geometry.length

    elevation_config = getattr(
        constants, "ELEVATION_CONFIG", DEFAULT_ELEVATION_CONFIG
    )
    resolver = ElevationResolver(elevation_config)
    resolver_fingerprint = resolver.fingerprint()
    old_slope_cache = load_slope_cache(constants.routing_slope_cache_path)
    new_slope_cache: dict[str, dict[str, Any]] = {}

    output_rows: list[dict[str, Any]] = []
    output_properties: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    for position, (_index, row) in enumerate(combined.iterrows()):
        raw_incline = row.get("incline")
        direct_incline, _incline_kind = parse_incline_percent(raw_incline)
        if direct_incline is not None:
            slope = SlopeEstimate(
                direct_incline,
                "direct_osm_numeric",
                100,
                note="numeric OSM incline is authoritative",
            )
        else:
            cache_key = slope_cache_key(
                row.geometry, raw_incline, resolver_fingerprint
            )
            cached = old_slope_cache.get(cache_key)
            slope = None
            if isinstance(cached, dict):
                try:
                    slope = SlopeEstimate(**cached)
                except TypeError:
                    # A stale/malformed entry must not block regeneration.
                    pass
            if slope is None:
                slope = resolver.estimate(row.geometry, raw_incline)
            new_slope_cache[cache_key] = slope.to_dict()
        source_counts[slope.source] += 1

        graded = grade_feature(
            row.to_dict(),
            edge_kind=row["edge_kind"],
            estimated_slope_percent=slope.percent,
            slope_source=slope.source,
            slope_confidence=slope.confidence,
        )
        properties: dict[str, Any] = {
            "routing_id": f"{row['source_layer']}:{row.get('id', position)}:{position}",
            "source_id": str(row.get("id", position)),
            "edge_kind": row["edge_kind"],
            "length_m": round(float(lengths_m.iloc[position]), 2),
            "slope_pct": slope.percent,
            "slope_source": (
                "direct_osm_numeric"
                if direct_incline is not None
                else slope.source
            ),
            "slope_confidence": (
                100 if direct_incline is not None else slope.confidence
            ),
        }
        properties.update(compact_grade_properties(graded))
        output_properties.append(properties)
        output_rows.append({**properties, "geometry": row.geometry})

    os.makedirs(constants.routing_folderpath, exist_ok=True)
    save_slope_cache(constants.routing_slope_cache_path, new_slope_cache)

    output = gpd.GeoDataFrame(output_rows, geometry="geometry", crs="EPSG:4326")
    output.to_file(constants.routing_demo_path, driver="GeoJSON")

    rules_hash = profile_ruleset_hash(ROUTING_PROFILES)
    profile_payload = {
        "schema_version": 1,
        "ruleset_version": PROFILE_RULESET_VERSION,
        "ruleset_hash": rules_hash,
        "profiles": public_profile_metadata(ROUTING_PROFILES),
    }
    _json_dump(profile_payload, constants.routing_profiles_path)

    metadata = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ruleset_version": PROFILE_RULESET_VERSION,
        "ruleset_hash": rules_hash,
        "feature_count": len(output),
        "edge_kind_counts": dict(Counter(output["edge_kind"])),
        "slope_source_counts": dict(source_counts),
        "elevation_provider_fingerprint": resolver_fingerprint,
        "profile_audit": _profile_audit(output_properties),
        "warnings": [
            "Profile rules are provisional and require participatory calibration.",
            (
                "Copernicus GLO-30 is a 30 m surface model; its slopes describe "
                "terrain trend, not measured sidewalk or cross slope."
            ),
        ],
    }
    _json_dump(metadata, constants.routing_metadata_path)
    print(
        f"Generated {len(output)} routable features at "
        f"{constants.routing_demo_path}."
    )


if __name__ == "__main__":
    main()
