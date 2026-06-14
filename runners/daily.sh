#!/bin/bash

# Track which steps failed
FAILED_STEPS=""
PYTHON_BIN="${PYTHON:-python}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
fi

run_step() {
    local script="$1"
    local label="$2"
    echo "========================================="
    echo "Running: $label"
    echo "========================================="
    if "$PYTHON_BIN" "$script"; then
        echo "\u2713 $label succeeded"
    else
        echo "\u2717 $label FAILED (exit code: $?)"
        FAILED_STEPS="${FAILED_STEPS}\n- ${label}"
    fi
    echo ""
}

# Each step runs independently regardless of the others
run_step oswm_codebase/getting_data.py             "getting_data"
run_step oswm_codebase/filtering_adapting_data.py  "filtering_adapting_data"
run_step oswm_codebase/generation/vec_tiles_gen.py "vec_tiles_gen"
run_step oswm_codebase/webmap/create_webmap_new.py "create_webmap_new"
run_step oswm_codebase/data_quality/tag_values_checking.py     "tag_values_checking"
run_step oswm_codebase/data_quality/quality_check_compiling.py "quality_check_compiling"
run_step oswm_codebase/data_quality/external_qc.py             "external_qc"
run_step oswm_codebase/dashboard/statistics_generation.py      "statistics_generation"
run_step oswm_codebase/datahub/API/generate_api.py             "generate_api"

# Print summary and propagate failure
echo "========================================="
echo "PIPELINE SUMMARY"
echo "========================================="

if [ -n "$FAILED_STEPS" ]; then
    echo "The following steps FAILED:"
    printf "%b\n" "$FAILED_STEPS"
    # Write failure list for the workflow notification step to read
    mkdir -p data/updates
    printf "%b\n" "$FAILED_STEPS" > data/updates/pipeline_failures.txt
    exit 1
else
    echo "\u2713 All steps completed successfully."
    rm -f data/updates/pipeline_failures.txt
    exit 0
fi
