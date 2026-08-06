#!/usr/bin/env bash
set -euo pipefail

# Restore the exact submodule revision committed by the node.  This does not
# silently move the node to the latest core main branch.
git submodule sync --recursive
git submodule update --init --recursive oswm_codebase
git submodule status --recursive
