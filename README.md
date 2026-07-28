# OpenSidewalkMap shared codebase

`oswm_codebase` contains the shared source code, templates, workflows, and identity assets used by [OpenSidewalkMap (OSWM)](https://github.com/kauevestena/opensidewalkmap) nodes.

OSWM is a decentralized, modular, GitHub-hosted ecosystem for inventorying, visualizing, analysing, routing over, monitoring, and distributing pedestrian-network data. It primarily transforms OpenStreetMap data into static maps, reports, dashboards, quality checks, and downloadable datasets that can be published with GitHub Pages.

## Role of this repository

This repository is not a complete deployed node by itself. Individual city or regional repositories include it as a Git submodule named `oswm_codebase` and add their own configuration, source data, generated data, and published pages.

The responsibilities are intentionally separated:

| Location | Responsibility |
|---|---|
| OSWM project repositories/organization | Project coordination, supporting material, and the collection of nodes |
| `oswm_codebase` | Reusable Python, HTML, JavaScript, CSS, assets, generators, runner scripts, and workflow templates |
| A node repository | Area-specific `config.py`, pinned codebase commit, generated datasets, reports, and GitHub Pages site |
| GitHub Pages | Static publication of the node homepage, Webmap, dashboard, quality reports, routing demo, feeds, and data hub |

[`kauevestena/opensidewalkmap_beta`](https://github.com/kauevestena/opensidewalkmap_beta) is the current reference node. It is a working model, not a claim that every future node must be an exact copy.

## Architecture

```text
OpenSidewalkMap project
├── oswm_codebase                    shared source submodule (this repository)
│   ├── assets/                      styles, symbols, homepage media, and branding
│   ├── dashboard/                   statistics and chart generators
│   ├── data_quality/                validation and completeness analysis
│   ├── datahub/                     static API, acquisition, and watcher/RSS
│   ├── generation/                  PMTiles, VRT, and routing-data generators
│   ├── routing/                     static routing demonstration
│   ├── runners/                     setup, daily, weekly, and custom pipelines
│   ├── webmap/                      MapLibre Webmap and scrutiny snapshots
│   ├── workflows/                   workflow templates copied into nodes
│   └── tests/                       lightweight automated validation
└── node repository
    ├── config.py                    node-specific area and tag configuration
    ├── oswm_codebase/               pinned Git submodule
    ├── data/                        generated raw/processed data and PMTiles
    ├── hub/, quality_check/         generated module outputs
    ├── statistics/                  generated dashboards
    ├── index.html, map.html          published entry pages
    └── .github/workflows/           node automation and Pages deployment
```

Generators run from the node root. They import shared code through the `oswm_codebase` submodule and write node-specific outputs beside it. A node therefore deploys a reproducible combination of its own commit and an explicitly pinned codebase commit.

## Current modules

| Module | Current role | Status |
|---|---|---|
| Webmap and scrutiny snapshots | MapLibre/PMTiles visualization, thematic styles, legends, popups, and printable A4 analytical snapshots | Active |
| Dashboard/statistics | Altair/Vega charts for individual pedestrian layers and aggregated data | Active |
| Data quality | Tag-value checks, geometry checks, report tables, QA maps, and external-provider links | Active |
| Completeness | Multi-scale and temporal footway/sidewalk-to-road completeness analysis | Active; computationally and API intensive |
| Routing demo | Client-side route exploration over generated pedestrian geometries | Experimental |
| Data hub and static API | Human-readable hub plus serverless JSON, GeoParquet, PMTiles, VRT, and chart-spec endpoints | Active |
| Change watcher and RSS | Detects relevant OSM changes, helps skip unnecessary pipeline runs, and emits HTML/RSS/Atom-style outputs | Active |
| Acquisition | Discovers relevant mapping projects from supported third-party platforms | Active, dependent on external services |

`demos/`, `other/prototypes/`, and `other/for_future/` contain exploratory work. `deprecated/` contains frozen legacy implementations and generated snapshots; it is not part of an active node pipeline.

## Branding assets

Shared identity resources live under `assets/branding/`:

```text
assets/branding/
├── favicon_homepage.png
├── manifest.json
├── branding.js
├── banners/
└── logos/
    ├── page_logo.png
    ├── page_logo_clean.png
    ├── page_logo_dark_clean.png
    ├── project_logo.png
    └── project_logo_100px.png
```

`manifest.json` is the canonical registry. Its paths are relative to the root of this repository, and consumers address them by semantic keys such as `favicon`, `logos.page_clean`, `logos.page_dark_clean`, and `logos.project` rather than duplicating filenames.

- Python generators use `branding.py` to resolve keys while generating a page. The generated HTML may contain the final relative URL.
- Browser-only pages use the static `assets/branding/branding.js` module, which fetches the same manifest and resolves paths relative to the codebase itself. No application server is required.
- The clean light page logo is used for printable output. The clean dark variant is used on the dark Webmap and routing surfaces. Project-logo variants serve compact headings and module cards.
- `banners` is reserved for clean shared banners; it is currently empty because no separate `*_clean` banner files exist on `main`.

Do not add a second path registry. Add or rename a shared identity asset in `manifest.json`, update consumers to use its semantic key, and run the manifest test. Paths must continue to work when this repository is mounted exactly as `oswm_codebase` inside any node.

The identical `assets/homepage/favicon_homepage.png` and the non-clean `assets/page_logo_dark.png` are retained only as unregistered legacy compatibility assets. Active code does not use them.

## Local development

### Prerequisites

- Git with submodule support;
- Python 3 and `venv`/`pip`;
- the Python packages in `requirements.txt`;
- GDAL command-line tools, including `ogr2ogr`, for tile/VRT and full pipeline work;
- Node.js for the dependency-free JavaScript snapshot tests;
- a local HTTP server for browser smoke tests (Python's standard library is sufficient).

For integration work, start with a node so relative paths and generated outputs are exercised in their real topology:

```bash
git clone --recurse-submodules https://github.com/kauevestena/opensidewalkmap_beta.git
cd opensidewalkmap_beta

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r oswm_codebase/requirements.txt
```

If the node was cloned without submodules:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

To develop this repository from within a node, create or check out the desired branch inside `oswm_codebase/`, but run generators from the node root because their inputs and outputs are node-relative:

```bash
git -C oswm_codebase switch -c my-codebase-branch

python oswm_codebase/webmap/create_webmap_new.py --development
python oswm_codebase/webmap/snapshot/generate_snapshot_summary.py
python oswm_codebase/datahub/datahub_index_generator.py
```

The full runners are available when the node data and external dependencies are configured:

```bash
sh oswm_codebase/runners/setup.sh
sh oswm_codebase/runners/daily.sh
sh oswm_codebase/runners/weekly.sh
```

These pipelines can download data and rewrite many committed node outputs. Review the node diff before committing. `local_setup.sh` automates cloning the current reference node, updating its submodule, creating `.venv`, and installing `requirements.txt`; the explicit commands above are preferable when you need control over the pinned revision.

## Testing and validation

From a standalone `oswm_codebase` checkout:

```bash
python tests/test_branding_manifest.py
python -m unittest discover -s tests/webmap_snapshot -p 'test_*.py'
node --test webmap/snapshot/snapshot_stats.test.mjs
git diff --check
```

The branding test rejects duplicate JSON keys, unsafe or duplicate paths, missing files, an incomplete logo contract, and requested assets left at their former locations.

For static smoke testing, serve the node root—not the submodule directory—so the same relative URLs used by GitHub Pages are exercised:

```bash
python3 -m http.server 8000
```

Then inspect at least:

- `http://localhost:8000/` — node homepage;
- `http://localhost:8000/map.html` — Webmap and snapshot composer;
- `http://localhost:8000/oswm_codebase/routing/routing_demo.html` — routing page;
- `http://localhost:8000/statistics/index.html` — dashboard;
- `http://localhost:8000/quality_check/oswm_qc_main.html` — data-quality entry point;
- `http://localhost:8000/hub/index.html` — data hub.

Use browser developer tools to confirm that `assets/branding/manifest.json`, both light and dark page logos, project logos, favicon, and any registered banners return HTTP 200.

## Creating or updating a node

The reference node's [README](https://github.com/kauevestena/opensidewalkmap_beta#readme) documents recursive cloning, configuration, generation, publication, troubleshooting, and deliberate submodule pinning. The essential update pattern is:

```bash
git submodule sync --recursive
git submodule update --init oswm_codebase
git -C oswm_codebase fetch origin
git -C oswm_codebase checkout <tested-codebase-commit>
git add oswm_codebase
git commit -m "chore: update oswm_codebase"
```

Do not leave the submodule on an unrecorded local branch and assume a node clone will reproduce it. The gitlink stored by the node is the contract.

## Contributing

- Open changes against the shared codebase for reusable logic and assets; keep node-specific configuration and outputs in the node.
- Change committed generated pages through their generators whenever possible, then regenerate and review the result.
- Preserve static hosting and submodule-relative paths.
- Add focused tests or smoke checks for behavior you change.
- Keep prototypes and deprecated implementations clearly labelled.

Project links:

- [Main OpenSidewalkMap repository](https://github.com/kauevestena/opensidewalkmap)
- [OpenSidewalkMap GitHub organization](https://github.com/opensidewalkmap)
- [Reference node](https://github.com/kauevestena/opensidewalkmap_beta)
- [Issues for this codebase](https://github.com/kauevestena/oswm_codebase/issues)

This repository is distributed under the terms in [LICENSE](LICENSE).
