"""Non-publishing, disposable metropolitan-extract replication experiment.

The reference guard is intentionally evaluated separately from the full-source
oracle. An oracle mismatch with a passing guard is an unsafe false acceptance,
not a successful update. This script never installs inputs or runs a publisher.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import requests
import osmium

CORE = Path(__file__).absolute().parent.parent
sys.path.insert(0, str(CORE))
from pbf_replication import read_header, source_identity, sequence_path, State

SITES = {
    "curitiba": {"source": "https://download.geofabrik.de/south-america/brazil/sul",
                 "repository": "kauevestena/opensidewalkmap_beta"},
    "milan": {"source": "https://download.geofabrik.de/europe/italy/nord-ovest",
              "repository": "opensidewalkmap/milan"},
}


def command(*args, allowed=(0,), timeout=1200):
    start = time.monotonic()
    result = subprocess.run(["osmium", *map(str, args)], text=True, capture_output=True, timeout=timeout)
    report = {"exit_code": result.returncode, "seconds": round(time.monotonic() - start, 3),
              "stdout": result.stdout[-6000:], "stderr": result.stderr[-6000:]}
    if result.returncode not in allowed:
        raise RuntimeError(json.dumps({"command": list(map(str, args)), **report}))
    return report


def download(url, destination, limit=1024**3):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            start = time.monotonic()
            h = hashlib.sha256()
            total = 0
            with requests.get(url, stream=True, timeout=(20, 60), headers={
                    "User-Agent": "OpenSidewalkMap sandbox metropolitan-extract evaluation"}) as response:
                response.raise_for_status()
                with destination.open("wb") as output:
                    for chunk in response.iter_content(1024**2):
                        total += len(chunk)
                        if total > limit or time.monotonic() - start > 900:
                            raise ValueError("Download size/time budget exceeded")
                        output.write(chunk)
                        h.update(chunk)
            if not total:
                raise ValueError("Empty download")
            return {"url": url, "bytes": total, "sha256": h.hexdigest(),
                    "seconds": round(time.monotonic() - start, 3)}
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def extract(source, destination, bbox):
    return command("extract", "-s", "smart", "-b", ",".join(map(str, bbox)),
                   source, "-o", destination, "-O")


def equal(left, right):
    result = command("diff", "--quiet", "--summary", left, right, allowed=(0, 1))
    return {"equal": result["exit_code"] == 0, **result}


def reference_guard(candidate, work):
    """Check every way and all multipolygon-member closures available locally.

    Other route/admin relations can be partial by extraction design. They are
    retained but are not treated as a claim of complete city relation coverage.
    Even these checks cannot discover absent parent ways or relations.
    """
    ways = command("check-refs", candidate, allowed=(0, 1))
    selected = work / "area-relations.osm.pbf"
    command("tags-filter", candidate, "r/type=multipolygon", "-o", selected, "-O")
    areas = command("check-refs", "-r", selected, allowed=(0, 1))
    selected.unlink()
    return {"passed": ways["exit_code"] == areas["exit_code"] == 0,
            "way_references": ways, "multipolygon_references": areas,
            "scope": "all ways and selected multipolygons; not a completeness proof"}


def fingerprints(source, node, destination):
    """Use the real OSWM raw-layer contract in an isolated node directory."""
    env = {**os.environ, "PYTHONPATH": str(node / "oswm_codebase") + os.pathsep + os.environ.get("PYTHONPATH", "")}
    script = ("import json,sys; import constants as cfg; "
              "from replication_pipeline import extract_city,fingerprint; "
              "r={k:fingerprint(v) for k,v in extract_city(sys.argv[1],cfg).items()}; "
              "open(sys.argv[2],'w').write(json.dumps(r,indent=2))")
    result = subprocess.run([sys.executable, "-c", script, str(source), str(destination)],
                            cwd=node, env=env, text=True, capture_output=True, timeout=1800)
    if result.returncode:
        return {"error": result.stderr[-5000:], "exit_code": result.returncode}
    return json.loads(destination.read_text())


def fixture_tests(root):
    """Adversarial tests demonstrate both detectable and silent failures."""
    root.mkdir(parents=True, exist_ok=True)
    cases = {
        "new_way_references_old_outside_nodes": (
            '<node id="1" version="1" lat="0" lon="0"/><node id="2" version="1" lat="0" lon="2"/>',
            '<create><way id="10" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/></way></create>', False),
        "moved_node_brings_unknown_parent_way_into_city": (
            '<node id="1" version="1" lat="0" lon="2"/><node id="2" version="1" lat="0" lon="3"/>'
            '<way id="10" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/></way>',
            '<modify><node id="1" version="2" lat="0" lon="0"/></modify>', True),
        "new_multipolygon_references_old_outside_way": (
            '<node id="1" version="1" lat="0" lon="0"/><node id="2" version="1" lat="0" lon="2"/>'
            '<node id="3" version="1" lat="1" lon="2"/>'
            '<way id="10" version="1"><nd ref="2"/><nd ref="3"/><nd ref="2"/></way>',
            '<create><relation id="20" version="1"><member type="node" ref="1" role="label"/>'
            '<member type="way" ref="10" role="outer"/><tag k="type" v="multipolygon"/>'
            '<tag k="highway" v="pedestrian"/></relation></create>', False),
        "moved_node_brings_unknown_parent_relation_into_city": (
            '<node id="1" version="1" lat="0" lon="2"/><node id="2" version="1" lat="1" lon="3"/>'
            '<node id="3" version="1" lat="2" lon="2"/>'
            '<way id="10" version="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="1"/></way>'
            '<relation id="20" version="1"><member type="way" ref="10" role="outer"/>'
            '<tag k="type" v="multipolygon"/></relation>',
            '<modify><node id="1" version="2" lat="0" lon="0"/></modify>', True),
        "deletion_of_existing_way": (
            '<node id="1" version="1" lat="0" lon="0"/><node id="2" version="1" lat="0" lon="0.1"/>'
            '<way id="10" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/></way>',
            '<delete><way id="10" version="2"/></delete>', True),
        "ordinary_new_local_way": (
            '<node id="1" version="1" lat="0" lon="0"/>',
            '<create><node id="2" version="1" lat="0" lon="0.1"/><way id="10" version="1">'
            '<nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/></way></create>', True),
    }
    reports = []
    for name, (initial, changes, expected_guard) in cases.items():
        work = root / name
        work.mkdir(exist_ok=True)
        base, change = work / "full.osm", work / "change.osc"
        base.write_text('<osm version="0.6">' + initial + '</osm>')
        change.write_text('<osmChange version="0.6">' + changes + '</osmChange>')
        metro, candidate, updated, truth = [work / f"{s}.osm.pbf" for s in ("metro", "candidate", "updated", "truth")]
        extract(base, metro, [-1, -1, 1, 1])
        command("apply-changes", metro, change, "-o", candidate, "-O")
        command("apply-changes", base, change, "-o", updated, "-O")
        extract(updated, truth, [-1, -1, 1, 1])
        guard = reference_guard(candidate, work)
        parity = equal(candidate, truth)
        assert guard["passed"] == expected_guard, name
        silent = guard["passed"] and not parity["equal"]
        # A reference-only fallback will fail to run for the silent cases.
        fallback = not guard["passed"]
        installed = work / "installed.osm.pbf"
        shutil.copyfile(truth if fallback else candidate, installed)
        recovered = equal(installed, truth)["equal"]
        assert recovered if fallback else True
        reports.append({"case": name, "guard": guard, "oracle": parity,
                        "unsafe_false_acceptance": silent, "fallback_triggered": fallback,
                        "after_reference_only_fallback_equals_truth": recovered})
    assert sum(r["unsafe_false_acceptance"] for r in reports) == 2
    return reports


def run(args):
    work = args.work.resolve()
    if work.exists() and any(work.iterdir()):
        raise ValueError("Use a new empty sandbox directory")
    work.mkdir(parents=True, exist_ok=True)
    report = {"sandbox_only": True, "started_at": datetime.now(timezone.utc).isoformat(),
              "code_revision": subprocess.check_output(["git", "-C", CORE, "rev-parse", "HEAD"], text=True).strip(),
              "buffer_km": args.buffer_km, "strategy": "smart (complete ways and multipolygons)",
              "publication": "none; no node workflow or production data is modified",
              "fixtures": fixture_tests(work / "fixtures"), "cities": []}
    def save():
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    save()
    if args.fixtures_only:
        return report
    for city in args.cities:
        site = SITES[city]
        area = work / city
        area.mkdir()
        node = area / "node"
        (node / "data/boundaries").mkdir(parents=True)
        (node / "oswm_codebase").symlink_to(CORE, target_is_directory=True)
        city_report = {"city": city, "repository": site["repository"], "downloads": [], "steps": []}
        report["cities"].append(city_report)
        # Pin the remote node inputs explicitly, without checking out or writing its branch.
        api = requests.get(f'https://api.github.com/repos/{site["repository"]}/commits/main', timeout=30)
        api.raise_for_status()
        revision = api.json()["sha"]
        city_report["node_revision"] = revision
        for relative in ("config.py", "data/boundaries/polygon.geojson"):
            city_report["downloads"].append(download(
                f'https://raw.githubusercontent.com/{site["repository"]}/{revision}/{relative}',
                node / relative, limit=16 * 1024**2))
        config = {}
        exec(compile((node / "config.py").read_text(), "config.py", "exec"), config)
        south, west, north, east = config["BOUNDING_BOX"]
        dy = args.buffer_km / 111.32
        dx = dy / math.cos(math.radians((south + north) / 2))
        bbox = [west - dx, south - dy, east + dx, north + dy]
        city_report.update({"node_bbox_wsen": [west, south, east, north], "buffered_bbox_wsen": bbox,
                            "coverage": "rectangular buffer including nearby municipalities, not an administrative metro polygon"})
        previous_full = None
        previous_state = None
        current = area / "metro-current.osm.pbf"
        base = site["source"]
        source = source_identity(base + "-latest.osm.pbf")
        for date in args.dates:
            print(json.dumps({"city": city, "date": date, "phase": "download control"}), flush=True)
            full = area / f"regional-{date}.osm.pbf"
            full_download = download(f"{base}-{date}.osm.pbf", full)
            city_report["downloads"].append(full_download)
            state = read_header(full, source)
            step = {"date": date, "sequence": state.sequence, "timestamp": state.timestamp.isoformat(),
                    "full_snapshot": full_download, "diff_downloads": []}
            city_report["steps"].append(step)
            save()
            if previous_full is None:
                step["bootstrap_extract"] = extract(full, current, bbox)
                step["metro_bytes"] = current.stat().st_size
                step["baseline_guard"] = reference_guard(current, area)
                save()
            else:
                if not 1 <= state.sequence - previous_state.sequence <= 10:
                    raise ValueError("Require one to ten consecutive real diffs per replay step")
                diffs = []
                for seq in range(previous_state.sequence + 1, state.sequence + 1):
                    stem = f"{source}/{sequence_path(seq)}"
                    state_path = area / f"{seq}.state.txt"
                    step["diff_downloads"].append(download(stem + ".state.txt", state_path, 65536))
                    diff_state = State.parse(state_path.read_text())
                    if diff_state.sequence != seq or (seq == state.sequence and diff_state != state):
                        raise ValueError("Diff state does not match the full snapshot cutoff")
                    path = area / f"{seq}.osc.gz"
                    step["diff_downloads"].append(download(stem + ".osc.gz", path, 128 * 1024**2))
                    diffs.append(path)
                # Validate the replay itself against the independent full file.
                full_applied = area / "full-applied.osm.pbf"
                command("apply-changes", previous_full, *diffs, "-o", full_applied, "-O")
                step["regional_replay_oracle"] = equal(full_applied, full)
                if not step["regional_replay_oracle"]["equal"]:
                    raise ValueError("Full regional replay differs from independent source")
                full_applied.unlink()
                union = area / "union.osm.pbf"
                candidate = area / "candidate.osm.pbf"
                step["apply"] = command("apply-changes", current, *diffs, "-o", union, "-O")
                try:
                    step["crop"] = extract(union, candidate, bbox)
                    step["guard"] = reference_guard(candidate, area)
                except (RuntimeError, OSError) as exc:
                    step["crop_error"] = str(exc)
                    step["guard"] = {"passed": False, "reason": "candidate could not be extracted or validated"}
                union.unlink()
                step["candidate_metro_bytes"] = candidate.stat().st_size if candidate.exists() else 0
                truth = area / "metro-truth.osm.pbf"
                step["control_extract"] = extract(full, truth, bbox)
                step["metro_object_oracle"] = equal(candidate, truth) if "crop_error" not in step else {"equal": False}
                save()
                print(json.dumps({"city": city, "date": date, "phase": "OSWM layer comparison",
                                  "guard": step["guard"]["passed"], "metro_equal": step["metro_object_oracle"]["equal"]}), flush=True)
                step["control_layers"] = fingerprints(full, node, area / "control-layers.json")
                save()
                if "error" in step["control_layers"]:
                    raise ValueError("Full source layer extraction failed: " + step["control_layers"]["error"])
                step["candidate_layers"] = (fingerprints(candidate, node, area / "candidate-layers.json")
                                            if "crop_error" not in step else {"error": step["crop_error"]})
                step["city_layers_equal"] = step["candidate_layers"] == step["control_layers"]
                step["unsafe_false_acceptance"] = step["guard"]["passed"] and not step["city_layers_equal"]
                # Test exactly the proposed guard-driven fallback, not an oracle-driven success claim.
                step["fallback_triggered"] = not step["guard"]["passed"]
                if step["fallback_triggered"]:
                    step["fallback_layers"] = fingerprints(truth, node, area / "fallback-layers.json")
                    step["fallback_city_layers_equal"] = step["fallback_layers"] == step["control_layers"]
                    shutil.copyfile(truth, current)
                else:
                    shutil.copyfile(candidate, current)
                step["next_run_cache_bytes"] = current.stat().st_size
                step["provider_incremental_bytes"] = sum(x["bytes"] for x in step["diff_downloads"])
                step["hosted_runner_acquisition_bytes_without_fallback"] = step["provider_incremental_bytes"] + city_report["steps"][-2].get("next_run_cache_bytes", city_report["steps"][0]["metro_bytes"])
                step["fallback_download_bytes"] = full_download["bytes"] if step["fallback_triggered"] else 0
                candidate.unlink(missing_ok=True)
                truth.unlink()
                for diff in diffs:
                    diff.unlink()
                previous_full.unlink()
                save()
                print(json.dumps({"city": city, "date": date, "phase": "step completed",
                                  **{k: step[k] for k in ("city_layers_equal", "unsafe_false_acceptance",
                                     "fallback_triggered", "next_run_cache_bytes", "provider_incremental_bytes")}}), flush=True)
            previous_full, previous_state = full, state
        city_report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["safe_to_deploy"] = False
    report["reason"] = "Synthetic unknown-parent edits defeat a reference-only guard, irrespective of observed real replay parity."
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cities", nargs="+", choices=SITES, default=list(SITES))
    parser.add_argument("--dates", nargs="+", default=["261028", "261029", "261030"])
    parser.add_argument("--buffer-km", type=float, default=25)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--fixtures-only", action="store_true")
    args = parser.parse_args()
    args.report = args.report.resolve()
    report = run(args)
    print("METRO_SANDBOX_REPORT=" + json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
