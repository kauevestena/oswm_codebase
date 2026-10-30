# Daily Geofabrik replication migration: Curitiba pilot

Status: implementation plan, 2026-10-30. This change creates the plan only;
the replication implementation and live pilot have not run.

## Objective and boundary

Replace ohsome as the authority for current-data acquisition and change detection.
Download a complete regional PBF once, then consume that region's daily replication
files. Accept approximately one day of source lag, expose the actual source cutoff,
and tolerate occasional publication delays without claiming that stale data are current.

Development branch: `migration/geofabrik-incremental-curitiba` in
`kauevestena/oswm_codebase`, starting from
`44cafc7c0f582ee1732e515446ed11a418b13afa`.

The only live test node is Curitiba:
`kauevestena/opensidewalkmap_beta`. Use a separate node branch,
`pilot/geofabrik-incremental-curitiba`, during preview testing. Pin every
preview to the exact core commit being evaluated. This node branch is proposed,
not created by this planning change.

Do not merge the core branch, change fleet defaults, modify another node, or
dispatch another node's workflows as part of this pilot. Offline fixtures and
the normal core test suite remain in scope.

## Verified starting point

At the inspected core revision:

- `getting_data.py` tries ohsome incremental acquisition, then Overpass, then
  the existing Geofabrik snapshot fallback.
- `pbf_acquisition.py` already resolves covering regions, bounds downloads,
  checks snapshot freshness/checksums, and supplies OSMnx-compatible features.
  It reads the replication timestamp but does not implement a persistent
  sequence-driven updater.
- `runners/daily.sh` calls the ohsome watcher before `pipeline_decision.py`.
  The watcher can report no changes when its provider watermark predates
  the local acquisition, causing a skip without a current source check.
- Watcher rendering also makes historical ohsome requests.
  Changing only the acquisition function would leave that dependency.
- Completeness obtains its roads separately through Overpass/PBF and can query
  ohsome for historical months. Those roads need to use the same source cutoff
  as the pedestrian layers in the pilot.
- The reusable builder, `.github/workflows/node_build.yml`, always stages,
  commits and deploys generated products. It currently caches elevation only.
- Curitiba's daily and weekly callers use the reusable workflow at `main`
  and pass `core_ref: main`. No branch rollout is currently configured.

The inspected Curitiba tree/ref was
`0d9eb8896079e0bebaf5cce3f7b28f5e364b5f73`. Re-read the node head before
implementation; normal scheduled outputs may advance it.

## Decisions for the first implementation

| Question | Decision |
| --- | --- |
| Current-data provider | Opt-in Geofabrik regional replication. Existing nodes retain the legacy backend by default. |
| Pilot region | Candidate `sul` (southern Brazil). Verify that its download polygon covers the complete stored Curitiba boundary and completeness query area before fixing the region. |
| Retained baseline | Complete provider-region PBF, including non-pedestrian objects and referenced nodes/relations. Do not replicate a pedestrian-only or naively clipped city file. |
| Update tracking | Provider replication URL, region identity, sequence and source timestamp from validated headers/state. Never infer a sequence from today's date. |
| First optimization | Incremental network acquisition, followed by full local city extraction and semantic comparison. |
| Product generation | Reuse existing generation when relevant city data change; skip expensive generation only after a successful comparison. Per-feature and per-tile regeneration is a later optimization. |
| History during pilot | Preserve cached historical results and disable ohsome history queries in the experimental backend. Record new local snapshot observations with their own source/method. |
| Publication | Read-only preview first. Any later live publication is confined to Curitiba and retains exact core provenance. |

Proposed configuration names, to finalize during implementation:

- `OSM_UPDATE_BACKEND = "legacy"` by default; pilot override
  `"geofabrik_replication"`.
- Existing `PBF_REGION`, download-size and freshness options remain usable.
- `OSM_HISTORY_BACKEND = "cached"` for the pilot, with no synthetic zero
  contributions when historical information is unavailable.

## Source-to-product flow

1. Load the last valid regional PBF and its matching local state.
2. Fetch the region's published replication state and select a fixed target sequence.
3. Download the contiguous missing changes, with bounded requests, retries,
   bytes, catch-up range and elapsed time.
4. Apply changes to a candidate regional PBF. Validate headers, object
   references, source cutoff, monotonic sequence and checksum.
5. Extract all pedestrian categories and completeness roads from that same
   candidate source using the node's actual geometry and tag rules.
6. Compare canonical city data with the last published raw inputs.
   Relevant changes include identities, tags, geometry, layer membership and
   metadata used by downstream products. Road changes also invalidate
   completeness products even when pedestrian layers are unchanged.
7. Generate and validate required outputs when data, configuration or core
   generation logic changed, or required products are missing.
8. Save provenance and promote validated state. Publish only in the later
   Curitiba publishing phase.

