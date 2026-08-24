#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN=python3
fi

"$PYTHON_BIN" oswm_codebase/getting_feature_versioning_data.py
"$PYTHON_BIN" oswm_codebase/filtering_adapting_data.py
"$PYTHON_BIN" oswm_codebase/data_quality/quality_check_compiling.py
"$PYTHON_BIN" oswm_codebase/dashboard/statistics_generation.py
"$PYTHON_BIN" oswm_codebase/data_quality/check_wiki_keys.py
"$PYTHON_BIN" oswm_codebase/metadata/metadata_generation.py
"$PYTHON_BIN" oswm_codebase/datahub/API/generate_api.py
"$PYTHON_BIN" oswm_codebase/datahub/datahub_index_generator.py
