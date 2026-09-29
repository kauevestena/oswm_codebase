# Thin-node fleet architecture

OSWM nodes are moving from embedded `oswm_codebase` Git submodules to thin,
self-contained node repositories that execute the canonical OSWM build engine
through a reusable GitHub Actions workflow.

## Invariants

A production node is converged only when:

1. its latest complete `oswm-build.json` records the desired core SHA;
2. all required products validate under that build;
3. the same build manifest is present in the deployed Pages site.

Moving a source-code pointer alone is not convergence.

## Target node contents

A thin node owns:

- `config.py` and node-specific configuration;
- generated data and static products during the current publication model;
- `oswm_runtime/`, a version-matched bundle of static JS/CSS/images and
  standalone routing/hazard clients;
- `oswm-build.json`, the authoritative build provenance;
- small caller workflows.

It does **not** own or track `oswm_codebase/`.

During CI, the reusable builder checks out `oswm_codebase` ephemerally into
the runner workspace. Existing Python and shell paths can therefore remain
unchanged during the migration.

## Rollout

### Phase 1 - Compatibility layer

- publish `oswm_runtime/`;
- write `oswm-build.json`;
- make Pages independent of submodule checkout;
- teach fleet observation to understand both architectures;
- add reusable `node_build.yml`.

No node loses its submodule in this phase.

### Phase 2 - Curitiba canary

Curitiba/reference is migrated first.

Acceptance requires:

- no `.gitmodules` dependency or `oswm_codebase` gitlink;
- daily and weekly builds execute via the reusable builder;
- complete required-output validation passes;
- renderer-v3 Positron/Dark Matter basemaps remain present;
- Webmap, routing, hazard analysis, dashboard, data-quality and Data Hub pages
  load from the self-contained runtime;
- repository and live Pages `oswm-build.json` agree on core SHA;
- fleet status reports the node as thin and healthy.

Rollback is a normal revert of the canary migration commit.

### Phase 3 - Production waves

After the Curitiba gate passes, migrate registered production nodes in fleet
rollout order. A wave advances only after every node in the previous wave is
healthy under build-provenance checks.

### Phase 4 - Retire legacy synchronization

After all nodes are thin:

- remove `node_codebase_sync.yml`;
- retire `update_codebase.yml`;
- remove submodule-specific fleet fields/checks;
- retire continuous managed-workflow synchronization where thin callers make it
  unnecessary.

## Scale model

The registry remains the explicit fleet inventory. New nodes are registered
rather than discovered implicitly from an organization.

For the current fleet size, nodes pull the desired core during their own build
cycle, requiring no PAT or fleet-wide write credential. If the fleet later
requires centrally pushed rollout waves, a GitHub App can dispatch the same
stable node-build contract without redesigning node repositories.

## Future storage phase

Removing submodules is independent from generated-output storage. A later
project may stop committing large generated binaries to `main` and publish
Pages directly from build artifacts, while durable geospatial products can be
published through an explicit archive/catalogue mechanism such as STAC.
