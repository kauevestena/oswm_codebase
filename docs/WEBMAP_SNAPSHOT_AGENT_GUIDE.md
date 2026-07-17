# Webmap Scrutiny Snapshots: Agent Handoff and Local Test Guide

## Status of this branch

- Repository: `kauevestena/oswm_codebase`
- Branch: `feat/webmap-scrutiny-snapshots`
- Base branch: `main`
- Current scope: planning and handoff documentation only
- No snapshot implementation has been started in this branch.
- Do not merge this branch unless the repository owner explicitly requests it.

This document is intended to let another coding agent continue the implementation and validate it against a local checkout of an OSWM node, initially `kauevestena/opensidewalkmap_beta`.

## Goal

Add a printer control to the OSWM Webmap that opens a print composer and produces an A4 scrutiny map suitable for physical printing or saving as PDF.

The default output should combine:

- the current thematic map;
- a legend using the exact same classifications and colors as the map;
- one compact chart associated with the active theme;
- quantitative facts that expose heterogeneity in the mapped real-world data;
- data-completeness information kept separate from physical heterogeneity;
- title, node name, timestamp, bounding box, scale, north arrow and attribution.

The feature must preserve the serverless/static architecture used by GitHub Pages.

## Non-negotiable constraints

1. Keep reusable source code in `oswm_codebase`.
2. Do not require an application server or database at runtime.
3. Do not edit generated `map.html` or root `webmap_params.json` as the source of truth. Modify their generators/templates instead.
4. Treat `?` and missing values as incompleteness, not as physical categories contributing to heterogeneity.
5. Clearly label statistics calculated from visible vector-tile features as counts of unique visible OSM elements.
6. Do not claim exact visible lengths from tiled geometries unless a validated spatial aggregation method is implemented.
7. Keep OSM and basemap attribution visible in the PDF.
8. Do not update or merge the node repository or this branch without explicit authorization.
9. Do not commit secrets, tokens, browser profiles, virtual environments or generated caches.
10. Preserve current Webmap behavior, including style selection, legend, popups, hover state and PMTiles loading.

## Repository topology

`oswm_codebase` is included as a Git submodule by OSWM node repositories. The initial integration node is:

```text
kauevestena/opensidewalkmap_beta
└── oswm_codebase/  -> Git submodule
```

Important consequences:

- source changes belong in this branch of `oswm_codebase`;
- the node consumes a pinned submodule commit, not automatically the latest `main`;
- testing locally requires switching the checked-out submodule to this feature branch;
- deployment later requires an explicit submodule-pointer update in each node;
- that pointer update is outside the current authorized scope.

The node's GitHub Actions checkout uses the pinned submodule commit. Do not assume that merging `oswm_codebase` alone updates deployed nodes.

## Current implementation landmarks

Read these files before changing code:

| File | Current role |
|---|---|
| `webmap/webmap_base.html` | MapLibre/PMTiles Webmap template and inline JavaScript |
| `webmap/create_webmap_new.py` | Produces root `map.html` and `webmap_params.json` |
| `webmap/webmap_lib.py` | Builds sources, MapLibre styles and legends |
| `webmap/webmap_params.json` | Development/template parameters |
| `dashboard/statistics_funcs.py` | Existing Altair aggregation/chart helpers |
| `dashboard/statistics_specs.py` | Existing chart-theme definitions |
| `dashboard/statistics_generation.py` | Generates the static dashboard |
| `functions.py` | Shared I/O, GeoPandas and length helpers |
| `constants.py` | Paths, field metadata, colors and theme definitions |
| `generation/vec_tiles_gen.py` | Produces PMTiles with GDAL/ogr2ogr |
| `runners/daily.sh` | Node regeneration pipeline |
| `requirements.txt` | Python runtime dependencies |

Current relevant behavior:

- `webmap_base.html` loads MapLibre, PMTiles and the MapLibre legend plugin from CDNs.
- `create_webmap_new.py` writes generated artifacts into the node root.
- the map style selector calls `map.setStyle(...)`.
- layer sources use stable promoted feature IDs through `promoteId: "id"`.
- the Dashboard already distinguishes feature count and `length(km)` in several charts.
- `create_length_field()` estimates a local UTM CRS before calculating lengths.

