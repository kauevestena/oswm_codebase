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

WATCHER_STATUS=0
"$PYTHON_BIN" oswm_codebase/datahub/watcher/watcher_lib.py || WATCHER_STATUS=$?

DECISION_ARGS=(
    --root . decide
    --watcher-status "$WATCHER_STATUS"
    --output data/updates/pipeline_decision.json
)
case "${OSWM_FORCE_REGEN:-}" in
    1|true|TRUE|yes|YES|on|ON) DECISION_ARGS+=(--force) ;;
esac
"$PYTHON_BIN" oswm_codebase/pipeline_decision.py "${DECISION_ARGS[@]}" || exit 1

MODE=$("$PYTHON_BIN" -c 'import json; print(json.load(open("data/updates/pipeline_decision.json"))["mode"])')
echo "Pipeline mode: $MODE"

if [ "$MODE" = "skip" ]; then
    run_step oswm_codebase/datahub/acquisition/generate_acquisition.py "generate_acquisition"
    run_step oswm_codebase/metadata/metadata_generation.py "metadata_generation"
    run_step oswm_codebase/datahub/API/generate_api.py "generate_api"
    run_step oswm_codebase/datahub/datahub_index_generator.py "datahub_index"
else
    if [ "$MODE" = "generate" ]; then
        run_step oswm_codebase/getting_data.py "getting_data"
        if [ ! -d "data/updates/versioning" ]; then
            run_step oswm_codebase/getting_feature_versioning_data.py "getting_feature_versioning_data"
        fi
    fi

    if [ "${#FAILED_STEPS[@]}" -eq 0 ]; then
        "$PYTHON_BIN" oswm_codebase/node_outputs.py --root . reset-derived || exit 1
    fi

    run_step oswm_codebase/filtering_adapting_data.py "filtering_adapting_data"
    run_step oswm_codebase/generation/vec_tiles_gen.py "vec_tiles_gen"
    run_step oswm_codebase/generation/vrt.py "vrt"
    run_step oswm_codebase/webmap/snapshot/generate_snapshot_summary.py "generate_snapshot_summary"
    run_step oswm_codebase/webmap/create_webmap_new.py "create_webmap_new"
    run_step oswm_codebase/data_quality/tag_values_checking.py "tag_values_checking"
    run_step oswm_codebase/data_quality/quality_check_compiling.py "quality_check_compiling"
    run_step oswm_codebase/data_quality/completeness/completeness_runner.py "completeness_runner"
    run_step oswm_codebase/data_quality/external_qc.py "external_qc"
    run_step oswm_codebase/dashboard/statistics_generation.py "statistics_generation"
    run_step oswm_codebase/generation/routing_demo_gen.py "routing_demo_gen"
    run_step oswm_codebase/generation/hazard_tiles_gen.py "hazard_tiles_gen"
    # reset-derived removes hub/, including the dashboard made by the initial
    # update check. Render it again after boundaries and derived data exist.
    run_step oswm_codebase/datahub/watcher/watcher_lib.py "watcher_render" --render-only
    run_step oswm_codebase/datahub/acquisition/generate_acquisition.py "generate_acquisition"
    run_step oswm_codebase/metadata/metadata_generation.py "metadata_generation"
    run_step oswm_codebase/datahub/API/generate_api.py "generate_api"
    run_step oswm_codebase/datahub/datahub_index_generator.py "datahub_index"
fi

if [ "${#FAILED_STEPS[@]}" -ne 0 ]; then
    mkdir -p data/updates
    printf '%s\n' "${FAILED_STEPS[@]}" > data/updates/pipeline_failures.txt
    printf 'Pipeline failed in: %s\n' "${FAILED_STEPS[*]}" >&2
    exit 1
fi

"$PYTHON_BIN" oswm_codebase/node_outputs.py --root . require
"$PYTHON_BIN" oswm_codebase/pipeline_decision.py --root . record-success
rm -f data/updates/pipeline_failures.txt
