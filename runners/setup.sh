#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN=python3
fi

"$PYTHON_BIN" oswm_codebase/runtime_assets.py
"$PYTHON_BIN" oswm_codebase/patch_readme_homepage.py
"$PYTHON_BIN" oswm_codebase/other/wipers/wipe_changed_stuff.py
case "${OSWM_THIN_NODE:-}" in
    1|true|TRUE|yes|YES|on|ON) ;;
    *) "$PYTHON_BIN" oswm_codebase/special_updates.py ;;
esac
"$PYTHON_BIN" oswm_codebase/metadata/metadata_generation.py
"$PYTHON_BIN" oswm_codebase/metadata/stac_generation.py --if-enabled
"$PYTHON_BIN" oswm_codebase/datahub/API/generate_api.py
