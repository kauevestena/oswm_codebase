"""Curitiba-only, non-publishing replication replay and parity evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from pbf_acquisition import _download
from pbf_replication import checksum, read_header, source_identity, sync_source
from replication_pipeline import extract_city, fingerprint
from time_utils import parse_timestamp


URL = "https://download.geofabrik.de/south-america/brazil/sul-latest.osm.pbf"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap-url")
    parser.add_argument("--start-sequence", type=int)
    parser.add_argument("--end-sequence", type=int)
    args = parser.parse_args()
    import constants as cfg
    if (cfg.USERNAME, cfg.REPO_NAME, cfg.CITY_SHORTNAME) != (
            "kauevestena", "opensidewalkmap_beta", "curitiba"):
        raise ValueError("This experimental preview is restricted to Curitiba")
    if os.environ.get("GITHUB_REPOSITORY", "kauevestena/opensidewalkmap_beta") != "kauevestena/opensidewalkmap_beta":
        raise ValueError("Unexpected preview repository")
    if not shutil.which("osmium"):
        raise RuntimeError("The parity preview requires osmium-tool (osmium diff)")
    if args.bootstrap_url and (args.start_sequence is None or args.end_sequence is None
                               or not 1 <= args.end_sequence - args.start_sequence <= 10):
        raise ValueError("A replay requires a start/end range of one to ten updates")
    evidence = Path("replication-preview")
    evidence.mkdir(exist_ok=True)
    cache = Path(".cache/oswm/replication/source/sul")
    cache.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="replay-", dir=cache.parent) as temp:
        work = Path(temp)
        replica_cache = work / "replica" if args.bootstrap_url else cache
        targets = range(args.start_sequence, args.end_sequence + 1) if args.bootstrap_url else [None]
        for index, target in enumerate(targets):
            path, report = sync_source(
                URL, replica_cache, bootstrap_url=args.bootstrap_url, target_sequence=target,
            )
            print(json.dumps({"phase": "source", **report}), flush=True)
            if index or not args.bootstrap_url:
                # Derive a candidate dated URL from the actual source watermark,
                # then require its embedded sequence to match; dates are not IDs.
                date = parse_timestamp(report["snapshot_timestamp"]).strftime("%y%m%d")
                control = work / "control.osm.pbf"
                control_url = URL.replace("latest", date)
                control_hash = _download(control_url, control, max_bytes=1024 * 1024 * 1024)
                if read_header(control, source_identity(URL)) != read_header(path, source_identity(URL)):
                    raise ValueError("Full snapshot and incremental result have different cutoffs")
                parity = subprocess.run(["osmium", "diff", "--quiet", "--summary", str(path), str(control)],
                                        text=True, capture_output=True, timeout=900)
                if parity.returncode:
                    raise ValueError("Regional object parity failed: " + parity.stderr[-4000:])
                left = {name: fingerprint(frame) for name, frame in extract_city(path, cfg).items()}
                right = {name: fingerprint(frame) for name, frame in extract_city(control, cfg).items()}
                if left != right:
                    raise ValueError("Curitiba extracted-layer parity failed")
                report["parity"] = {"regional_objects_equal": True, "city_fingerprints": left,
                                    "full_snapshot_sha256": control_hash, "full_snapshot_url": control_url,
                                    "osmium_summary": parity.stderr}
                control.unlink()
            results.append(report)
            (evidence / "replay.json").write_text(json.dumps(results, indent=2) + "\n")
        # Verify idempotency without interpreting it as a real incremental update.
        path, noop = sync_source(URL, replica_cache, target_sequence=args.end_sequence)
        if noop["diffs_applied"] or any(x["url"].endswith(".osm.pbf") for x in noop["downloads"]):
            raise ValueError("A no-op unexpectedly fetched source data")
        results.append({"phase": "no_new_sequence", **noop})
        if args.bootstrap_url:
            # Seed the daily acquisition cache only from the successful replay.
            source = json.loads((replica_cache / "current.json").read_text())
            shutil.copyfile(path, cache / source["file"])
            (cache / "current.json").write_text(json.dumps(source, indent=2) + "\n")
    (evidence / "replay.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({"preview_passed": True, "real_advances": sum(r["diffs_applied"] > 0 for r in results),
                      "node": cfg.CITY_NAME, "reports": str(evidence / "replay.json")}), flush=True)


if __name__ == "__main__":
    main()