## Target user flow

1. The user navigates to an area and selects a Webmap style.
2. The user clicks a MapLibre control containing a printer icon.
3. A modal opens with conservative defaults:
   - A4 landscape;
   - current viewport;
   - active theme;
   - north-up, two-dimensional export;
   - unknown values reported separately;
   - editable title.
4. The composer prepares a preview.
5. The user chooses `Print / Save as PDF`.
6. Browser print CSS produces one A4 landscape page.

The first version may use the native print dialog rather than constructing PDF bytes directly. A later, separately authorized enhancement may add a one-click PDF download.

## Statistical contract

### Current viewport

Use `map.queryRenderedFeatures()` only after the style and visible tiles are ready. Restrict the query to the analytical layers configured for the active theme.

Deduplicate returned features with a stable key such as:

```text
sourceLayer + ':' + properties.element + ':' + (feature.id or properties.id)
```

Vector-tile features can be split or duplicated at tile boundaries. Deduplication is mandatory for feature counts.

For the viewport MVP, report:

- unique feature count;
- known feature count;
- unknown feature count and percentage;
- count of known categories;
- dominant known category and percentage;
- Shannon entropy and effective diversity, when at least two known categories exist.

Use known categories only for heterogeneity:

```text
H = -sum(p_i * ln(p_i))
effective_diversity = exp(H)
```

Avoid qualitative labels such as `high heterogeneity` until documented thresholds have been agreed upon.

### Whole node

Generate a deterministic summary from processed GeoParquet rather than from PMTiles. Suggested output:

```text
data/snapshots/node_summary.json
```

The summary should contain, per layer/theme:

- generation timestamp;
- total feature count;
- known and unknown counts;
- counts by category;
- lengths by category for line layers;
- category percentages;
- entropy/effective diversity based only on known values;
- source dataset path or identifier.

Use `create_length_field()` on a copy of the GeoDataFrame where applicable. Do not mutate the source GeoParquet merely to produce the summary.

### Themes

The initial theme mapping should cover:

- `footway_categories`: category/layer distribution;
- `surface`: sidewalks;
- `smoothness`: sidewalks;
- `tactile_paving`: configured relevant layer;
- `lit`: sidewalks;
- `wheelchair`: sidewalks;
- `traffic_calming`: crossings;
- `crossings_and_kerbs`: compact crossing and kerb summaries;
- `age`: histogram;
- `n_revs`: histogram.

Theme metadata, labels and colors should be emitted by Python into `webmap_params.json`. Do not duplicate the color dictionaries manually in JavaScript.

## Recommended source layout

```text
webmap/
├── create_webmap_new.py
├── webmap_base.html
└── snapshot/
    ├── generate_snapshot_summary.py
    ├── snapshot_control.js
    ├── snapshot_stats.js
    ├── snapshot_charts.js
    └── snapshot_composer.js

assets/styles/
└── webmap_snapshot.css

tests/
└── webmap_snapshot/
    ├── test_snapshot_summary.py
    └── fixtures/
```

JavaScript modules should have clear boundaries:

- `snapshot_control.js`: MapLibre control and modal entrypoint;
- `snapshot_stats.js`: pure deduplication, aggregation and metrics;
- `snapshot_charts.js`: compact SVG/Vega-Lite chart specifications;
- `snapshot_composer.js`: export-map lifecycle, preview assembly and printing.

Keep statistical functions pure where possible so they can be tested without a browser.

## Export-map design

Do not enable `preserveDrawingBuffer` permanently on the interactive map.

Create a temporary, off-screen MapLibre map sized for the print composition. It should:

1. copy the active style;
2. preserve current layer visibility;
3. use the selected extent;
4. default to `bearing=0` and `pitch=0`;
5. use a higher pixel ratio where supported;
6. enable `canvasContextAttributes.preserveDrawingBuffer` only for this export map;
7. wait for style readiness, `idle` and loaded tiles, with a finite timeout;
8. capture the map canvas as PNG;
9. remove the temporary map and DOM container in a `finally` block.

