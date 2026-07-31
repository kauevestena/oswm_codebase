"""Generate shared accessibility-aware routing and hazard datasets.

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
from shapely.geometry import mapping

# The generator runs from a node repository while this file lives inside the
# oswm_codebase submodule.
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
oswm_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if oswm_dir not in sys.path:
    sys.path.insert(0, oswm_dir)

import constants
from accessibility.normalization import (
    is_unknown,
    parse_incline_percent,
    prepare_feature,
)
from hazard_analysis.assessment import (
    assess_feature,
    compact_hazard_properties,
)
from hazard_analysis.rules import (
    HAZARD_CATEGORIES,
    HAZARD_PROFILES,
    HAZARD_RULES,
    HAZARD_RULESET_VERSION,
    SEVERITY_LEVELS,
)
from hazard_analysis.terrain import generate_terrain_overlays
from hazard_analysis.validation import (
    public_rule_metadata,
    ruleset_hash as hazard_ruleset_hash,
    validate_rules,
)
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


def _associate_crossing_context(
    crossings: gpd.GeoDataFrame,
    kerbs: gpd.GeoDataFrame | None,
    sidewalks: gpd.GeoDataFrame | None,
    radius_m: float = 2.0,
) -> gpd.GeoDataFrame:
    """Attach paired kerb/tactile and nearby surface evidence."""

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
    crossings["associated_kerb_surfaces"] = [[] for _ in range(len(crossings))]
    crossings["associated_sidewalk_surfaces"] = [
        [] for _ in range(len(crossings))
    ]
    crossings["associated_transition_states"] = [
        [
            {
                **({} if is_unknown(kerb) else {"kerb": kerb}),
                **(
                    {}
                    if is_unknown(tactile)
                    else {"tactile_paving": tactile}
                ),
            }
        ]
        if not is_unknown(kerb) or not is_unknown(tactile)
        else []
        for kerb, tactile in zip(crossing_kerbs, crossing_tactile)
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
    sidewalk_metric = None
    sidewalk_index = None
    if sidewalks is not None and not sidewalks.empty:
        sidewalk_metric = sidewalks.to_crs(metric_crs).reset_index(drop=True)
        sidewalk_index = sidewalk_metric.sindex

    kerb_lists: list[list[Any]] = []
    tactile_lists: list[list[Any]] = []
    kerb_surface_lists: list[list[Any]] = []
    sidewalk_surface_lists: list[list[Any]] = []
    transition_lists: list[list[dict[str, Any]]] = []
    for position, geometry in enumerate(crossing_metric.geometry):
        candidate_positions = list(
            spatial_index.query(geometry.buffer(radius_m), predicate="intersects")
        )
        nearby = kerb_metric.iloc[candidate_positions]
        kerb_values = list(crossings.iloc[position]["associated_kerbs"])
        tactile_values = list(
            crossings.iloc[position]["associated_tactile_paving"]
        )
        kerb_surfaces = []
        sidewalk_surfaces = []
        transitions = list(
            crossings.iloc[position]["associated_transition_states"]
        )
        for _nearby_position, kerb_row in nearby.iterrows():
            kerb_value = kerb_row.get("kerb")
            tactile_value = kerb_row.get("tactile_paving")
            kerb_surface = kerb_row.get("surface")
            if not is_unknown(kerb_value):
                kerb_values.append(kerb_value)
            if not is_unknown(tactile_value):
                tactile_values.append(tactile_value)
            if not is_unknown(kerb_surface):
                kerb_surfaces.append(kerb_surface)

            sidewalk_surface = None
            if sidewalk_metric is not None and sidewalk_index is not None:
                sidewalk_candidates = list(
                    sidewalk_index.query(
                        kerb_row.geometry.buffer(radius_m),
                        predicate="intersects",
                    )
                )
                if sidewalk_candidates:
                    nearby_sidewalks = sidewalk_metric.iloc[
                        sidewalk_candidates
                    ].copy()
                    nearby_sidewalks["_distance"] = (
                        nearby_sidewalks.geometry.distance(kerb_row.geometry)
                    )
                    closest = nearby_sidewalks.sort_values("_distance").iloc[0]
                    sidewalk_surface = closest.get("surface")
                    if not is_unknown(sidewalk_surface):
                        sidewalk_surfaces.append(sidewalk_surface)

            state = {}
            for key, value in (
                ("kerb", kerb_value),
                ("tactile_paving", tactile_value),
                ("kerb_surface", kerb_surface),
                ("sidewalk_surface", sidewalk_surface),
            ):
                if not is_unknown(value):
                    state[key] = value
            if state:
                transitions.append(state)

        kerb_lists.append(kerb_values)
        tactile_lists.append(tactile_values)
        kerb_surface_lists.append(kerb_surfaces)
        sidewalk_surface_lists.append(sidewalk_surfaces)
        transition_lists.append(transitions)

    crossings["associated_kerbs"] = kerb_lists
    crossings["associated_tactile_paving"] = tactile_lists
    crossings["associated_kerb_surfaces"] = kerb_surface_lists
    crossings["associated_sidewalk_surfaces"] = sidewalk_surface_lists
    crossings["associated_transition_states"] = transition_lists
    return crossings


def _json_dump(
    payload: dict[str, Any],
    path: str,
    *,
    expected_feature_count: int | None = None,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / (
        f".{destination.name}.tmp.{os.getpid()}"
    )
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=None if expected_feature_count is not None else 2,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":")
                if expected_feature_count is not None
                else None,
            )
            handle.write("\n")
        with temporary.open(encoding="utf-8") as handle:
            check = json.load(handle)
        if expected_feature_count is not None:
            actual = len(check.get("features", []))
            if actual != expected_feature_count:
                raise ValueError(
                    f"{destination}: expected {expected_feature_count} "
                    f"features, got {actual}"
                )
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _profile_audit(
    properties: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    audit: dict[str, dict[str, Any]] = {}
    for profile_id, profile in ROUTING_PROFILES.items():
        if profile["routing_mode"] == "distance":
            continue
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


def _hazard_audit(
    profile_properties: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    audit = {}
    for profile_id, properties in profile_properties.items():
        severities = [int(item["severity"]) for item in properties]
        statuses = Counter(item["status"] for item in properties)
        rules = Counter(
            rule_id
            for item in properties
            for rule_id in item.get("rule_ids", [])
        )
        audit[profile_id] = {
            "severity_counts": {
                str(level): severities.count(level)
                for level in SEVERITY_LEVELS
            },
            "status_counts": dict(statuses),
            "most_common_decisive_rules": dict(rules.most_common(10)),
        }
    return audit


def main() -> None:
    print("Generating accessibility-aware routing data...")
    validate_profiles(ROUTING_PROFILES)
    validate_rules(HAZARD_RULES)

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
    crossings = _associate_crossing_context(crossings, kerbs, sidewalks)

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
    hazard_features: dict[str, list[dict[str, Any]]] = {
        profile_id: [] for profile_id in HAZARD_PROFILES
    }
    hazard_properties: dict[str, list[dict[str, Any]]] = {
        profile_id: [] for profile_id in HAZARD_PROFILES
    }
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

        prepared = prepare_feature(
            row.to_dict(),
            edge_kind=row["edge_kind"],
            estimated_slope_percent=slope.percent,
            slope_source=slope.source,
            slope_confidence=slope.confidence,
        )
        graded = grade_feature(
            prepared,
            edge_kind=row["edge_kind"],
            estimated_slope_percent=slope.percent,
            slope_source=slope.source,
            slope_confidence=slope.confidence,
        )
        assessed = assess_feature(prepared, normalized=True)
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
        for profile_id in HAZARD_PROFILES:
            hazard = {
                "routing_id": properties["routing_id"],
                "source_id": properties["source_id"],
                "edge_kind": properties["edge_kind"],
                "length_m": properties["length_m"],
                "slope_pct": properties["slope_pct"],
                "slope_source": properties["slope_source"],
                "slope_confidence": properties["slope_confidence"],
                **compact_hazard_properties(assessed, profile_id),
            }
            hazard_properties[profile_id].append(hazard)
            hazard_features[profile_id].append(
                {
                    "type": "Feature",
                    "geometry": mapping(row.geometry),
                    "properties": hazard,
                }
            )
    resolver.close()

    os.makedirs(constants.routing_folderpath, exist_ok=True)
    save_slope_cache(constants.routing_slope_cache_path, new_slope_cache)

    routing_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(row["geometry"]),
                "properties": {
                    key: value
                    for key, value in row.items()
                    if key != "geometry"
                },
            }
            for row in output_rows
        ],
    }
    _json_dump(
        routing_collection,
        constants.routing_demo_path,
        expected_feature_count=len(output_rows),
    )

    rules_hash = profile_ruleset_hash(ROUTING_PROFILES)
    distance_profile_id = next(
        profile_id
        for profile_id, profile in ROUTING_PROFILES.items()
        if profile["routing_mode"] == "distance"
    )
    profile_payload = {
        "schema_version": 2,
        "ruleset_version": PROFILE_RULESET_VERSION,
        "ruleset_hash": rules_hash,
        "distance_profile_id": distance_profile_id,
        "profiles": public_profile_metadata(ROUTING_PROFILES),
    }
    _json_dump(profile_payload, constants.routing_profiles_path)

    metadata = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ruleset_version": PROFILE_RULESET_VERSION,
        "ruleset_hash": rules_hash,
        "feature_count": len(output_rows),
        "edge_kind_counts": dict(
            Counter(item["edge_kind"] for item in output_properties)
        ),
        "slope_source_counts": dict(source_counts),
        "elevation_provider_fingerprint": resolver_fingerprint,
        "profile_audit": _profile_audit(output_properties),
        "warnings": [
            "Profile rules are provisional and require participatory calibration.",
            (
                "Global DEM providers describe terrain trend, not measured "
                "sidewalk or cross slope."
            ),
        ],
    }
    _json_dump(metadata, constants.routing_metadata_path)

    os.makedirs(constants.hazard_analysis_folderpath, exist_ok=True)
    for profile_id, features in hazard_features.items():
        _json_dump(
            {"type": "FeatureCollection", "features": features},
            constants.hazard_profile_features_path(profile_id),
            expected_feature_count=len(output_rows),
        )
        # Also write GeoParquet for analytical and cloud-optimized use
        if features:
            profile_gdf = gpd.GeoDataFrame.from_features(
                features, crs="EPSG:4326"
            )
            profile_gdf.to_parquet(
                constants.hazard_profile_parquet_path(profile_id)
            )

    hazard_hash = hazard_ruleset_hash(HAZARD_RULES)
    hazard_profile_payload = {
        "schema_version": 1,
        "ruleset_version": HAZARD_RULESET_VERSION,
        "ruleset_hash": hazard_hash,
        "profiles": HAZARD_PROFILES,
        "categories": HAZARD_CATEGORIES,
        "severity_levels": {
            str(level): metadata
            for level, metadata in SEVERITY_LEVELS.items()
        },
        "rules": public_rule_metadata(HAZARD_RULES),
    }
    _json_dump(hazard_profile_payload, constants.hazard_profiles_path)

    terrain_config = getattr(
        constants,
        "HAZARD_TERRAIN_CONFIG",
        {
            "enabled": True,
            "max_dimension": 1600,
            "smoothing_sigma_pixels": 3.0,
        },
    )
    bounds = tuple(float(value) for value in combined.total_bounds)
    terrain_metadata = generate_terrain_overlays(
        bounds,
        elevation_config,
        terrain_config,
        constants.hazard_analysis_folderpath,
    )
    terrain_metadata["generated_at"] = datetime.now(timezone.utc).isoformat()
    _json_dump(terrain_metadata, constants.hazard_terrain_metadata_path)

    hazard_metadata = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ruleset_version": HAZARD_RULESET_VERSION,
        "ruleset_hash": hazard_hash,
        "feature_count": len(output_rows),
        "edge_kind_counts": dict(
            Counter(item["edge_kind"] for item in output_properties)
        ),
        "slope_source_counts": dict(source_counts),
        "profile_audit": _hazard_audit(hazard_properties),
        "warnings": [
            "Hazard rules are provisional and require participatory calibration.",
            (
                "Missing evidence is never converted into a negative claim; "
                "unflagged does not mean safe."
            ),
            (
                "Surface material is used only as a low-confidence proxy where "
                "direct smoothness evidence is unavailable."
            ),
            (
                "Terrain rasters show unsigned contextual potential from a "
                "global DSM, never measured sidewalk or cross slope."
            ),
        ],
    }
    _json_dump(hazard_metadata, constants.hazard_metadata_path)
    print(
        f"Generated {len(output_rows)} routable features at "
        f"{constants.routing_demo_path} and {len(output_rows)} hazard "
        "features per profile."
    )


if __name__ == "__main__":
    main()
