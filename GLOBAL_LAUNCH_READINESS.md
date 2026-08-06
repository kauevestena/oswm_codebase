# OSWM global-launch readiness

## Decision

The shared codebase is ready to support a **controlled Milan pilot**, but a
many-node global launch should wait for hosted cold-start, no-change, and
incremental evidence from Milan and at least two additional, operationally
different nodes.

This branch closes the repository-safety and reproducibility blockers found in
the `opensidewalkmap_beta` template. It does not claim that best-effort public
data providers can sustain simultaneous global cold starts.

## What was stressed

The investigation started from a shallow clone of the reference node and
changed only its node identity to Milan. That exposed two separate classes of
risk:

1. A config-only clone retained hundreds of Curitiba-generated files,
   including boundaries, raw and processed data, PMTiles, update state,
   quality reports, statistics, API pages, and embedded URLs. The Milan branch
   removed 369 tracked generated files (about 302 MB) before testing.
2. The automation could report success after failed setup commands, replace
   the entire node workflow directory, stage the whole checkout, pull an
   unreviewed latest submodule revision, and collide across scheduled writer
   jobs. Pages publication was implicit or absent, and timestamps mixed local
   wall time with UTC interpretation.

The Milan boundary resolves to OSM administrative relation `44915`, with the
configured fallback bounds `(45.3867381, 9.0408867, 45.5358482, 9.2781103)`.
An earlier public-provider probe showed the full Milan OSWM tag union timing
out at one public Overpass endpoint; even a highway-only subset returned about
70,000 elements. Fleet enrollment therefore needs staggered jobs and, beyond
the pilot, controlled bulk/Overpass capacity.

## Implemented contracts

### Clean node initialization and stale-output removal

`node_outputs.py` is the canonical generated-output contract.

```bash
# Dry-run: list inherited generated paths without changing them.
python oswm_codebase/node_outputs.py --root . reset-node

# Apply only when deliberately turning a template into a new node.
python oswm_codebase/node_outputs.py --root . reset-node --apply

# Reconcile all derived products before a complete regeneration.
python oswm_codebase/node_outputs.py --root . reset-derived

# Enforce the deployment-product contract and GitHub size guard.
python oswm_codebase/node_outputs.py --root . require
python oswm_codebase/node_outputs.py --root . validate-sizes --max-mib 95
```

Both reset commands refuse filesystem roots and directories that do not look
like OSWM nodes. Initialization preserves `README.md`, `index.html`,
`config.py`, Git metadata, and the `oswm_codebase` gitlink, then recreates only
an empty update registry. Derived reconciliation preserves the weekly
`quality_check/keys_without_wiki.json` input while deleting undeclared products
from complete-rebuild directories.

### Reproducible node identity and provider behavior

- `OSM_RELATION_ID` avoids fuzzy city selection for known administrative
  boundaries. Nominatim lookup has an OSWM user agent, timeout, bounded retry,
  exponential backoff, and polygon validation.
- Overpass cold acquisition has explicit endpoints, bounded attempts, backoff,
  and actionable terminal failure. It never retries forever.
- The fallback bounding-box GeoDataFrame is explicitly EPSG:4326.
- Incremental OHSOME updates are prepared before publication, fail closed on a
  missing layer/provider error, deduplicate element identities, and record the
  provider watermark actually applied rather than an unverified wall-clock
  time.

### Deterministic pipeline state

`pipeline_decision.py` emits JSON with one of three modes:

- `generate`: cold start, OSM change/inconclusive check, or explicit force;
- `rebuild`: unchanged raw inputs but a new core revision or missing derived
  product;
- `skip`: no OSM change, the exact core revision already succeeded, and all
  declared outputs exist.

`OSWM_FORCE_REGEN` is wired into the daily runner. A codebase revision change
forces a derived rebuild even when the OSM watcher reports no changes. The
daily runner records success only after every stage and every required output
passes.

Registry writes use timezone-aware UTC ISO-8601 strings. Existing
`DD/MM/YYYY HH:MM:SS` values are interpreted in `METADATA_TIMEZONE` (UTC when
unspecified) and remain readable during migration.

### Safe fleet automation