Controls, legend, north arrow, scale and metadata should be reconstructed as HTML/SVG outside the raster map image. Do not rely on MapLibre controls being present inside the canvas.

If the basemap makes the canvas unreadable because of a CORS error, fail visibly and offer a vector-data-only fallback. Never silently generate a blank map.

## Chart design

- Prefer horizontal bars for categorical OSM values.
- Use the same colors as the active MapLibre classification.
- Show the most important categories and optionally collapse a long tail into `other`.
- Preserve the full category set when computing diversity, even if the chart collapses the tail.
- Render unknown/missing values in a distinct neutral style and explain them as incompleteness.
- Use an SVG renderer so chart text and shapes remain sharp in the PDF.
- For numeric themes, use compact histograms with explicit units.
- When the viewport sample is empty or too small, show a clear warning instead of an authoritative-looking chart.

## Suggested implementation sequence

### Phase 1: vertical slice

- Add a printer control with an inline SVG icon and accessible label.
- Add a print-preview container and A4 landscape CSS.
- Implement the temporary export map.
- Implement viewport deduplication and a single `surface` chart.
- Produce a printable one-page preview.

Stop and test this slice before adding further themes.

### Phase 2: generated metadata

- Refactor the theme declarations in `create_webmap_new.py` into structured metadata.
- Export analytical layer, field, label, chart type, unknown value and legend items per style.
- Add node name, node URL and data timestamps to `webmap_params.json`.
- Preserve backward compatibility with existing style generation.

### Phase 3: node summary

- Implement `generate_snapshot_summary.py`.
- Make output deterministic and UTF-8 encoded.
- Add unit tests using small GeoDataFrame fixtures.
- Add a dedicated step to `runners/daily.sh` before Webmap generation.
- Ensure a summary-generation failure is reported by the existing pipeline failure mechanism.

### Phase 4: remaining themes

- Add categorical themes first.
- Add `crossings_and_kerbs` as a special two-panel case.
- Add numeric histograms last.
- Add graceful fallback for an unknown future style.

### Phase 5: hardening

- Handle style changes while the composer is open.
- Disable printing while a new style is loading.
- Add timeout/error states for tiles and external raster sources.
- Restore document title after printing.
- Clean up temporary maps, event handlers and Vega views.
- Verify that repeated opens do not leak WebGL contexts.

## Local setup

### 1. Clone the node with submodules

```bash
git clone --recurse-submodules https://github.com/kauevestena/opensidewalkmap_beta.git
cd opensidewalkmap_beta
```

If the node was cloned previously:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

### 2. Switch only the submodule working tree to this branch

```bash
cd oswm_codebase
git fetch origin
git switch feat/webmap-scrutiny-snapshots
cd ..
```

At this point, the node repository will normally report a modified submodule pointer. That is expected for local testing. Do not commit or push the node pointer unless explicitly authorized.

Confirm the state:

```bash
git status
git -C oswm_codebase status
git -C oswm_codebase branch --show-current
```

### 3. Create the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r oswm_codebase/requirements.txt
```

Full PMTiles regeneration additionally requires either local `ogr2ogr`/GDAL or Docker. Snapshot UI development can initially reuse the PMTiles already committed in the node, so avoid a heavy full pipeline run unless necessary.

On Debian/Ubuntu, local GDAL can be installed with:

```bash
sudo apt-get update
sudo apt-get install gdal-bin libgdal-dev
```

### 4. Regenerate only the Webmap when appropriate

From the node root:

```bash
python oswm_codebase/webmap/create_webmap_new.py
```

Avoid `--development` unless intentionally updating the template parameters inside the submodule; the current flag also writes back to `oswm_codebase/webmap/webmap_params.json`.

After the summary generator exists, run it explicitly before regenerating the map:

```bash
python oswm_codebase/webmap/snapshot/generate_snapshot_summary.py
python oswm_codebase/webmap/create_webmap_new.py
```

The full daily runner may exit early when no OSM changesets are found. For feature development, prefer targeted scripts over relying on `runners/daily.sh`.

### 5. Serve the node over HTTP

Do not open `map.html` through `file://`, because the Webmap fetches JSON and tile resources.

