"""Read-only, cold/warm OSMnx acquisition benchmark for two sandbox nodes."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import traceback
import zlib

import requests

CORE = Path(__file__).absolute().parent.parent
SITES = {
    "curitiba": ("kauevestena/opensidewalkmap_beta", "f71145af01ad6f91d144b79e59a5b93aea5cfa67"),
    "milan": ("opensidewalkmap/milan", "78b5e6af60a031ccd232e8b35eccd23b521e8fd1"),
}
SNAPSHOT = "2026-10-29T21:21:26Z"
AGENT = "OpenSidewalkMap-Sandbox/1.0 (https://github.com/kauevestena/oswm_codebase/pull/62)"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def prepare_node(city, work):
    node = work / "node"
    (node / "data/boundaries").mkdir(parents=True)
    (node / "oswm_codebase").symlink_to(CORE, target_is_directory=True)
    repo, revision = SITES[city]
    inputs = []
    for name in ("config.py", "data/boundaries/polygon.geojson"):
        url = f"https://raw.githubusercontent.com/{repo}/{revision}/{name}"
        r = requests.get(url, timeout=30, headers={"User-Agent": AGENT})
        r.raise_for_status()
        (node / name).write_bytes(r.content)
        inputs.append({"url": url, "bytes": len(r.content), "sha256": hashlib.sha256(r.content).hexdigest()})
    sys.path.insert(0, str(node / "oswm_codebase"))
    import constants as cfg
    return cfg, {"repository": repo, "revision": revision, "inputs": inputs}


def merged_tags(dictionaries):
    result = {}
    for d in dictionaries:
        for key, values in d.items():
            values = [values] if isinstance(values, str) else values
            result.setdefault(key, []).extend(values)
    return {k: list(dict.fromkeys(v)) for k, v in result.items()}


def partition(pedestrian, roads, boundary, cfg):
    pedestrian = pedestrian[pedestrian.geometry.intersects(boundary)].copy()
    pedestrian = pedestrian[~pedestrian.isin(cfg.OTHER_FOOTWAY_EXCLUSION_RULES).any(axis=1)]
    layers = {}
    for name, query in cfg.layer_tags_dict.items():
        match = pedestrian.isin(query).any(axis=1)
        layers[name] = pedestrian[match].copy()
        pedestrian = pedestrian[~match]
    layers["roads_for_completeness"] = roads[roads.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    return layers


def descriptors(layers, cfg):
    """Comparable source identity, normalized geometry and retained OSWM tags."""
    import pandas as pd
    keys = set().union(*(set(v) for v in cfg.columns_to_keep.values()))
    keys.update(["kerb", "kerb:height", "kerb:approach_aid", "crossing", "crossing:signals", "step_count"])
    keys.difference_update(["geometry", "id", "osm_id", "last_update"])
    maps, summaries = {}, {}
    for name, frame in layers.items():
        if "id" not in frame.columns:
            frame = frame.reset_index().rename(columns={"osmid": "id"})
        records = {}
        coverage = Counter()
        for row in frame.to_dict("records"):
            identity = f"{row['element']}:{int(row['id'])}"
            if identity in records:
                raise ValueError("Duplicate source identity: " + identity)
            tags = {}
            for key in sorted(keys):
                value = row.get(key)
                if value is None:
                    continue
                if isinstance(value, str) and value in {"nan", "None", "<NA>"}:
                    continue
                if isinstance(value, str) and value.startswith("["):
                    try:
                        value = ast.literal_eval(value)
                    except (ValueError, SyntaxError):
                        pass
                if isinstance(value, (list, tuple)):
                    value = sorted(map(str, value))
                elif pd.isna(value):
                    continue
                else:
                    value = str(value)
                tags[key] = value
                coverage[key] += 1
            records[identity] = {"g": hashlib.sha256(row["geometry"].normalize().wkb).hexdigest(), "a": digest(tags)}
        maps[name] = records
        summaries[name] = {"count": len(records), "ids_sha256": digest(sorted(records)),
                           "geometry_and_tags_sha256": digest(records), "field_coverage": dict(coverage)}
    return maps, summaries


class Meter:
    """Count encoded HTTP response bodies, including failed attempts/metadata.

    Explicit undecoded raw streams handle both length-delimited and chunked
    responses. Headers/TLS/framing are excluded. Decoded JSON is separate.
    """
    def __init__(self):
        self.events = []
        self.queries = Counter()
        self.phase = ""

    def __enter__(self):
        self.original = requests.Session.send
        meter = self
        def send(session, request, **kwargs):
            if len(meter.events) >= 40:
                raise RuntimeError("HTTP request budget exhausted")
            body = request.body or b""
            body = body.encode() if isinstance(body, str) else body
            key = request.url, hashlib.sha256(body).hexdigest()
            interpreter = "/interpreter" in request.url
            if interpreter:
                meter.queries[key] += 1
                if meter.queries[key] > 1:
                    raise RuntimeError("Repeated identical interpreter attempt suppressed by sandbox bound")
            start = time.monotonic()
            event = {"phase": meter.phase, "method": request.method,
                     "url": request.url.split("?", 1)[0], "request_body_bytes": len(body)}
            meter.events.append(event)
            try:
                # raw.tell() is zero for some urllib3 chunked-gzip responses.
                # Read undecoded bytes explicitly before restoring Response's
                # usual decoded .content behavior for OSMnx.
                request.headers["Accept-Encoding"] = "gzip, deflate"
                kwargs["stream"] = True
                response = meter.original(session, request, **kwargs)
                if getattr(response, "_oswm_source_counted", False):
                    event.update({"redirect_reuse": True, "status": response.status_code,
                                  "encoded_body_bytes": 0, "decoded_body_bytes": 0,
                                  "seconds": round(time.monotonic() - start, 3)})
                    return response  # destination was metered by nested send
                event["status"] = response.status_code
                event["encoded_body_bytes"] = 0
                chunks = []
                for chunk in response.raw.stream(1024**2, decode_content=False):
                    event["encoded_body_bytes"] += len(chunk)
                    chunks.append(chunk)
                encoded = b"".join(chunks)
                encoding = response.headers.get("Content-Encoding", "identity")
                if encoding == "gzip":
                    content = gzip.decompress(encoded)
                elif encoding == "deflate":
                    try: content = zlib.decompress(encoded)
                    except zlib.error: content = zlib.decompress(encoded, -zlib.MAX_WBITS)
                elif encoding in ("identity", ""):
                    content = encoded
                else:
                    raise ValueError("Unsupported content encoding: " + encoding)
                response._content = content
                response._content_consumed = True
                response._oswm_source_counted = True
                event.update({"body_complete": True,
                              "decoded_body_bytes": len(content), "content_encoding": response.headers.get("Content-Encoding", "identity"),
                              "content_length_header": response.headers.get("Content-Length"),
                              "seconds": round(time.monotonic() - start, 3)})
                response.raise_for_status()  # avoid OSMnx's recursive 429/504 retry
                if interpreter:
                    payload = response.json()
                    event["osm_base_timestamp"] = payload.get("osm3s", {}).get("timestamp_osm_base")
                    event["osm_elements"] = len(payload.get("elements", []))
                    if payload.get("remark"):
                        raise ValueError("Overpass remark (partial/error response): " + payload["remark"])
                    base = event["osm_base_timestamp"]
                    if base and SNAPSHOT != "live" and base < SNAPSHOT:
                        raise ValueError("Overpass database watermark predates the requested snapshot")
                return response
            except Exception as exc:
                event.update({"error": type(exc).__name__ + ": " + str(exc)[:500],
                              "seconds": round(time.monotonic() - start, 3)})
                raise
        requests.Session.send = send
        return self

    def __exit__(self, *unused):
        requests.Session.send = self.original

    def summary(self):
        return {"http_requests": len(self.events),
                "interpreter_requests": sum("/interpreter" in e["url"] for e in self.events),
                "encoded_response_body_bytes": sum(e.get("encoded_body_bytes", 0) for e in self.events),
                "decoded_response_body_bytes": sum(e.get("decoded_body_bytes", 0) for e in self.events),
                "byte_total_is_lower_bound": any(e.get("redirect_reuse") or ("error" in e and not e.get("body_complete")) for e in self.events),
                "events": self.events}


def deadline(signum, frame):
    raise TimeoutError("Sandbox variant elapsed-time budget exhausted")


def compact_features_query(polygon_coord_str, tags):
    """Same n/w/r tag union and down-reference closure, expanded once."""
    from osmnx import _overpass
    clauses = []
    for key, values in tags.items():
        if values is True:
            condition = '[' + json.dumps(key) + ']'
        else:
            values = [values] if isinstance(values, str) else values
            pattern = "^(" + "|".join(re.escape(v) for v in values) + ")$"
            condition = '[' + json.dumps(key) + '~' + json.dumps(pattern) + ']'
        clauses.append('nwr' + condition + '(poly:' + json.dumps(polygon_coord_str) + ');')
    return _overpass._make_overpass_settings() + ';(' + ''.join(clauses) + ');(._;>;);out;'


def osm_benchmark(cfg, work, report, save, variants):
    import osmnx as ox
    import geopandas as gpd
    from shapely.geometry import box
    from replication_pipeline import ROAD_TYPES
    from osmnx import _overpass
    original_builder = _overpass._create_overpass_features_query
    boundary = gpd.read_file(cfg.boundaries_geojson_path).geometry.union_all()
    bbox = box(*boundary.bounds)
    ped_tags = merged_tags(cfg.layer_tags_dict.values())
    union_tags = merged_tags([ped_tags, {"highway": ROAD_TYPES}])
    report.update({"osmnx_version": ox.__version__, "boundary_bounds": list(boundary.bounds),
                   "snapshot": SNAPSHOT, "pedestrian_tags": ped_tags, "combined_tags": union_tags,
                   "variants": [], "measurement": "encoded HTTP response-body bytes, excluding headers/TLS; includes status/DNS/error bodies"})
    ox.settings.http_user_agent = AGENT
    ox.settings.http_referer = "https://github.com/kauevestena/oswm_codebase/pull/62"
    ox.settings.requests_timeout = 45
    ox.settings.overpass_settings = '[out:json][timeout:{timeout}]{maxsize}'
    if SNAPSHOT != "live":
        ox.settings.overpass_settings += '[date:"' + SNAPSHOT + '"]'
    ox.settings.use_cache = True
    ox.settings.log_console = False
    endpoints = ["https://overpass.private.coffee/api", "https://overpass-api.de/api"]
    signal.signal(signal.SIGALRM, deadline)
    for variant in variants:
        _overpass._create_overpass_features_query = compact_features_query if variant == "compact_combined_one_query" else original_builder
        item = {"variant": variant, "attempts": []}
        report["variants"].append(item)
        folder = work / variant
        folder.mkdir()
        ox.settings.cache_folder = str(folder / "http-cache")
        active_meter = None
        def fetch():
            if variant in ("combined_one_query", "compact_combined_one_query"):
                active_meter.phase = variant + ":combined"
                combined = ox.features_from_polygon(bbox, union_tags)
                roads = combined[combined["highway"].isin(ROAD_TYPES)].copy()
                return partition(combined, roads, boundary, cfg)
            active_meter.phase = variant + ":pedestrian"
            # Retain the exact city predicate in partition(), while avoiding
            # repeating thousands of boundary vertices in every tag clause.
            ped = ox.features_from_polygon(bbox, ped_tags)
            active_meter.phase = variant + ":roads"
            roads = ox.features_from_polygon(bbox, {"highway": ROAD_TYPES})
            roads = roads[roads["highway"].isin(ROAD_TYPES)].copy()
            return partition(ped, roads, boundary, cfg)
        for endpoint in endpoints:
            ox.settings.overpass_url = endpoint
            # Private.coffee documents no rate-limit slots. Polling its status
            # recursively is not required by that operator's usage policy.
            ox.settings.overpass_rate_limit = endpoint != "https://overpass.private.coffee/api"
            attempt = {"endpoint": endpoint, "rate_limit_status_polling": ox.settings.overpass_rate_limit}
            item["attempts"].append(attempt)
            start = time.monotonic()
            with Meter() as meter:
                active_meter = meter
                meter.phase = variant + ":cold"
                try:
                    signal.alarm(180)
                    layers = fetch()
                    signal.alarm(0)
                    attempt["acquisition_seconds"] = round(time.monotonic() - start, 3)
                    maps, summaries = descriptors(layers, cfg)
                    item["layers"] = summaries
                    target = folder / "descriptors.json.gz"
                    with gzip.open(target, "wt") as stream:
                        json.dump(maps, stream, sort_keys=True, separators=(",", ":"))
                    item["descriptor_file"] = str(target.relative_to(work))
                    attempt["success"] = True
                except Exception as exc:
                    signal.alarm(0)
                    attempt.update({"success": False, "error": type(exc).__name__ + ": " + str(exc),
                                    "acquisition_seconds": round(time.monotonic() - start, 3)})
                finally:
                    attempt["http"] = meter.summary()
                    save()
            if attempt["success"]:
                # Same-date warm cache is a re-read, not a fresh daily update.
                start = time.monotonic()
                with Meter() as warm:
                    active_meter = warm
                    warm.phase = variant + ":warm_same_snapshot"
                    try:
                        signal.alarm(180)
                        cached = fetch()
                        signal.alarm(0)
                        _, warm_summary = descriptors(cached, cfg)
                        item["warm_same_snapshot"] = {"seconds": round(time.monotonic() - start, 3),
                                                     "layers_equal": warm_summary == item["layers"], "http": warm.summary()}
                    except Exception as exc:
                        signal.alarm(0)
                        item["warm_same_snapshot"] = {"error": str(exc), "http": warm.summary()}
                break
        item["success"] = any(a["success"] for a in item["attempts"])
        item["total_encoded_body_bytes_including_failures"] = sum(a["http"]["encoded_response_body_bytes"] for a in item["attempts"])
        item["cache_json_bytes"] = sum(p.stat().st_size for p in folder.rglob("*.json"))
        save()
        print(json.dumps({"city": report["city"], **{k: item[k] for k in ("variant", "success", "total_encoded_body_bytes_including_failures")}}), flush=True)
    _overpass._create_overpass_features_query = original_builder


def main():
    global SNAPSHOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", choices=SITES, required=True)
    parser.add_argument("--provider", choices=["osmnx", "baseline"], default="osmnx")
    parser.add_argument("--pbf", type=Path)
    parser.add_argument("--snapshot", default="live", help="live or an explicit UTC timestamp")
    parser.add_argument("--variants", nargs="+", choices=["bbox_two_queries", "combined_one_query", "compact_combined_one_query"],
                        default=["combined_one_query", "compact_combined_one_query"])
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    SNAPSHOT = args.snapshot
    work = args.work.resolve()
    if work.exists() and any(work.iterdir()):
        raise ValueError("Use a new empty sandbox")
    work.mkdir(parents=True, exist_ok=True)
    pbf = args.pbf.resolve() if args.pbf else None
    report = {"city": args.city, "provider": args.provider, "sandbox_only": True,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "code_revision": subprocess.check_output(["git", "-C", CORE, "rev-parse", "HEAD"], text=True).strip()}
    report["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def save():
        (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    save()
    try:
        cfg, provenance = prepare_node(args.city, work)
        report["node_inputs"] = provenance
        save()
        if args.provider == "osmnx":
            osm_benchmark(cfg, work, report, save, args.variants)
        else:
            if pbf is None:
                raise ValueError("A baseline requires --pbf")
            import osmium
            with osmium.io.Reader(str(pbf)) as reader:
                header = reader.header()
                report["pbf_header"] = {k: header.get(k) for k in (
                    "osmosis_replication_timestamp", "osmosis_replication_sequence_number", "osmosis_replication_base_url")}
            report["snapshot"] = report["pbf_header"]["osmosis_replication_timestamp"]
            if not report["snapshot"] or (SNAPSHOT != "live" and report["snapshot"] != SNAPSHOT):
                raise ValueError("PBF header does not identify the requested source cutoff")
            from replication_pipeline import extract_city
            started = time.monotonic()
            maps, summaries = descriptors(extract_city(pbf, cfg), cfg)
            report.update({"layers": summaries, "seconds": round(time.monotonic() - started, 3),
                           "pbf_bytes": pbf.stat().st_size, "pbf_sha256": hashlib.file_digest(pbf.open('rb'), 'sha256').hexdigest()})
            with gzip.open(work / "descriptors.json.gz", "wt") as stream:
                json.dump(maps, stream, sort_keys=True, separators=(",", ":"))
    except Exception:
        report["fatal_error"] = traceback.format_exc()
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
        print("SOURCE_BENCHMARK_REPORT=" + json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
