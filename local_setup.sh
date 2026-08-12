#!/bin/bash

OSWM_NODE_URL=https://github.com/kauevestena/opensidewalkmap_beta.git

git clone --recurse-submodules "${OSWM_NODE_URL}"
cd opensidewalkmap_beta

# Ensure .gitmodules tracks branch main (once only, if not already set)
# echo '[submodule "oswm_codebase"]' >> .gitmodules
# echo '  path = oswm_codebase' >> .gitmodules
# echo '  url = https://github.com/kauevestena/oswm_codebase.git' >> .gitmodules
# echo '  branch = main' >> .gitmodules

# Materialize the exact gitlink recorded by the node repository.  Updating the
# shared codebase is a separate reviewed operation.
git submodule sync --recursive
git submodule update --init --recursive oswm_codebase

# setup the local python environment:
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r oswm_codebase/requirements.txt