- All writer workflows use `oswm-node-writer-${{ github.repository }}` with
  overlap disabled.
- Scheduled/setup jobs check out the node's recorded gitlink. They do not pull
  the latest core branch behind the node commit's back.
- The core updater takes an exact SHA, verifies that it is a commit reachable
  from core `main`, then records that exact gitlink.
- Workflows stage only named output profiles through `node_outputs.py`; broad
  `git add .` and `git add -A` are absent.
- Publication uses normal commits, fetch/rebase, and a non-force push.
- GitHub Pages is deployed by a dedicated least-privilege workflow.
- `special_updates.py` synchronizes only `workflows/manifest.json` entries,
  removes retired core workflows, preserves node-only workflows, and no longer
  overwrites the node `.gitignore`.
- Daily and weekly cron expressions are literal node configuration. Managed
  synchronization renders them, so fleet staggering survives future core
  updates.

### Reproducible runtime and CI

`requirements.txt` is an exact, universal Python 3.12 lock generated from
`requirements.in`; the development lock adds pytest and PyYAML. Core CI runs
the Python suite, browser-module tests under Node, shell parsing, and package
consistency checks.

Current local evidence on this branch:

- Python: **91 passed, plus 12 subtests**;
- JavaScript: **28 passed**;
- daily-runner fixtures: cold start, confirmed no-change, and codebase-change
  rebuild all passed;
- all runner shell scripts parse;
- all workflow YAML parses;
- Python compilation and `git diff --check` pass;
- regenerating both locks produces no diff.

These are contract and fixture tests. They are intentionally not presented as
a successful live Milan generation.

## Enrolling Milan (or another new node)

1. Shallow-clone the reference node without trusting its generated state.
2. Create an isolated branch and initialize the recorded submodule gitlink.
3. Run the dry reset, inspect the listed paths, then apply it.
4. Set at least `CITY_NAME`, `CITY_SHORTNAME`, `REPO_NAME`, bounding box,
   midpoint, `OSM_RELATION_ID`, `NODE_DAILY_CRON`, and `NODE_WEEKLY_CRON`.
5. Pin a core revision that passed core CI; do not configure the submodule to
   float automatically.
6. Run `python oswm_codebase/special_updates.py` and review the workflow/state
   diff.
7. Run core tests and the node readiness audit before any generation.
8. Run one read-only hosted cold start with logs and resource metrics. Do not
   push its output until the required-output, PMTiles, stale-output, and 95 MiB
   gates pass.
9. Run an immediate second cycle and require the machine decision to be
   `skip`. Then test a known small incremental fixture/change.
10. Visually verify the deployed homepage, MapLibre themes, charts, printable
    snapshot, routing, hazard views, quality pages, statistics, metadata, and
    static API.

## Remaining launch gates

Priority 0 for Milan:

- complete a hosted cold start within the configured timeout;
- prove a subsequent no-change run is idempotent;
- prove an incremental update changes only the expected inputs/products;
- confirm every required product is nonempty and every staged file is below
  95 MiB;
- validate Pages environment configuration and every published link/view;
- record real duration, peak memory/disk, provider attempts, and output sizes.

Priority 0 before many nodes:

- provide controlled Overpass/regional-extract capacity and a documented
  provider budget instead of relying on public endpoints for simultaneous
  cold starts;
- test concurrent core synchronization and scheduled updates across multiple
  pilot repositories;
- introduce fleet observability for node/core SHA, last successful stage,
  duration, sizes, provider failures, and deployment status;
- decide whether generated deployment artifacts should remain in permanent Git
  history or move to a bounded artifact/publication store.

Priority 1:

- extend bounded retry/circuit-breaker policy to OSM changesets, OHSOME
  watcher history, Copernicus DEM, and every optional acquisition provider;
- add regional load tests and failure-injection tests;
- automate node enrollment from a versioned registry once the manual Milan
  acceptance sequence is green.

## Launch criterion

Milan is accepted only when cold, no-change, and incremental hosted runs pass,
obsolete sentinels are removed, the exact core SHA is visible in node state,
no history is rewritten, Pages is verified, and provider failure yields a
bounded actionable error rather than a false success. Global enrollment begins
only after the same contract passes on multiple staggered pilots.
