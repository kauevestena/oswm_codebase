"""Replay Overpass changes from a real persisted live seed, with a full oracle.

The historical 24h probes can fail to bootstrap on public servers. This separate
experiment restores a successful live seed and tests the same update protocol
over the actual elapsed interval, without claiming it is a 24h replay.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import traceback

import requests

import change_query_probe as p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", required=True, choices=p.bench.SITES)
    parser.add_argument("--seed", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    seed_path, work = args.seed.resolve(), args.work.resolve()
    if work.exists() and any(work.iterdir()):
        raise ValueError("Require a new sandbox")
    work.mkdir(parents=True, exist_ok=True)
    report = {"city": args.city, "sandbox_only": True,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "code_revision": subprocess.check_output(["git", "-C", p.bench.CORE, "rev-parse", "HEAD"], text=True).strip(),
              "seed_workflow_run": 41343838674,
              "publication": "none; persisted source graph remains a disposable workflow artifact"}
    def save():
        (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    save()
    try:
        original = json.loads((seed_path / "report.json").read_text())
        if not original.get("success") or original["city"] != args.city:
            raise p.InvalidSource("The earlier experiment did not produce a valid city seed")
        if original["code_revision"] != "66bd4556d2161c5164284a907080c5348cfa435e":
            raise p.InvalidSource("Unexpected seed provenance")
        cfg, inputs = p.bench.prepare_node(args.city, work)
        import geopandas as gpd
        from replication_pipeline import ROAD_TYPES
        boundary = gpd.read_file(cfg.boundaries_geojson_path).geometry.union_all()
        tags = p.bench.merged_tags([*cfg.layer_tags_dict.values(), {"highway": ROAD_TYPES}])
        body = p.query_body(boundary.bounds, tags)
        configuration = Path("config.py").read_bytes() + Path(cfg.boundaries_geojson_path).read_bytes()
        query_id = hashlib.sha256(body.encode() + configuration).hexdigest()
        before, pointer = p.SnapshotCache(seed_path / "source-cache").load(query_id)
        start = pointer["cutoff"]
        report.update({"node_inputs": inputs, "query_id": query_id, "start": start, "end": start,
                       "seed": pointer, "scope": original["scope"]})
        provider = p.Provider(body, report, save)
        # Read a fresh live snapshot FIRST to fix an independent oracle cutoff.
        # The following adiff has explicit start/end timestamps, not 'now'.
        print(json.dumps({"city": args.city, "phase": "fresh independent live oracle"}), flush=True)
        target, end = provider.live()
        if p.stamp(end) <= p.stamp(start):
            raise p.InvalidSource("No later source watermark: replay interval did not advance")
        report.update({"end": end, "interval_seconds": (p.stamp(end) - p.stamp(start)).total_seconds(),
                       "full_24h_replay": False,
                       "interval_note": "elapsed between two live snapshots, not a validated overnight update"})
        before_maps, before_summary = p.views(before, cfg, boundary, tags)
        target_maps, target_summary = p.views(target, cfg, boundary, tags)
        print(json.dumps({"city": args.city, "phase": "apply explicit-cutoff delta to restored cache"}), flush=True)
        candidate, acquisition = p.acquire(before, pointer, query_id, start, end,
                                           lambda: provider.delta(start, end), lambda t: target)
        same = candidate == target
        report["acquisition"] = acquisition
        report["raw_query_result_parity"] = {"equal": same,
            "candidate_sha256": p.signature(candidate), "control_sha256": p.signature(target),
            "candidate_objects": len(candidate), "control_objects": len(target),
            "missing_sample": sorted(target.keys() - candidate.keys())[:20],
            "extra_sample": sorted(candidate.keys() - target.keys())[:20],
            "modified_sample": [k for k in target if k in candidate and target[k] != candidate[k]][:20]}
        if same:
            report["layer_parity"] = {"equal": True,
                "method": "identical complete primitives; common deterministic OSWM extraction", "layers": target_summary}
        else:
            candidate_maps, candidate_summary = p.views(candidate, cfg, boundary, tags)
            report["layer_parity"] = {"equal": candidate_maps == target_maps,
                                     "candidate": candidate_summary, "control": target_summary}
        if p.SnapshotCache(seed_path / "source-cache").load(query_id)[1] != pointer:
            raise p.InvalidSource("Replay modified the immutable seed")
        def injected_timeout(): raise requests.ReadTimeout("Injected delta failure")
        recovered, recovery = p.acquire(before, pointer, query_id, start, end, injected_timeout, lambda t: target)
        report["forced_delta_failure"] = {**recovery, "full_target_equal": recovered == target,
            "baseline_unchanged": before == p.SnapshotCache(seed_path / "source-cache").load(query_id)[0],
            "full_response_reused_from_oracle": True}
        report["daily_full_plus_local_detection"] = {**p.local_changes(before_maps, target_maps),
            "same_snapshot_repeat_needs_rebuild": p.local_changes(target_maps, target_maps)["needs_rebuild"],
            "baseline_layers": before_summary, "target_layers": target_summary}
        cache = p.SnapshotCache(work / "source-cache")
        final = cache.commit(target, end, query_id)  # always retain the verified target
        reloaded, final = cache.load(query_id)
        def no_fetch(): raise AssertionError("Target replay must not request data")
        _, repeat = p.acquire(reloaded, final, query_id, start, end, no_fetch, lambda t: no_fetch())
        report["final_checkpoint"], report["idempotent_repeat"] = final, repeat
        delta = next((r for r in provider.events if r["phase"] == "adiff" and r.get("success")), None)
        full = next(r for r in provider.events if r["phase"] == "full:live" and r.get("success"))
        delta_bytes = delta["http"]["encoded_response_body_bytes"] if delta else None
        report["traffic"] = {"baseline_cache_bytes": pointer["compressed_bytes"],
            "successful_delta_response_bytes": delta_bytes,
            "target_full_response_bytes": full["http"]["encoded_response_body_bytes"],
            "hosted_incoming_cache_plus_delta_bytes": pointer["compressed_bytes"] + delta_bytes if delta else None,
            "cache_upload_bytes_additional": final["compressed_bytes"],
            "caveat": "cache payload estimate excludes artifact ZIP framing/metadata; errors and full oracle are separate overhead"}
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
        print("CACHED_CHANGE_REPORT=" + json.dumps(report), flush=True)


if __name__ == "__main__": main()
