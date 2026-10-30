# Curitiba daily-replication pilot

Experimental backend on `migration/geofabrik-incremental-curitiba`; production
defaults remain legacy. This document records implementation and validation,
not permission to roll the backend out to other nodes.

## Running the preview

The only allowed caller repository is `kauevestena/opensidewalkmap_beta`.
Its pilot branch calls `node_replication_preview.yml` and checks out the build
engine at the same full core commit SHA. The reusable preview has read-only
repository permissions, disables checkout credential persistence and has no
commit, push, dispatch or Pages step.

The node caller supports manual dispatch and a push trigger restricted to its
own workflow file on the exact pilot branch. It has no schedule. Manual runs
may supply a retained Geofabrik bootstrap
URL, its actual embedded starting sequence, and a later published end sequence
for replay. Verify those sequences through PBF headers and region state files;
do not derive them from dates. Bootstrap replay uses the normal freshness checks,
so update the input sample when its initial snapshot becomes too old.

With replay inputs empty, the preview restores its validated source cache or
bootstraps a current complete southern Brazil snapshot. It then checks source
and city-layer parity with an independent full snapshot at the same sequence.
An unchanged sequence is tested as a no-op, not reported as a real advance.

The preview runs the normal daily product generator in an ephemeral checkout,
with `OSWM_OSM_UPDATE_BACKEND=geofabrik_replication` and `OSWM_PBF_REGION=sul`.
It uploads `replication-preview/` reports as an Actions artifact; generated
products are not published. The cache is an optimization: eviction, a checksum
mismatch or an unavailable required diff cause validated rebootstrap.

## Implemented behavior

- Sequential daily diffs update a complete regional PBF through locked
  Pyosmium 4.3.1. Source headers, source identity, sequence, timestamps,
  checksums, request/size budgets and candidate promotion are validated.
- Current pedestrian layers and completeness roads use the same source cutoff.
  Full city extraction and canonical comparison handle node movements,
  deletions, relation changes and changes in layer membership.
- Comparison uses published fingerprints, not the cache sequence alone. A
  retry after installation but before successful generation cannot skip
  unpublished data. A core/configuration change still forces regeneration.
- The experimental daily path bypasses the ohsome updater and watcher.
  Completeness history queries are disabled; previously recorded historical
  entries and feeds remain dated and available. New observations use the
  snapshot date. Snapshot differences are explicitly net changes, not complete
  edit or contributor statistics.
- The first version optimizes network transfers. PBF merging, extraction and
  generation still require local processing; feature/tile-level generation
  is not claimed.

## Validation so far

- Python suite: **248 passed, 20 subtests passed** with the locked dependencies
  and a supported Noto CJK font supplied via `OSWM_LABEL_FONT_PATHS`.
- JavaScript suite: **41 passed**.
- Runner syntax, Python compilation and whitespace checks pass.
- Binary fixture coverage includes two sequential advances, multi-day catch-up,
  deletion, node-only movement, tag/category transitions, relation changes,
  unchanged reruns, same-count content differences, missing diffs, corrupt or
  absent caches, stale/future/regressing watermarks, bounded downloads,
  staged-file tampering and retry after acquisition without publication.
- Integration tests deny HTTP requests during city extraction and rendering,
  verify preserved completeness history and source-date observations, and
  verify the preview workflow's read-only/no-publication contract.

Live Curitiba replay and complete product-generation results are recorded as
they complete. No production cutover, rollback rehearsal or other-node rollout
is claimed by these offline checks.

The first GitHub preview reached regional object equality but stopped because
the independent city-extraction path had not created its staging directory.
That path now creates the directory itself and has a dedicated regression.
Candidate product metadata also reads the candidate source cutoff without
advancing the published registry before validation.

Provider transfer size is not total CI transfer size. Hosted runners restore
and save a complete regional cache; that overhead can exceed a small daily diff.
The pilot must measure it before claiming an overall bandwidth improvement.

## Acceptance still required

See [the migration gates](GEOFABRIK_INCREMENTAL_MIGRATION.md): independent
matching-snapshot parity, two real regional advances evaluated for Curitiba,
no-op/recovery evidence, full preview product validation and measured transfer
savings precede a Curitiba publishing canary. The core remains a draft until
the evidence supports a separate rollout decision.
