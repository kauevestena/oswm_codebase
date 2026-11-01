"""Sandbox: validate Overpass query-result deltas, or use full acquisition.

This stores sanitized OSM primitives, not only modified features or version IDs.
It never installs data into a node or runs a publisher. Full snapshots are test
oracles; their traffic is reported separately from an operational delta.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET

import requests

import source_benchmark as bench

KINDS = {"node", "way", "relation"}
T0 = "2026-10-31T00:00:00Z"
T1 = "2026-11-01T00:00:00Z"


class InvalidSource(RuntimeError):
    pass


def stamp(value):
    result = datetime.fromisoformat(value.replace("\\:", ":").replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise InvalidSource("Source timestamps require a timezone")
    return result


def encoded(records):
    return json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def signature(records):
    return hashlib.sha256(encoded(records)).hexdigest()


def key(obj):
    return f"{obj['type']}:{obj['id']}"


def primitive(obj):
    """Retain semantic OSM data; discard uid/user/changeset and inline geometry.

    Geometry is reconstructed from the full reference graph. Versions are not
    an update gate: the same way version can acquire different coordinates.
    """
    kind = obj["type"]
    identifier = int(obj["id"])
    if kind not in KINDS or identifier <= 0:
        raise InvalidSource("Invalid OSM identity")
    result = {"type": kind, "id": identifier, "tags": dict(obj.get("tags", {}))}
    if kind == "node":
        lat, lon = float(obj["lat"]), float(obj["lon"])
        if not math.isfinite(lat + lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise InvalidSource("Invalid node position")
        result.update(lat=lat, lon=lon)
    elif kind == "way":
        result["nodes"] = [int(n) for n in obj["nodes"]]
    else:
        result["members"] = [{"type": m["type"], "ref": int(m["ref"]), "role": m.get("role", "")}
                             for m in obj["members"]]
        if any(m["type"] not in KINDS for m in result["members"]):
            raise InvalidSource("Invalid relation member kind")
    return result


def xml_primitive(element):
    obj = {"type": element.tag, "id": element.get("id"),
           "tags": {t.get("k"): t.get("v") for t in element.findall("tag")}}
    if element.tag == "node":
        obj.update(lat=element.get("lat"), lon=element.get("lon"))
    elif element.tag == "way":
        obj["nodes"] = [nd.get("ref") for nd in element.findall("nd")]
    elif element.tag == "relation":
        obj["members"] = [dict(m.attrib) for m in element.findall("member")]
    return primitive(obj)


def validate(records):
    if not records:
        raise InvalidSource("Unexpected empty city source")
    missing = []
    for identity, obj in records.items():
        if identity != key(obj):
            raise InvalidSource("Record key/identity mismatch")
        if obj["type"] == "way":
            if not obj["nodes"]:
                raise InvalidSource("Empty way")
            missing.extend(f"node:{n}" for n in obj["nodes"] if f"node:{n}" not in records)
        elif obj["type"] == "relation":
            missing.extend(f"{m['type']}:{m['ref']}" for m in obj["members"] if f"{m['type']}:{m['ref']}" not in records)
    if missing:
        raise InvalidSource(f"Missing referenced objects ({len(missing)}): {sorted(set(missing))[:15]}")


def full_records(payload, target):
    if payload.get("remark"):
        raise InvalidSource(payload["remark"])
    available = payload.get("osm3s", {}).get("timestamp_osm_base")
    if not available or stamp(available) < stamp(target):
        raise InvalidSource("Full-source watermark precedes requested cutoff")
    records = {}
    for element in payload["elements"]:
        item = primitive(element)
        if key(item) in records:
            raise InvalidSource("Duplicate full-source identity")
        records[key(item)] = item
    validate(records)
    return records


def parse_adiff(content, target):
    root = ET.fromstring(content)
    if root.tag not in {"osm", "osm-adiff"}:
        raise InvalidSource("Unexpected augmented-diff root")
    remark = root.find("remark")
    if remark is not None:
        raise InvalidSource("Overpass remark: " + "".join(remark.itertext()))
    meta = root.find("meta")
    if meta is None or not meta.get("osm_base") or stamp(meta.get("osm_base")) < stamp(target):
        raise InvalidSource("Delta watermark precedes requested cutoff")
    if any(child.tag not in {"note", "meta", "action"} for child in root):
        raise InvalidSource("A full snapshot is not an augmented diff")
    actions, seen = [], set()
    statistics = Counter()
    def one(parent):
        if parent is None:
            raise InvalidSource("Missing action side")
        children = [c for c in parent if c.tag in KINDS]
        if len(children) != 1:
            raise InvalidSource("Action must describe one OSM object")
        return children[0]
    for action in root.findall("action"):
        kind = action.get("type")
        if kind not in {"create", "modify", "delete"}:
            raise InvalidSource("Unsupported augmented-diff action: " + str(kind))
        old_xml = None if kind == "create" else one(action.find("old"))
        new_xml = (one(action.find("new")) if action.find("new") is not None
                   else one(action) if kind == "create" else None)
        if kind != "delete" and new_xml is None:
            raise InvalidSource("Missing new side of augmented-diff action")
        old = xml_primitive(old_xml) if old_xml is not None else None
        new = xml_primitive(new_xml) if new_xml is not None and kind != "delete" else None
        identity = key(old or new)
        if identity in seen:
            raise InvalidSource("Duplicate augmented-diff identity: " + identity)
        seen.add(identity)
        if new is not None and old is not None and key(new) != identity:
            raise InvalidSource("Action changes identity")
        if new_xml is not None and (new_xml.tag + ":" + str(int(new_xml.get("id")))) != identity:
            raise InvalidSource("Delete/new identity mismatch")
        if kind != "delete" and new_xml is not None and new_xml.get("visible") == "false":
            raise InvalidSource("Non-delete action contains an invisible object")
        statistics[kind] += 1
        if kind == "delete":
            statistics["left_query_but_visible" if new_xml is not None and new_xml.get("visible") == "true"
                       else "osm_deleted" if new_xml is not None and new_xml.get("visible") == "false"
                       else "delete_without_visibility"] += 1
        if kind == "modify" and old_xml.get("version") == new_xml.get("version"):
            statistics["same_version_modifies"] += 1
        actions.append({"action": kind, "key": identity, "old": old, "new": new})
    return actions, dict(statistics)


def apply_adiff(base, actions):
    result = dict(base)
    for action in actions:
        identity, kind = action["key"], action["action"]
        if kind == "create":
            if identity in base:
                raise InvalidSource("Create collides with existing query result")
        elif identity not in base or base[identity] != action["old"]:
            raise InvalidSource("Delta old data does not match cached baseline: " + identity)
        if kind == "delete":
            del result[identity]  # visible=true still means it LEFT this query
        else:
            result[identity] = action["new"]
    validate(result)
    return result


class SnapshotCache:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def load(self, query_id):
        pointer = json.loads((self.path / "current.json").read_text())
        if pointer["query_id"] != query_id:
            raise InvalidSource("Query/configuration changed; bootstrap required")
        data = gzip.decompress((self.path / pointer["file"]).read_bytes())
        if hashlib.sha256(data).hexdigest() != pointer["sha256"]:
            raise InvalidSource("Source-cache checksum mismatch")
        records = json.loads(data)
        validate(records)
        return records, pointer

    def commit(self, records, cutoff, query_id):
        validate(records)
        raw = encoded(records)
        sha = hashlib.sha256(raw).hexdigest()
        name = f"source-{sha}.json.gz"
        destination = self.path / name
        candidate = self.path / ".candidate.gz"
        candidate.write_bytes(gzip.compress(raw, compresslevel=6, mtime=0))
        os.replace(candidate, destination)
        pointer = {"file": name, "sha256": sha, "cutoff": cutoff, "query_id": query_id,
                   "compressed_bytes": destination.stat().st_size, "objects": len(records)}
        pending = self.path / ".current.json"
        pending.write_text(json.dumps(pointer, indent=2) + "\n")
        os.replace(pending, self.path / "current.json")
        return pointer


def acquire(base, pointer, query_id, start, end, delta_supplier, full_supplier):
    """Prepare a target without advancing any checkpoint or publication marker."""
    if pointer["query_id"] == query_id and pointer["cutoff"] == end:
        return base, {"mode": "idempotent_cached_target", "needs_commit": False}
    try:
        if pointer["query_id"] != query_id or pointer["cutoff"] != start or stamp(end) <= stamp(start):
            raise InvalidSource("Baseline query/window mismatch")
        actions, statistics = parse_adiff(delta_supplier(), end)
        return apply_adiff(base, actions), {"mode": "adiff", "actions": statistics, "needs_commit": True}
    except Exception as exc:
        fresh = full_supplier(end)
        validate(fresh)
        return fresh, {"mode": "full_fallback", "delta_error": type(exc).__name__ + ": " + str(exc), "needs_commit": True}


def local_changes(before, after, configuration_changed=False):
    if before.keys() != after.keys():
        raise InvalidSource("Missing raw layer in local change detection")
    changes = {}
    for layer, new in after.items():
        old = before[layer]
        shared = new.keys() & old.keys()
        changes[layer] = {"added": len(new.keys() - old.keys()), "removed": len(old.keys() - new.keys()),
                          "modified": sum(new[i] != old[i] for i in shared)}
    return {"needs_rebuild": configuration_changed or any(any(x.values()) for x in changes.values()),
            "configuration_changed": configuration_changed, "layers": changes}


def query_body(bbox, tags):
    """Only area relations become features; all nested dependencies are retained."""
    west, south, east, north = bbox
    bounds = f"({south},{west},{north},{east})"
    clauses = []
    for name, values in tags.items():
        pattern = "^(" + "|".join(re.escape(v) for v in values) + ")$"
        condition = '[' + json.dumps(name) + '~' + json.dumps(pattern) + ']'
        for kind in ("node", "way", "relation"):
            area = '["type"~"^(multipolygon|boundary)$"]' if kind == "relation" else ""
            clauses.append(kind + area + condition + bounds + ";")
    return "(" + "".join(clauses) + ");(._;>>;);"


class Provider:
    def __init__(self, body, report, save):
        self.body, self.report, self.save = body, report, save
        self.full = {}
        self.events = []

    def fetch(self, query, response_format, phase, target, timeout):
        last_error = None
        for endpoint in ("https://overpass-api.de/api", "https://overpass.private.coffee/api"):
            try:
                return self.fetch_once(query, response_format, phase, target, timeout, endpoint)
            except Exception as exc:
                last_error = exc
        raise last_error

    def fetch_once(self, query, response_format, phase, target, timeout, endpoint):
        outcome = {"phase": phase, "endpoint": endpoint,
                   "query_sha256": hashlib.sha256(query.encode()).hexdigest(), "target": target}
        self.events.append(outcome)
        began = time.monotonic()
        # One interpreter request per endpoint, never OSMnx's recursive retry.
        import osmnx as ox
        from osmnx import _overpass
        ox.settings.overpass_rate_limit = True
        ox.settings.requests_timeout = 15
        signal.signal(signal.SIGALRM, bench.deadline)
        bench.SNAPSHOT = "live"  # explicit cutoff validation is performed below
        try:
            signal.alarm(timeout + 90)
            with bench.Meter(response_format=response_format) as meter:
                meter.phase = phase
                try:
                    try:
                        pause = _overpass._get_overpass_pause(endpoint)
                    except requests.RequestException as exc:
                        # /status can fail independently of /interpreter. A
                        # single bounded query after a short pause still obeys
                        # interpreter HTTP 429/504, with no recursive retry.
                        outcome["status_warning"] = type(exc).__name__ + ": " + str(exc)
                        pause = 10
                    if pause > 45:
                        raise InvalidSource("No public query slot within the sandbox wait budget")
                    time.sleep(pause)
                    response = requests.post(endpoint + "/interpreter", data={"data": query},
                                             headers={"User-Agent": bench.AGENT}, timeout=(15, timeout + 20))
                    content = response.content
                    watermark = next((e.get("osm_base_timestamp") for e in reversed(meter.events)
                                      if e.get("osm_base_timestamp")), None)
                    if not watermark or stamp(watermark) < stamp(target):
                        raise InvalidSource("Response does not cover requested source cutoff")
                    outcome.update({"success": True, "watermark": watermark,
                                    "response_sha256": hashlib.sha256(content).hexdigest()})
                finally:
                    outcome["http"] = meter.summary()
        except Exception as exc:
            outcome.update({"success": False, "error": type(exc).__name__ + ": " + str(exc)})
            raise
        finally:
            signal.alarm(0)
            outcome["seconds"] = round(time.monotonic() - began, 3)
            self.report["requests"] = self.events
            self.save()
        return content

    def snapshot(self, cutoff, reason="control"):
        if cutoff not in self.full:
            query = f'[out:json][timeout:45][date:"{cutoff}"];{self.body}out body;'
            content = self.fetch(query, "json", "full:" + reason + ":" + cutoff, cutoff, 45)
            self.full[cutoff] = full_records(json.loads(content), cutoff)
        return self.full[cutoff]

    def delta(self, start, end):
        query = f'[out:xml][timeout:60][adiff:"{start}","{end}"];{self.body}out meta geom;'
        return self.fetch(query, "xml", "adiff", end, 60)


def views(records, cfg, boundary, tags):
    from osmnx import features as feature_module
    from shapely.geometry import box
    from replication_pipeline import ROAD_TYPES
    elements = sorted(records.values(), key=lambda e: ({"node": 0, "way": 1, "relation": 2}[e["type"]], e["id"]))
    frame = feature_module._create_gdf(iter([{"elements": elements}]), box(*boundary.bounds), tags)
    roads = frame[frame["highway"].isin(ROAD_TYPES)].copy()
    return bench.descriptors(bench.partition(frame, roads, boundary, cfg), cfg)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", choices=bench.SITES, required=True)
    parser.add_argument("--start", default=T0)
    parser.add_argument("--end", default=T1)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    if not stamp(args.start) < stamp(args.end) < datetime.now(timezone.utc):
        raise ValueError("Require an increasing historical window")
    work = args.work.resolve()
    if work.exists() and any(work.iterdir()):
        raise ValueError("Use a new empty sandbox directory")
    work.mkdir(parents=True, exist_ok=True)
    report = {"city": args.city, "sandbox_only": True, "start": args.start, "end": args.end,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "code_revision": subprocess.check_output(["git", "-C", bench.CORE, "rev-parse", "HEAD"], text=True).strip(),
              "publication": "none; source cache and staged data remain in disposable sandbox"}
    def save():
        (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    save()
    try:
        cfg, inputs = bench.prepare_node(args.city, work)
        report["node_inputs"] = inputs
        import geopandas as gpd
        from replication_pipeline import ROAD_TYPES
        boundary = gpd.read_file(cfg.boundaries_geojson_path).geometry.union_all()
        tags = bench.merged_tags([*cfg.layer_tags_dict.values(), {"highway": ROAD_TYPES}])
        body = query_body(boundary.bounds, tags)
        configuration = Path("config.py").read_bytes() + Path(cfg.boundaries_geojson_path).read_bytes()
        query_id = hashlib.sha256(body.encode() + configuration).hexdigest()
        report.update({"query_id": query_id, "scope": "tagged nodes/ways/area relations in city bbox; transitive reference closure",
                       "bbox": list(boundary.bounds), "tags": tags})
        provider = Provider(body, report, save)
        print(json.dumps({"city": args.city, "phase": "baseline full snapshot"}), flush=True)
        before = provider.snapshot(args.start, "bootstrap")
        cache = SnapshotCache(work / "source-cache")
        seed = cache.commit(before, args.start, query_id)
        before, pointer = SnapshotCache(work / "source-cache").load(query_id)
        report["baseline"] = {**seed, "serialized_cache_reloaded": True}
        before_maps, before_summary = views(before, cfg, boundary, tags)
        report["baseline_layers"] = before_summary
        save()
        print(json.dumps({"city": args.city, "phase": "augmented diff"}), flush=True)
        candidate, acquisition = acquire(before, pointer, query_id, args.start, args.end,
                                         lambda: provider.delta(args.start, args.end),
                                         lambda t: provider.snapshot(t, "fallback"))
        report["acquisition"] = acquisition
        save()
        print(json.dumps({"city": args.city, "phase": "independent target full snapshot"}), flush=True)
        target = provider.snapshot(args.end, "independent_oracle")
        target_maps, target_summary = views(target, cfg, boundary, tags)
        # Fault injection reuses the real full target: no additional public
        # query, and it is not counted as evidence of a second live download.
        def injected_timeout():
            raise requests.ReadTimeout("Injected delta failure")
        recovered, recovery = acquire(before, pointer, query_id, args.start, args.end,
                                      injected_timeout, lambda t: provider.snapshot(t, "fault_injection"))
        report["forced_delta_failure"] = {**recovery, "full_target_equal": recovered == target,
            "checkpoint_unchanged_before_commit": cache.load(query_id)[1] == pointer,
            "full_response_reused_from_oracle": True}
        same = candidate == target
        report["raw_query_result_parity"] = {"equal": same, "candidate_sha256": signature(candidate),
                                            "control_sha256": signature(target),
                                            "candidate_objects": len(candidate), "control_objects": len(target),
                                            "missing_sample": sorted(target.keys() - candidate.keys())[:20],
                                            "extra_sample": sorted(candidate.keys() - target.keys())[:20],
                                            "modified_sample": [k for k in target if k in candidate and target[k] != candidate[k]][:20]}
        if same:
            # Identical complete primitives are a stronger equality than derived
            # descriptors. Render the target once through the real OSWM contract.
            report["layer_parity"] = {"equal": True, "method": "canonical primitives identical; common deterministic OSWM extraction", "layers": target_summary}
        else:
            candidate_maps, candidate_summary = views(candidate, cfg, boundary, tags)
            report["layer_parity"] = {"equal": candidate_maps == target_maps, "candidate": candidate_summary, "control": target_summary}
        if acquisition["mode"] == "adiff" and not same:
            report["oracle_rejected_delta"] = True
            candidate = target  # sandbox recovery, not a claimed delta success
        changes = local_changes(before_maps, target_maps)
        report["daily_full_plus_local_detection"] = {**changes,
            "same_snapshot_repeat_needs_rebuild": local_changes(target_maps, target_maps)["needs_rebuild"],
            "note": "conservative rebuild gate; selective downstream product generation is not tested"}
        final = cache.commit(candidate, args.end, query_id)
        report["final_checkpoint"] = final
        _, repeated = acquire(candidate, final, query_id, args.start, args.end,
                              lambda: (_ for _ in ()).throw(AssertionError("replay must not fetch a delta")),
                              lambda t: (_ for _ in ()).throw(AssertionError("replay must not fetch a full snapshot")))
        report["idempotent_repeat"] = repeated
        delta = next((r for r in provider.events if r["phase"] == "adiff" and r.get("success")), None)
        full_target = next(r for r in provider.events if r["phase"].startswith("full:") and r["target"] == args.end and r.get("success"))
        report["traffic"] = {"baseline_cache_bytes": seed["compressed_bytes"],
            "successful_delta_response_bytes": delta["http"]["encoded_response_body_bytes"] if delta else None,
            "target_full_response_bytes": full_target["http"]["encoded_response_body_bytes"],
            "hosted_incoming_cache_plus_delta_bytes": seed["compressed_bytes"] + delta["http"]["encoded_response_body_bytes"] if delta else None,
            "cache_upload_bytes_additional": final["compressed_bytes"],
            "caveat": "full controls are experiment overhead; headers/TLS and dependency setup excluded; API errors retained separately"}
        report["delta_trial_passed"] = acquisition["mode"] == "adiff" and same and report["layer_parity"]["equal"]
        report["daily_full_trial_passed"] = True
        report["success"] = True
    except Exception:
        report["fatal_error"] = traceback.format_exc()
        report["success"] = False
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
        print("CHANGE_QUERY_REPORT=" + json.dumps(report), flush=True)


if __name__ == "__main__": main()
