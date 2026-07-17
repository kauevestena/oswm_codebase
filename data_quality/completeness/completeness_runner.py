"""
Completeness analysis runner for OSWM.

Hybrid pipeline:
- Current month: computed from local GeoParquet data (fast, offline)
- Historical months: OHSOME API at Z15 (fewer calls than Z17)

First run:  3 prior months via OHSOME + current month local = 4 timestamps
Monthly:    +1 current (local) + -1 historical (OHSOME extending backwards)

Output: quality_check/completeness/data.json
"""

import os
import sys
import json
import argparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from functions import get_boundaries_bbox, record_datetime, dump_json, create_folder_if_not_exists
from completeness_lib import run_completeness_analysis, generate_completeness_map

# Output paths
OUTPUT_DIR = os.path.join("quality_check", "completeness")
DATA_JSON_PATH = os.path.join(OUTPUT_DIR, "data.json")


def main():
    parser = argparse.ArgumentParser(description="OSWM Completeness Analysis")
    parser.add_argument("--silent", action="store_true", help="Run in automated silent mode")
    args = parser.parse_args()

    def p(msg):
        if not args.silent:
            print(msg)

    p("=" * 60)
    p("OSWM Completeness Analysis (Hybrid)")
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
    )

    elapsed = time.time() - t0
    p(f"\n[completeness] Analysis completed in {elapsed:.1f}s ({elapsed/60:.1f} min)")

    # 4. Save JSON
    create_folder_if_not_exists(OUTPUT_DIR)
    dump_json(results, DATA_JSON_PATH)
    p(f"Data saved to {DATA_JSON_PATH}")

    # 5. Generate map
    generate_completeness_map(results, OUTPUT_DIR, silent=args.silent)

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