```bash
python -m http.server 8000
```

Open:

```text
http://localhost:8000/map.html
```

The current generated source URLs can point to the deployed GitHub Pages node. This is acceptable for an initial local UI test with real data. If a fully local mode is added, implement it as a documented generator/runtime option rather than manually editing generated JSON.

## Test plan

### Pure JavaScript tests

Use Node's built-in test runner if possible to avoid introducing a large test stack solely for pure functions.

Required cases:

- duplicate tile fragments with the same OSM identity count once;
- equal numeric IDs in different source layers remain distinct;
- missing `feature.id` falls back safely to properties;
- `?`, null, undefined and empty strings map to the configured unknown bucket;
- unknown values are excluded from entropy;
- one known category yields entropy zero and effective diversity one;
- two equally represented categories yield effective diversity two;
- collapsed chart categories do not alter full-distribution metrics;
- empty input returns a valid empty result.

### Python summary tests

Use small in-memory GeoDataFrames and verify:

- counts by theme/category;
- unknown counts;
- deterministic category ordering;
- line lengths are calculated in a projected CRS;
- point layers do not receive misleading lengths;
- missing optional columns produce a documented fallback rather than a crash;
- output JSON contains only JSON-safe scalar values;
- repeated generation with identical data produces identical analytical content.

### Browser integration tests

At minimum, manually test current Firefox and Chromium on the local HTTP server.

Check:

1. Existing map loads with no new console errors.
2. Printer icon is keyboard-focusable and has an accessible name.
3. Opening and closing the composer does not move or reset the interactive map.
4. `surface`, `smoothness`, `footway_categories`, `crossings_and_kerbs`, `age` and `n_revs` render appropriate charts.
5. Moving the viewport changes current-scope counts and facts.
6. Switching style immediately before opening the composer uses the new style.
7. Hidden layers are not incorrectly reported as visible data.
8. The map snapshot is not transparent, black or blank.
9. Legend colors match the map and chart.
10. The page prints as exactly one A4 landscape page.
11. OSM/CARTO attribution remains legible.
12. Repeating the export several times does not trigger WebGL-context warnings.
13. An empty viewport produces a useful message.
14. A deliberately blocked basemap produces a visible error/fallback.

If automated browser testing is added, keep it focused on the print composer and use a small fixture map where possible. Do not make every unit test depend on large remote PMTiles.

## Acceptance criteria

- A printer icon is visible as a standard Webmap control.
- The default output is a single A4 landscape scrutiny map.
- Map, legend and chart use the same theme and classification colors.
- Current-viewport statistics are based on deduplicated visible OSM elements.
- Whole-node statistics come from processed GeoParquet summaries.
- Missing/unknown values are reported separately from real-world diversity.
- The PDF includes title, node, timestamp, extent, scale, north and attribution.
- No server-side runtime component is introduced.
- Existing Webmap interactions continue to work.
- Repeated exports clean up temporary maps and event listeners.
- A rendering failure cannot silently produce a blank PDF.
- Tests cover statistical edge cases and at least one browser print path.

## Commit discipline for the continuing agent

Use small, reviewable commits on `feat/webmap-scrutiny-snapshots`. Suggested boundaries:

1. `docs: define scrutiny snapshot contract`
2. `feat: add snapshot print control vertical slice`
3. `feat: export snapshot theme metadata`
4. `feat: generate node snapshot summaries`
5. `feat: add scrutiny charts and facts`
6. `test: cover snapshot statistics and print composer`

Before every commit:

- inspect `git diff` and `git status`;
- exclude generated caches and virtual environments;
- avoid unrelated formatting or refactors;
- do not commit node-repository changes;
- do not merge or open a deployment PR unless explicitly requested.

## Useful references

- MapLibre Map API: <https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/>
- MapLibre Map options: <https://maplibre.org/maplibre-gl-js/docs/API/type-aliases/MapOptions/>
- Vega Embed: <https://vega.github.io/vega-embed/>
- CSS printing: <https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Media_queries/Printing>
- CSS `@page`: <https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@page>

