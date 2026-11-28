"""Generate completeness from the local OSM snapshot; optionally backfill one date using OHSOME v2."""

import os
import sys
import json
import argparse
import tempfile
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from functions import get_boundaries_bbox, record_datetime, dump_json, create_folder_if_not_exists
from completeness_lib import run_completeness_analysis, generate_completeness_map

# Output paths
OUTPUT_DIR = os.path.join("quality_check", "completeness")
DATA_JSON_PATH = os.path.join(OUTPUT_DIR, "data.json")


def main():
    parser = argparse.ArgumentParser(description="OSWM Completeness Analysis")
    parser.add_argument("--silent", action="store_true", help="Run in automated silent mode")
    parser.add_argument("--offline", action="store_true", help="Without historical queries (the default)")
    parser.add_argument("--history-date", type=date.fromisoformat, help="Backfill one UTC date via authenticated OHSOME v2")
    parser.add_argument("--refresh-roads", action="store_true", help="Refresh the current road snapshot before measuring it")
    args = parser.parse_args()
    if args.offline and args.history_date:
        parser.error("--offline and --history-date are mutually exclusive")

    def p(msg):
        if not args.silent:
            print(msg)

    p("=" * 60)
    p("OSWM Completeness Analysis")
    p("=" * 60)

    # 1. Get bounds
    bounds = get_boundaries_bbox()
    p(f"Bounds: {bounds}")

    # 2. Check for existing data.json
    existing_data = None
    if os.path.exists(DATA_JSON_PATH):
        try:
            with open(DATA_JSON_PATH, "r") as f:
                existing_data = json.load(f)
            existing_ts = existing_data.get("timestamps", [])
            p(f"Found existing data.json with {len(existing_ts)} timestamps: {existing_ts}")
        except Exception as e:
            p(f"Could not load existing data.json: {e}")
            existing_data = None

    # 3. Run analysis
    import time
    t0 = time.time()

    results = run_completeness_analysis(
        bounds,
        existing_data=existing_data,
        silent=args.silent,
        historical_date=args.history_date.isoformat() if args.history_date else None,
        refresh_roads=args.refresh_roads,
    )

    elapsed = time.time() - t0
    p(f"\n[completeness] Analysis completed in {elapsed:.1f}s ({elapsed/60:.1f} min)")

    # 4. Save JSON
    create_folder_if_not_exists(OUTPUT_DIR)
    # Render both before replacing existing outputs. Failed backfills cannot replace history.
    with tempfile.TemporaryDirectory(prefix=".completeness-", dir=OUTPUT_DIR) as stage:
        stage_json = os.path.join(stage, "data.json")
        dump_json(results, stage_json)
        generate_completeness_map(results, stage, silent=args.silent)
        os.replace(os.path.join(stage, "index.html"), os.path.join(OUTPUT_DIR, "index.html"))
        os.replace(stage_json, DATA_JSON_PATH)
    p(f"Data saved to {DATA_JSON_PATH}")

    # 6. Record timestamp
    record_datetime("Completeness Analysis")

    p("=" * 60)
    p("Completeness analysis finished!")
    p(f"  Timestamps: {results['timestamps']}")
    p(f"  JSON: {DATA_JSON_PATH}")
    p(f"  Map:  {OUTPUT_DIR}/index.html")
    p("=" * 60)


if __name__ == "__main__":
    main()