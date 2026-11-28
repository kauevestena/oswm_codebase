#!/usr/bin/env bash
set -uo pipefail

PYTHON_BIN="${PYTHON:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN=python3
fi

FAILED_STEPS=()

run_step() {
    local script="$1"
    local label="$2"
    shift 2
    echo "==> $label"
    if ! "$PYTHON_BIN" "$script" "$@"; then
        FAILED_STEPS+=("$label")
    fi
}

# A scheduled run compares a fresh snapshot, not a history watermark.
# An explicit force_regeneration may rebuild from complete cached raw data.
DECISION_ARGS=(--root . decide --output data/updates/pipeline_decision.json)
WATCHER_ARGS=(--render-snapshot)
FORCE_REBUILD=0
case "${OSWM_FORCE_REGEN:-}" in
    1|true|TRUE|yes|YES|on|ON) FORCE_REBUILD=1; DECISION_ARGS+=(--force) ;;
esac
if [ "$FORCE_REBUILD" = 1 ] && "$PYTHON_BIN" -c '
import pathlib, sys
sys.path.insert(0, "oswm_codebase")
from pipeline_decision import RAW_OUTPUTS
sys.exit(0 if all(pathlib.Path(path).is_file() for path in RAW_OUTPUTS) else 1)
'; then
    DECISION_ARGS+=(--watcher-status 0)
    WATCHER_ARGS+=(--cached-inputs)
else
    run_step oswm_codebase/getting_data.py "getting_data"
    if [ "${#FAILED_STEPS[@]}" -ne 0 ]; then
        mkdir -p data/updates
        printf '%s\n' "${FAILED_STEPS[@]}" > data/updates/pipeline_failures.txt
        exit 1
    fi
    DECISION_ARGS+=(--snapshot-checked --watcher-status 2)
fi
"$PYTHON_BIN" oswm_codebase/pipeline_decision.py "${DECISION_ARGS[@]}" || exit 1

MODE=$("$PYTHON_BIN" -c 'import json; print(json.load(open("data/updates/pipeline_decision.json"))["mode"])') || exit 1
echo "Pipeline mode: $MODE"

if [ "$MODE" = "skip" ]; then
    "$PYTHON_BIN" oswm_codebase/datahub/watcher/watcher_lib.py "${WATCHER_ARGS[@]}" || exit 1
    # Road-only edits can change completeness even when pedestrian layers match.
    run_step oswm_codebase/data_quality/completeness/completeness_runner.py "completeness_runner" --refresh-roads
    run_step oswm_codebase/datahub/acquisition/generate_acquisition.py "generate_acquisition"
    run_step oswm_codebase/metadata/metadata_generation.py "metadata_generation"
    run_step oswm_codebase/metadata/stac_generation.py "stac_generation" --if-enabled
    run_step oswm_codebase/datahub/API/generate_api.py "generate_api"
    run_step oswm_codebase/datahub/datahub_index_generator.py "datahub_index"
else
    if ! "$PYTHON_BIN" oswm_codebase/node_outputs.py --root . require-versioning; then
        run_step oswm_codebase/getting_feature_versioning_data.py "getting_feature_versioning_data"
    fi

    if [ "${#FAILED_STEPS[@]}" -eq 0 ]; then
        "$PYTHON_BIN" oswm_codebase/node_outputs.py --root . reset-derived || exit 1
    fi

    "$PYTHON_BIN" oswm_codebase/datahub/watcher/watcher_lib.py "${WATCHER_ARGS[@]}" || exit 1
    run_step oswm_codebase/runtime_assets.py "runtime_assets"
    run_step oswm_codebase/filtering_adapting_data.py "filtering_adapting_data"
    run_step oswm_codebase/generation/vec_tiles_gen.py "vec_tiles_gen"
    run_step oswm_codebase/generation/raster_basemap_gen.py "raster_basemap_gen"
    run_step oswm_codebase/generation/vrt.py "vrt"
    run_step oswm_codebase/webmap/snapshot/generate_snapshot_summary.py "generate_snapshot_summary"
    run_step oswm_codebase/webmap/create_webmap_new.py "create_webmap_new"
    run_step oswm_codebase/data_quality/tag_values_checking.py "tag_values_checking"
    run_step oswm_codebase/data_quality/quality_check_compiling.py "quality_check_compiling"
    run_step oswm_codebase/data_quality/completeness/completeness_runner.py "completeness_runner"
    run_step oswm_codebase/data_quality/external_qc.py "external_qc"
    run_step oswm_codebase/dashboard/statistics_generation.py "statistics_generation"
    run_step oswm_codebase/generation/routing_demo_gen.py "routing_demo_gen"
    run_step oswm_codebase/generation/routing_tiles_gen.py "routing_tiles_gen"
    run_step oswm_codebase/generation/hazard_tiles_gen.py "hazard_tiles_gen"
    run_step oswm_codebase/datahub/acquisition/generate_acquisition.py "generate_acquisition"
    run_step oswm_codebase/metadata/metadata_generation.py "metadata_generation"
    run_step oswm_codebase/metadata/stac_generation.py "stac_generation" --if-enabled
    run_step oswm_codebase/datahub/API/generate_api.py "generate_api"
    run_step oswm_codebase/datahub/datahub_index_generator.py "datahub_index"
fi

# Repair existing homepages on every daily mode before publishing success.
run_step oswm_codebase/patch_readme_homepage.py "patch_readme_homepage"

if [ "${#FAILED_STEPS[@]}" -ne 0 ]; then
    mkdir -p data/updates
    printf '%s\n' "${FAILED_STEPS[@]}" > data/updates/pipeline_failures.txt
    printf 'Pipeline failed in: %s\n' "${FAILED_STEPS[*]}" >&2
    exit 1
fi

if [ "$MODE" != "skip" ]; then
    "$PYTHON_BIN" oswm_codebase/build_provenance.py --root . --mode "$MODE" || exit 1
fi

"$PYTHON_BIN" oswm_codebase/node_outputs.py --root . require || exit 1
"$PYTHON_BIN" oswm_codebase/pipeline_decision.py --root . record-success || exit 1
rm -f data/updates/pipeline_failures.txt
