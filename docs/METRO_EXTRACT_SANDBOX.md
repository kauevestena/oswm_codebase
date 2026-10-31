# Buffered extract sandbox: Curitiba and Milan

This experiment is isolated on `sandbox/metro-extract-curitiba-milan`, stacked
on the existing Geofabrik migration branch. No node branch, live dataset,
production cache, schedule, or publisher is changed. The workflow has only
`contents: read` permission and does not persist checkout credentials.

## Question and method

Can a small metropolitan PBF be maintained from Geofabrik regional daily diffs,
with a reference-integrity check triggering a full-source rebuild when needed?

The test uses a rectangular 25 km latitude-adjusted buffer around each node's
configured bounding box. This includes neighbouring municipalities but is not
an administrative metropolitan boundary. Extraction uses Osmium's `smart`
strategy, completing ways and multipolygons from the available source.

For each city, the source snapshots dated 2026-10-28, 2026-10-29, and 2026-10-30
are downloaded independently. Embedded replication URL, sequence and timestamp
headers identify the matching daily diffs. Regional replay must equal the
independently downloaded full snapshot before it can be used as a control.

Each metropolitan update applies the **entire regional diff**, then extracts
the buffered area again. This avoids naively discarding changes based only on
node positions or on the pre-existing object IDs. The candidate is tested for:

- all way-to-node references;
- multipolygon-member references, including available dependencies;
- object equality with a fresh buffered extract from the full source;
- canonical geometry/tag/identity fingerprints for the actual OSWM raw layers:
  kerbs, sidewalks, crossings, other footways, and completeness roads.

If the direct full-regional-source OSWM parser fails, that error is retained
verbatim. The experiment then separately compares candidate layers with the
fresh buffered control. `control_layer_scope` explicitly distinguishes these
two cases. Agreement with a fresh buffered control does **not** establish that
direct full-regional-source OSWM extraction worked or that geographical
extraction can never omit a relevant enclosing/crossing object.

The first two checks form the proposed local acceptance guard. The latter two
are independent **test oracles**, requiring full snapshots, and are not counted
as checks a daily small-cache runner could perform without downloading them.
Other route and administrative relations may be incomplete by extraction design;
the guard does not claim to prove that every relation is present or complete.

When the local guard fails, the experiment rebuilds the metropolitan baseline
from the corresponding full snapshot, tests its city layers against the control,
and uses that baseline for the next replay step. It separately reports any
candidate that passes the local guard but differs from the city-layer oracle.
Such an outcome is an unsafe false acceptance, never a successful migration.

## Synthetic cases

Six small OSM fixtures exercise the mechanism without relying on the particular
edits made during the real replay window:

| Edit | Local guard | Result |
| --- | --- | --- |
| New way references an unchanged outside node | Rejects | Full-source rebuild restores parity |
| New multipolygon references an unchanged outside way | Rejects | Full-source rebuild restores parity |
| Outside node moves inside; unchanged parent way was absent | Passes | Way is silently omitted; no rebuild is triggered |
| Outside node moves inside; unchanged parent way and multipolygon were absent | Passes | Way/relation are silently omitted; no rebuild is triggered |
| Existing local way is deleted | Passes | Matches full-source control |
| Ordinary new local way with available nodes | Passes | Matches full-source control |

The unknown-parent cases show a structural limit: a file can have no dangling
references while still be missing relevant objects. Increasing a finite buffer
does not make the reference-only guard a completeness proof. These fixtures do
not estimate how often such edits occur in Curitiba or Milan.

## Reproduction

Install the core's locked Python requirements and `osmium-tool`, then run from
the core checkout:

```sh
python sandbox/metro_extract_probe.py \
  --cities curitiba milan --buffer-km 25 \
  --dates 261028 261029 261030 \
  --work /tmp/oswm-metro-probe-new \
  --report /tmp/oswm-metro-report.json
```

Use a new empty work directory. The dates are historical test inputs, not a
production freshness policy. Dated snapshots are subject to provider retention.
The report records node revisions, source hashes, actual sequences/cutoffs,
download sizes, comparison results, and fallback decisions. Regional controls
and intermediates remain disposable; only the small evidence reports belong in
git. The workflow runs each city in its own disposable runner and uploads JSON
evidence even if a later stage fails.

## Transfer interpretation

For a hosted runner, the relevant normal acquisition cost is the **whole cached
metropolitan PBF plus the regional diffs**, not just the diff download. A rebuild
adds a full regional snapshot download. Independent full snapshots fetched for
this experiment are control overhead and must not be presented as ordinary
incremental traffic. Cache upload after a successful run would be additional
traffic; this experiment deliberately does not save any shared source cache.

## Deployment conclusion

The reference-only fallback mechanism is **not safe to deploy**, even if the
real replay window happens to match perfectly. Possible remedies include a
synchronized dependency/parent lookup source or a service that produces
complete city snapshots/diffs. A stronger conservative guard for objects
entering the area is also worth investigating, but would need separate
adversarial validation and measurement of how often it forces a full rebuild.
Full regional state on a persistent updater remains the baseline for retaining
source dependencies; Milan's direct feature-parser blocker is a separate
unresolved issue below.

## Observed results

The initial [two-city workflow](https://github.com/kauevestena/oswm_codebase/actions/runs/41248467389)
tested implementation `d8443894d77dcc2a98dc6da044933f0a2da6e0ac`.

Curitiba's job completed successfully. Both real advances, **2505 → 2506 →
2507**, matched the independent full regional sources, their fresh metropolitan
extracts, and all five OSWM raw layers. Local guards passed and no real replay
fallback was needed. The baseline was **20,175,849 bytes**; the last updated
cache was **20,188,400 bytes**. Cache download plus regional diff/state download
would have been **20,453,927** and **20,686,859 bytes** for the two updates,
versus full snapshots of **428,903,024** and **429,012,750 bytes** respectively.
That is approximately **95.2% less acquisition download traffic**, excluding
cache upload, package installation, experiment controls and other products.

[Curitiba evidence](pilots/curitiba_metro_20261031.json) records exact hashes,
node revision, timestamps, layer counts/fingerprints, and the six fixture tests.
The second real update changed completeness roads from 29,849 to 29,850 while
the four pedestrian layers retained the same fingerprints.

Milan's initial job stopped at a **separate direct-regional-parser blocker**.
The initial cache was **106,696,464 bytes**. Its first real advance, **4012 →
4013**, passed the regional replay oracle and exactly matched the fresh
metropolitan extract at **106,708,121 bytes**. Both local reference guards
passed. However, the full Nord-Ovest source could not be parsed into OSWM city
layers: `_write_spatial_subset` raised `Incomplete PBF relation 1023743`.

The current OSM API identifies relation 1023743 as the boundary of the Réserve
naturelle de la Grande Sassière, a French protected area tagged `foot=yes` and
`access=no`. This diagnostic lookup is current OSM metadata, not a replacement
for the dated snapshot control. Source:
<https://www.openstreetmap.org/api/0.6/relation/1023743>.

[Milan initial failure evidence](pilots/milan_metro_initial_20261031.json) is
retained. The initial whole workflow is correctly marked **failed**, despite
the successful Curitiba job and Milan's first object comparison. No Milan
raw-layer success is inferred from that failed run.

The [Milan continuation](https://github.com/kauevestena/oswm_codebase/actions/runs/41249489263)
uses `2c3741ddb86599c4bbc79a653a830684dea614b6`. It retains any direct-source
parser failures and explicitly labels a fresh buffered control when needed.
Pushes on the experimental branch now repeat Milan only; manual inputs can
select either or both cities. Final Milan results will be added when complete.