An unchanged city can still advance its verified source cutoff. Represent this as
"checked against source at T; no relevant city changes", not as edits at T.
Provider status checks, data processing and publication have separate timestamps.

## Correctness and recovery

### Dependencies and filter transitions

A node move can change an unchanged way's geometry; a changed member can affect
a relation. Tag removal can move an existing object out of a layer, and tag
changes can move it into a different layer. Real deletions and movement across
the city boundary also need correct handling.

The initial implementation avoids incomplete feature patching: apply changes to
the full regional object store and re-extract the city. A future feature-level
updater must compute the affected dependency closure and demonstrate equivalent
results before replacing this step.

### Checkpoints, failures and parallel writers

Keep a bundle containing the regional PBF, state, checksum and source identity.
Build updates in a separate candidate directory; retain the last good bundle
until the candidate validates. Reject mismatched PBF/state pairs and gaps in the
replication sequence. Serialize pilot writers.

Distinguish the sequence applied to the source cache from the sequence represented
by the published node products. If generation or publication fails after source
acquisition, retry extraction/comparison against the published raw data even when
there are no additional provider changes. A restored cache must never cause an
unpublished change to be skipped.

Do not advance public acquisition/provenance records on failed processing. Do not
replace good products with empty or partial results. A legitimate empty category
must be distinguished from failed extraction and covered by fixtures.

### Cache persistence

The existing ephemeral runner is insufficient for incremental-only downloads.

For the pilot, add explicit restore/save of an isolated PBF/state bundle using
GitHub Actions cache. Use versioned keys scoped by repository, pilot mode,
provider, region and source sequence; retain the checksum/state manifest with
the file. Save a new validated bundle rather than trying to overwrite an
immutable cache key. Keep preview and publishing caches separate.

Treat cache as an optimization that may disappear. A cache miss, checksum
failure or missing required diff triggers a validated full-snapshot bootstrap,
never reuse of an unverified sequence record. Do not commit regional PBFs,
downloaded diffs or cache internals to the node repository or Pages.

Measure download size, working disk space and restore/save time before choosing
a long-term store. A durable object store is an optional later improvement,
not a prerequisite or new service dependency for this pilot.

### Retention and provider behavior

Geofabrik currently retains regional diffs for 100 days. Rebootstrap if the
necessary range is unavailable; also test a missing file within that period.

Diffs belong to their provider region. Do not mix official global sequences,
another region's files, or an Overpass result into the same replication chain.
Region-identity changes require a new baseline. Provider clipping-boundary
changes can appear in regional diffs and must not be labelled automatically as
individual mapper deletions.

Preserve the current no-regression guard: a source cutoff older than the
published acquisition cannot replace it. A fresher Overpass result may remain
a separately attributed recovery path, but cannot become the base for
regional diff application.

Proposed pilot freshness policy: warn above 48 hours and reject acquisition above
72 hours, keeping the last successful products. Report an unavailable or stale
source explicitly rather than returning a successful "no changes" decision.

## History and user-visible behavior

The experimental daily path must make no requests to `api.ohsome.org`, including
during watcher rendering and completeness generation.

- Preserve historical values with their original source and time coverage.
- Disable the historical ohsome backfill in the pilot. Mark missing historical
  coverage as unavailable; never replace it with zeros.
- Collect new daily snapshot comparisons and local completeness observations
  using the dataset cutoff as the observation date.
- Label snapshot differences as net differences between observations. They do
  not count every intervening edit or provide a complete contributor history.
- Keep optional OSM API versioning/changeset features separate from replication.
  Public Geofabrik files omit contributor names, user IDs and changeset IDs.
- Show source cutoff and processing time separately in the watcher/provenance.

Backfilling arbitrary past history or replacing contributor analytics with a new
history service is a separate project, not a silent feature removal.

## Work packages and gates

### 1. Replication engine and offline regression fixtures

Proposed files: `pbf_replication.py`, focused binary-fixture tests and shared
helpers extracted from `pbf_acquisition.py` where useful.

Implement bootstrap, header/state validation, bounded diff acquisition,
candidate application, bundle promotion, provenance and recovery. Use the locked
Pyosmium version already in the project; verify the available API rather than
assuming current upstream documentation matches that version.

Gate: binary PBF + OsmChange fixtures pass for creation, modification, deletion,
node-only moves, relation-member changes, layer/tag transitions, crossing and
enclosing geometries, missed days, idempotent reruns, corrupt caches, missing
diffs, stale/future timestamps and interrupted application.

### 2. Opt-in daily integration

Touchpoints: `getting_data.py`, `pipeline_decision.py`, `runners/daily.sh`,
`datahub/watcher/watcher_lib.py`, completeness acquisition, build provenance
and config documentation.

Run the replication source check before an experimental daily skip decision.
Reuse the same source for roads and pedestrian features. Isolate history rendering
from acquisition decisions. Preserve legacy behavior for non-opted-in nodes.
Keep existing derived-rebuild semantics: a forced product rebuild must not mean
an unnecessary full provider download.

