"""Opt-in daily integration and a non-publishing Curitiba replication preview."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
from datetime import datetime, timezone

from time_utils import isoformat_utc, parse_timestamp


BACKEND = "geofabrik_replication"
STAGING = Path(".cache/oswm/replication/staged")
REPORT = STAGING / "report.json"
ROADS = "roads_for_completeness"
ROAD_TYPES = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential",
              "unclassified", "motorway_link", "trunk_link", "primary_link", "secondary_link",
              "tertiary_link"]


def enabled():
    return os.environ.get("OSWM_OSM_UPDATE_BACKEND", "legacy") == BACKEND


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def registry_for_products(root, registry):
    """Annotate candidate products without advancing the publication checkpoint."""
    if not enabled():
        return registry
    candidate = read_json(Path(root) / REPORT)
    if not candidate.get("city_fingerprints") or parse_timestamp(candidate.get("snapshot_timestamp")) is None:
        raise ValueError("Products require a validated candidate source cutoff")
    return {**registry, "Data Fetching": candidate["snapshot_timestamp"]}


def feature_records(frame):
    """Canonical per-object content, independent of row order and empty columns."""
    import pandas as pd
    records = {}
    for row in frame.to_dict("records"):
        identity = f"{row.get('element')}:{int(row['id'])}"
        if identity in records:
            raise ValueError(f"Duplicate OSM identity: {identity}")
        properties = {}
        for key, value in row.items():
            if key == "geometry":
                properties[key] = value.normalize().wkb_hex
            elif isinstance(value, (list, tuple, dict)):
                properties[key] = value
            elif value is not None and not pd.isna(value):
                properties[key] = value.item() if hasattr(value, "item") else value
        records[identity] = json.dumps(properties, sort_keys=True, ensure_ascii=False, default=str)
    return records


def fingerprint(frame):
    records = feature_records(frame)
    encoded = json.dumps(records, sort_keys=True, ensure_ascii=False).encode()
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "count": len(records),
            "crs": str(frame.crs)}


def difference(before, after):
    left, right = feature_records(before), feature_records(after)
    return {"added": len(right.keys() - left.keys()), "removed": len(left.keys() - right.keys()),
            "modified": sum(left[k] != right[k] for k in left.keys() & right.keys())}


def extract_city(path, cfg):
    """One extraction contract shared by daily acquisition and snapshot parity."""
    import osmnx as ox
    import geopandas as gpd
    from shapely.geometry import box
    from functions import merge_list_of_dictionaries
    from pbf_acquisition import features_from_pbf
    STAGING.mkdir(parents=True, exist_ok=True)
    boundary = gpd.read_file(cfg.boundaries_geojson_path).geometry.union_all()
    bbox = box(*boundary.bounds)
    tags = merge_list_of_dictionaries([*cfg.layer_tags_dict.values(), {"highway": ROAD_TYPES}])
    combined = features_from_pbf(ox, path, bbox, tags, temporary_dir=STAGING)
    combined = combined.reset_index().rename(columns={"osmid": "id"})
    roads = combined[combined["highway"].isin(ROAD_TYPES)
                     & combined.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    pedestrian = combined[combined.geometry.intersects(boundary)].copy()
    pedestrian = pedestrian[~pedestrian.isin(cfg.OTHER_FOOTWAY_EXCLUSION_RULES).any(axis=1)]
    layers = {}
    for category, query in cfg.layer_tags_dict.items():
        selected = pedestrian.isin(query).any(axis=1)
        layers[category] = pedestrian[selected].copy()
        pedestrian = pedestrian[~selected]
    layers[ROADS] = roads
    for name, frame in layers.items():
        # Match the existing raw-data serialization contract, including list tags.
        for column in frame.columns:
            if frame[column].dtype == object:
                frame[column] = frame[column].astype(str)
        layers[name] = frame.replace("nan", None)
    return layers


def prepare(*, bootstrap_url=None, target_sequence=None):
    import geopandas as gpd
    from shapely.geometry import box
    import constants as cfg
    from pbf_acquisition import INDEX_URL, _cached_json, select_region
    from pbf_replication import sync_source

    STAGING.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    boundary = gpd.read_file(cfg.boundaries_geojson_path).geometry.union_all()
    cache = Path(".cache/oswm/replication/source")
    cache.mkdir(parents=True, exist_ok=True)
    region, url = select_region(
        _cached_json(INDEX_URL, cache), box(*boundary.bounds),
        os.environ.get("OSWM_PBF_REGION", getattr(cfg, "PBF_REGION", "auto")),
        boundary_loader=lambda u: _cached_json(u, cache),
    )
    published = read_json("data/updates/acquisition.json")
    registry = read_json(cfg.updating_infos_path)
    path, source = sync_source(
        url, cache / region, bootstrap_url=bootstrap_url, target_sequence=target_sequence,
        minimum_timestamp=parse_timestamp(registry.get("Data Fetching")),
        max_download_bytes=getattr(cfg, "PBF_MAX_DOWNLOAD_MIB", 1024) * 1024 * 1024,
        max_age_hours=getattr(cfg, "PBF_MAX_AGE_HOURS", 72),
    )
    layers = extract_city(path, cfg)
    digests, changes = {}, {}
    for name, frame in layers.items():
        dest = STAGING / f"{name}.parquet"
        frame.to_parquet(dest, index=False)
        normalized = gpd.read_parquet(dest)
        digests[name] = fingerprint(normalized)
        previous = Path("data/raw") / f"{name}.parquet"
        changes[name] = difference(gpd.read_parquet(previous), normalized) if previous.exists() else {
            "added": len(normalized), "removed": 0, "modified": 0,
        }
    config_hash = hashlib.sha256(Path("config.py").read_bytes()
                                 + Path(cfg.boundaries_geojson_path).read_bytes()).hexdigest()
    report = {**source, "region": region, "city_fingerprints": digests,
              "configuration_sha256": config_hash, "net_snapshot_changes": changes,
              "needs_update": (digests != published.get("city_fingerprints")
                               or config_hash != published.get("configuration_sha256")
                               or any(not (Path("data/raw") / f"{name}.parquet").exists()
                                      for name in digests)),
              "history": {"mode": "cached", "backfill": "unavailable",
                          "changes_measure": "net differences between snapshots; not all edits"}}
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    return report


def install_prepared():
    """Install staged raw inputs; source/public acquisition watermarks stay separate."""
    import geopandas as gpd
    report = read_json(REPORT)
    if not report.get("city_fingerprints"):
        raise ValueError("No successfully prepared replica acquisition")
    for name, expected in report["city_fingerprints"].items():
        source = STAGING / f"{name}.parquet"
        if fingerprint(gpd.read_parquet(source)) != expected:
            raise ValueError(f"Staged input changed after prepare: {name}")
    for name in report["city_fingerprints"]:
        destination = Path("data/raw") / f"{name}.parquet"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(STAGING / f"{name}.parquet", destination)


def render():
    """Render replica status without querying a history provider or erasing history."""
    report = read_json(REPORT)
    if not report.get("snapshot_timestamp"):
        raise ValueError("No verified replication report to render")
    root = Path("hub/watcher")
    root.mkdir(parents=True, exist_ok=True)
    details = html.escape(json.dumps({k: report[k] for k in (
        "region", "sequence", "snapshot_timestamp", "checked_at", "net_snapshot_changes", "history"
    )}, indent=2))
    (root / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>OSWM update status</title>'
        '<h1>Daily OSM snapshot status</h1><p>Source cutoff and processing time are separate. '
        'Changes below are net snapshot differences, not counts of every edit. '
        'Contributor history and historical backfill are unavailable in this pilot; '
        'previously recorded historical data are preserved.</p><pre>' + details + '</pre></html>'
    )
    # Existing historical feeds remain available with their original dates.
    for name in ("feed.xml", "changesets.xml"):
        path = root / name
        if not path.exists():
            path.write_text('<?xml version="1.0"?><rss version="2.0"><channel>'
                            '<title>OSWM historical feed unavailable</title>'
                            '<description>No history provider configured for this pilot.</description>'
                            '</channel></rss>')


def finalize():
    """Called only after generation and complete output validation succeed."""
    report = read_json(REPORT)
    registry_path = Path("data/updates/registry.json")
    registry = read_json(registry_path)
    stamp = report["snapshot_timestamp"]
    previous = parse_timestamp(registry.get("Data Fetching"))
    if previous and parse_timestamp(stamp) < previous:
        raise ValueError("Refusing to regress the published acquisition watermark")
    registry["Data Fetching"] = stamp
    # No private cache file paths are part of published provenance.
    public = {k: v for k, v in report.items() if k not in {"file", "downloads"}}
    Path("data/updates/acquisition.json").write_text(json.dumps(public, indent=2) + "\n")
    registry_path.write_text(json.dumps(registry, indent=4) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "install", "render", "finalize"])
    parser.add_argument("--bootstrap-url")
    parser.add_argument("--target-sequence", type=int)
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(bootstrap_url=args.bootstrap_url,
                                 target_sequence=args.target_sequence), indent=2))
    else:
        {"install": install_prepared, "render": render, "finalize": finalize}[args.command]()


if __name__ == "__main__":
    main()
