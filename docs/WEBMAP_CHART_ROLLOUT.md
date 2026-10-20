# Webmap chart rollout check — October 20, 2026

## Change under observation

Visible-area charts now refresh on MapLibre `idle`, after the requested tiles
and their final frame have rendered. Previously the control only listened to
`moveend` and `styledata`; an early empty/partial query could persist when late
tiles arrived without another user movement. Exact whole-node summaries remain
precomputed and do not re-query tiles on idle. The listener is removed with the
control and completion events are coalesced through the existing render timer.

MapLibre documents the completion event at
https://maplibre.org/maplibre-gl-js/docs/API/type-aliases/MapEventType/#idle.

The change includes a stable runtime capability marker:

- Export: `THEME_CHART_VERSION = "viewport-idle-v1"`.
- Panel attribute: `data-oswm-theme-chart-version="viewport-idle-v1"`.
- Published module: `oswm_runtime/webmap/theme_charts/theme_chart_control.js`.
- Module SHA-256: `60488ea5255c9dcaa24454706b86fd909f0ae28925ae40f0e882d3ca6989f939`.

The marker is diagnostic metadata, not a user-visible version banner.

## Baseline

On October 20, all five registered nodes had chart module Git blob
`915d0311f7d5f973f759fdae18e9d75f0bd3c444`, without the new marker. Their full
build manifests reported core `bf6f98b2e72c48e8208e622d648dc7366e7d51f2`.
The nodes are Curitiba (`kauevestena/opensidewalkmap_beta`), Hiroshima, Lima,
Milan and Oslo (the latter four under `opensidewalkmap`).

Do not manually dispatch node regeneration for this experiment. The normal daily
workflow checks out core `main`; a changed core revision selects a rebuild even
when OSM has not changed. Existing acquisition and publication gates still apply.

## October 21 verification

Read the current `fleet/registry.toml` for the five repositories and Pages URLs.
For each node:

1. Verify a successful **new** daily run used a core revision containing this
   change. Inspect the decision/build logs for the normal revision-change path;
   distinguish an acquisition/generation run from a derived rebuild.
2. Read repository `oswm-build.json` and the chart module at a known node commit.
   Check the core revision, marker and module hash above (or inspect later
   intentional changes rather than treating any newer core as automatic proof).
3. Fetch the public Pages `oswm-build.json`, `map.html`, and published chart module
   with fresh HTTP requests. Match the served manifest and module to the node
   repository; verify `map.html` still imports that runtime module. A repository
   commit or HTTP 200 alone does not prove that Pages contains the update.
4. If WebGL2 works in the test browser, open map analysis: whole-dataset charts
   must paint the exact summary; visible-area charts must repaint after a pan
   and after tile completion without a second pan. Check the panel attribute.
   If WebGL2 is unavailable, report deployment evidence separately and leave
   end-to-end map interaction explicitly unverified.
5. Report one row per node with observed core, build/Pages results, marker/hash,
   and discrepancies. A late/failed build should remain visible as a failed or
   pending rollout, not be disguised by changing monitoring thresholds.

## Historical request audit

| Request | Current evidence | Remaining work |
|---|---|---|
| Blank webmap theme charts | PR #53 merged October 7; template imports official ECharts ESM distribution; real-renderer SVG regressions exist | This change addresses late-tile refresh; live WebGL interaction still needs acceptance |
| STAC publication | PR #51 merged September 30; opt-in generator and runner integration present | None of the five current configs enables STAC; licensing and pilot activation remain |
| Configurable isochrone bands | PR #41 merged September 19; start/increment/count inputs and export present | No missing implementation identified in this audit |
| Japanese snapshots | Japanese locale is present in snapshot internationalization | No missing implementation identified in this audit |
| Kerb dashboard explanation | PR #59 remains open, with the correction | Merge and regenerate separately; not included in this chart change |
| Submodule retirement | All five registered nodes use thin callers | Core README, local setup and legacy workflow-template cleanup remains |

This is a targeted audit of the cited requests, not a certification of every
historical request or every live node feature.

## Validation

The late-tile regression fails against the previous production control: its
query count remains one after tile completion. It passes after this change and
checks painted SVG geometry and updated, deduplicated counts. Additional tests
protect exact summaries, closed panels, coalescing and control removal.

- Full JavaScript suite: 41 passing tests.
- Focused Python architecture/chart wiring suite: 7 passing tests.
- Runtime publication test compares the copied chart module byte-for-byte.
- Live Curitiba was opened on October 20, but this browser reported
  `GPUInitializationError: WebGL2 is required`; no live chart-functionality claim
  is made from that attempt.