Gate: tests deny all ohsome HTTP requests in the experimental daily path; cover
no-change source advancement, road-only changes, configuration changes, failed
publication/retry and unchanged behavior with the legacy backend.

### 3. Curitiba-only preview harness

Add a dedicated read-only reusable preview workflow on the core branch. Invoke
the same runner and output validators as the normal build, but stop before
staging, committing or dispatching Pages. Enforce the Curitiba repository
allowlist in the preview workflow.

On the proposed Curitiba pilot branch, adapt the existing
`data_daily_updating.yml` caller to manual dispatch only and call that preview
workflow at a full core SHA. Set `core_ref` to the same SHA. Dispatch the already
registered daily workflow against the pilot branch; no default-branch schedule
or caller change is needed for preview.

Use the Curitiba boundary/configuration from its repository, with explicit pilot
overrides in the isolated preview workspace. Upload comparison reports, product
validation results, provenance, timing, transfer sizes and representative preview
outputs as run artifacts. Do not upload the regional baseline as a public product.

Gate: prove repository products and deployed Pages were unchanged by preview,
and that no other node workflow was invoked.

### 4. Live parity and efficiency evidence, Curitiba only

Perform a historical replay using retained regional snapshots if a matching pair
is available; otherwise bootstrap and wait for the next published sequence.
A repeated run at the same sequence tests idempotency, not live incrementality.

Compare the result of applying N-1 to N changes against a separately obtained
full provider snapshot at exactly N. Validate embedded cutoffs/sequences; do not
compare against a moving "latest" snapshot at an unmatched time.

Require semantic parity for the affected regional objects and all city raw layers:
OSM type/ID, relevant tags, node coordinates and references, relation members,
canonical geometry/CRS and counts. Document any canonicalization; do not weaken
the comparison to counts or image similarity.

Also run a negative control that omits a real/fixture change and demonstrate that
the comparator detects it.

Measure:
- initial snapshot bytes/time and peak working disk space;
- subsequent diff bytes, catch-up time and PBF processing time;
- cache restore/save overhead;
- city extraction/comparison and product generation time;
- snapshot age and sequence advancement.

Gate: at least two distinct real incremental advances for Curitiba, a repeated
no-new-sequence run, a catch-up/recovery exercise, parity at a matching snapshot,
and passing required-output/runtime/tile validation. Record complete run links
and exact core/node SHAs. Report the actual savings rather than assuming PBF
rewriting is constant-time.

### 5. Curitiba publication and rollback rehearsal

After preview gates pass, the next stage is a Curitiba-only publishing canary
using a fixed experimental core SHA and the validated cache/update path.
Any node caller/configuration change must remain specific to Curitiba.
A reusable workflow's reference and its core checkout must both point to the
intended tested revision.

Serialize with Curitiba's normal writers. Validate repository products, deployed
`oswm-build.json`, runtime resources, PMTiles, routing, hazards, dashboard,
completeness and freshness labels. Do not leave scheduled weekly/setup jobs able
to silently overwrite pilot products with an inconsistent backend; coordinate
their Curitiba-only references or keep publication manual while scheduling is
being evaluated.

Rehearse rollback to the recorded stable core and last known-good node products.
Keep pilot state separate and restore backend-compatible provenance/history.
A newer replica source must not be used to disguise an older restored dataset.

The core branch remains unmerged and no additional node is enrolled by this plan.
A broader rollout needs a separate decision based on the Curitiba evidence.

## Deliverables and completion checklist

- [x] Separate core migration branch and reviewable implementation plan.
- [ ] Replication engine and offline regression coverage.
- [ ] Opt-in daily integration with zero ohsome calls in the experimental path.
- [ ] Persistent, validated pilot cache with tested bootstrap/recovery.
- [ ] Manual Curitiba preview workflow pinned to an exact core SHA.
- [ ] Matching-snapshot parity and measured incremental-transfer savings.
- [ ] Two live incremental advances plus no-op and catch-up evidence.
- [ ] Curitiba product/browser/deployed-provenance validation if publication begins.
- [ ] Rollback evidence and concise pilot report.
- [ ] Separate decision about merging the core or enrolling another node.

## Primary references

- [Geofabrik download/update behavior, metadata and retention](https://download.geofabrik.de/technical.html)
- [Geofabrik region catalogue](https://download.geofabrik.de/index-v1.json)
- [Southern Brazil replication state](https://download.geofabrik.de/south-america/brazil/sul-updates/state.txt)
- [Pyosmium replication tools](https://github.com/osmcode/pyosmium/blob/master/docs/user_manual/10-Replication-Tools.md)
- [Existing full-snapshot fallback](PBF_FALLBACK.md)
- [Existing thin-node build contract](THIN_NODE_MIGRATION.md)

Upstream documentation can describe newer Pyosmium versions; implementation and
tests must use the project's actual locked dependency version.
