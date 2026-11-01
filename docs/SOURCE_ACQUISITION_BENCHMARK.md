# Curitiba and Milan acquisition benchmark

This is a read-only sandbox investigation on
`sandbox/metro-extract-curitiba-milan`, not a production source change. Neither
node branch, production cache, generated site, nor schedule is modified.

## Comparison and measurement

The requested comparison is acquisition of the five OSWM raw layers: kerbs,
sidewalks, crossings, other footways and completeness roads. A complete buffered
PBF contains many unrelated objects; a filtered Overpass response or Overture
export is a different representation. Compare the bytes needed by each actual
acquisition method, not just the final GeoParquet export sizes.

The PBF reference inputs are dated **2026-10-29T21:21:26Z**. The local full-source
SHA-256 hashes were checked against the independently downloaded full snapshots
recorded in the metropolitan replay evidence. All five reference counts match
those archived controls. Curitiba uses direct regional parsing; Milan uses a
fresh 25 km buffered extract because the direct regional parser is blocked by
incomplete relation 1023743, as recorded in the earlier experiment.

The source-reference descriptors compare OSM element type/ID, normalized geometry
and retained OSWM tag values. Their compressed maps remain disposable local or
workflow artifacts rather than large git files. Small reference summaries are
saved in `docs/pilots/*_source_reference_20261031.json`.

### OSMnx

OSMnx is version 2.1.1 from the core's locked requirements. The initial experiment
used the exact node polygon for pedestrian features, its bounding box for roads,
and the same historical cutoff as the PBF references. An alternative combined
query used the bounding box and union of all relevant tags, followed by exact
local clipping and the same exclusion/category-priority rules.

The [initial workflow](https://github.com/kauevestena/oswm_codebase/actions/runs/41252443369)
ran harness `c87e6fb73269541c7ecb18e390bca62ec3a00bb4`. Neither city returned a
valid dataset from either historical variant. Failures included:

- Curitiba's literal polygon request was 4,620,635 bytes and received HTTP 413.
- Its combined historical request received an Overpass runtime-error remark
  stating that the query exhausted about 2,048 MB of server memory.
- Milan encountered status-endpoint HTTP 502 and timeouts; its combined
  interpreter request also timed out.
- The former Kumi endpoint returned busy/status responses and timed out.

These are failed acquisition attempts, **not tiny successful downloads**. A
green harness workflow means the outcomes were recorded, not that acquisition
worked. The historical reports retain the failures explicitly.

The initial byte counter also proved invalid for chunked-gzip responses:
urllib3's `raw.tell()` can be zero after a real body has been received. Its
encoded-byte totals are marked invalid and are not used in any bandwidth
comparison. The corrected meter forces streamed reads, counts undecoded response
chunks, then restores the normal decoded response for OSMnx. Tests cover gzip,
deflate, identity encoding, chunked zero-tell behavior, error responses, partial
timeouts, retry bounds, source-provenance identity and range-cache reuse.

An initial [live continuation](https://github.com/kauevestena/oswm_codebase/actions/runs/41253617613)
at `e8e1d34307419cd34a86b6b3941346b6f9ad1a27` was superseded and cancelled.
It is not counted as a completed two-city benchmark. Its artifact nevertheless
contains **completed Curitiba measurements**: the ordinary two-bbox-query cold
download and warm verification, and the ordinary combined cold acquisition and
descriptors. Cancellation interrupted the latter warm stage, not its already
saved cold dataset. These completed stages are retained rather than discarded.

The final [live query-plan comparison](https://github.com/kauevestena/oswm_codebase/actions/runs/41254128986)
uses `cf0e3a4492d845541adb969ba7b210f625921cd5`. It measures:

1. Ordinary OSMnx query construction for one bbox query with all relevant tags.
2. A compact equivalent tag union, with reference expansion performed once.
3. A warm repeat of each successful query against its already acquired cache.

The compact variant still uses OSMnx's feature processing and spatial filtering,
but overrides its private query builder only inside the disposable benchmark
process. It is explicitly a query optimization, not unmodified OSMnx. The
unmodified builder expands node/way/relation references separately for every
tag:value clause; the compact builder uses equivalent anchored tag-value regex
unions and one down-reference closure. Actual output agreement is checked
separately from this query-plan rationale.

Both variants retain the exact city polygon for local pedestrian clipping and
the exact configured tag/exclusion/priority rules. The bbox avoids repeating
thousands of polygon vertices in every Overpass clause. These are optimized
variants, not a claim that the original literal-polygon query succeeded.

Live queries use the latest data offered by each server, rather than expensive
historical lookup. Their database watermarks are recorded. Differences from the
October 29 reference can therefore reflect real intervening edits as well as
selection/representation differences; this is not a same-cutoff parity claim.

Public queries are sequential across cities and the continuation waits for the
initial experiment to finish. The current Private.coffee endpoint and the main
Overpass endpoint are tried with bounded requests, meaningful identification,
and a 45-second query timeout. Main-server rate-limit status handling is retained;
Private.coffee documents no rate-limit slots, so the benchmark does not spin in
OSMnx's recursive status polling there. Partial/error responses
are rejected. HTTP error bodies and metadata count toward measured traffic;
interrupted transfers are explicitly labelled lower bounds. Headers, TLS and
transport framing are excluded. Warm cache hits **do not constitute fresh daily
updates**: reusing an unchanged latest-data query key can simply return old data.

## Completed OSMnx results

Both jobs in the final query-plan workflow completed. The main Overpass endpoint
returned the successful datasets; Private.coffee attempts timed out. Ordinary
combined attempts in that final trial failed on status HTTP 502 (Curitiba) or a
45-second interpreter timeout (Milan). Those failures do not establish that the
ordinary builder can never work: the earlier Curitiba artifact demonstrates
that it did work on another attempt.

| City and method | Successful endpoint response bodies | Cold acquisition stage | Warm repeat |
| --- | ---: | ---: | --- |
| Curitiba, ordinary OSMnx, two bbox queries | 5,942,735 B | 132.196 s | 0 HTTP requests; same layers |
| Curitiba, ordinary OSMnx, combined bbox query | 5,582,915 B | 70.607 s | Interrupted by workflow cancellation |
| Curitiba, compact combined query through OSMnx | 5,582,917 B | 75.245 s | 0 HTTP requests; same layers |
| Milan, compact combined query through OSMnx | 13,550,359 B | 78.589 s | 0 HTTP requests; same layers |

Response totals include the successful endpoint's status responses and compressed
data response. Failed endpoint attempts are retained separately. Some failures
ended before a complete response and their byte totals are lower bounds; they
are not silently counted as zero-cost retries. Cold timings above are for the
successful endpoint, excluding earlier failed attempts. They include acquisition
and GeoDataFrame creation but precede descriptor hashing/serialization. The warm
timing in the JSON includes verification hashing, so it must not be directly
compared as an identical timing stage.

The compact data response alone was 5,582,736 encoded / 32,055,675 decoded bytes
for Curitiba and 13,550,178 encoded / 80,946,492 decoded bytes for Milan. OSMnx's
saved JSON caches were 27,032,228 and 67,838,833 bytes. Restoring those uncompressed
caches is not required for a fresh daily query and would be a different transfer
cost. The benchmark's cold runs start with empty caches.

For Curitiba, **all three completed live variants have identical per-object
identity, normalized-geometry and retained-tag descriptors across all five raw
layers**. Combining the two ordinary queries saved approximately 6% of response
bytes. Compacting the query further reduced its request body from 21,633 to
1,636 bytes, but did not materially reduce the returned dataset. No universal
runtime advantage is claimed from these single trials. Milan's compact request
was 1,531 bytes rather than the ordinary combined request's 20,013 bytes.

The returned server watermarks were **2026-10-31T23:51:51Z** for the final
Curitiba compact query and **2026-10-31T23:55:52Z** for Milan. Relative to the
older October 29 references, the live layers contain small ID/geometry/tag
differences, recorded in `*_osmnx_overlap_20261031.json`. All **11 reference IDs
absent from the live results** were checked against OSM object history up to
the relevant query watermark: **nine were deleted and two Curitiba roads were
retagged from secondary to construction after the reference cutoff**. Thus those
particular absences are explained by actual changes, not inferred selection
loss. This does not turn the comparison into strict same-cutoff parity or prove
that every possible new object/geometry is captured.

The relevant evidence includes `*_osmnx_live_20261031.json`, the completed stages
in `curitiba_osmnx_bbox_20261031.json`, and
`osmnx_missing_reference_audit_20261031.json`. History audit output deliberately
retains only versions, timestamps, visibility and relevant tags, not contributor
names or account identifiers.

### Overture

The tested release is **2026-10-21.0**, also reported as latest by the STAC catalog
at the time of the test. The instrumented reader selects files using Overture's
STAC GeoParquet index and prunes row groups using bbox statistics. It reads all
columns of the selected row groups, then filters individual feature bboxes.
Pedestrian/kerb candidate mapping uses exact city intersection; completeness
roads use the city bbox. This is a measured practical reader, **not a claim of
minimum possible bandwidth**: column projection could reduce traffic further.

The test reads transportation segments, transportation connectors and base
infrastructure. Connectors are reported separately so an optional routing-data
download is not silently charged to a geometry-only layer comparison.

| City | Segments + infrastructure + metadata | Including connectors | Exported files, all three types |
| --- | ---: | ---: | ---: |
| Curitiba | 50,014,117 B | 64,078,370 B | 22,477,923 B |
| Milan | 98,755,046 B | 124,753,900 B | 46,032,405 B |

These are actual HTTP response-body transfers, including footer/index reads,
row-group spillover and repeated ranges. The much smaller export files are not
substituted for network usage. The output GeoParquet remains disposable; the
small request/hash/size reports are preserved in `docs/pilots/`.

The local exploratory reads were repeated on the same `ubuntu-latest`
GitHub-hosted runner class used by the OSMnx benchmark in
[this read-only workflow](https://github.com/kauevestena/oswm_codebase/actions/runs/41254331074),
using `5fd1e99d75e5943ee9103f350fdedfe41ef29b21`. **Both jobs succeeded**; all
HTTP response hashes, transferred-byte totals and candidate-provenance ID sets
match the local exploratory reads exactly. The GitHub-hosted full three-type
reader took 26.223 seconds for Curitiba and 45.490 seconds for Milan, including
selection/export/candidate analysis. Runtime remains a single
observational trial with different remote services, not a controlled claim that
one provider is universally faster. Query setup/dependency installation and node
configuration downloads are excluded from provider-response byte totals.

The segments-plus-infrastructure export files were 16,816,932 bytes for Curitiba
and 35,984,864 bytes for Milan. Caching these thematic city exports could reduce
later reads of the **same monthly release**, but it would not provide fresh
daily OSM edits. It is not equivalent to the one-day-lag requirement.

The schema does support sidewalk/crosswalk segment subclasses and kerb
infrastructure. Infrastructure `source_tags` preserve relevant original OSM
attributes: the downloaded kerb candidates include wheelchair, tactile paving,
kerb type and kerb-height values. For example, the Milan candidates contain
36,951 tactile-paving values and 596 kerb-height values. Overture should not be
dismissed as having no kerb or accessibility data.

## Overture provenance overlap

Only whole-feature/geometry OpenStreetMap source IDs are used; `/routes` and
other attribute-only provenance are excluded. GERS features can merge/split OSM
features and have scoped subclasses. A count of GERS segments is therefore not
compared directly to a count of OSM ways.

| OSWM reference layer | Curitiba reference IDs found under tested candidate mapping | Milan reference IDs found under tested candidate mapping |
| --- | ---: | ---: |
| Kerbs | 97.73% | 99.83% |
| Sidewalks | 99.67% | 99.69% |
| Crossings | 99.88% | 99.79% |
| Other footways | 76.86% | 74.35% |
| Completeness roads | 99.32% | 99.90% |

This is **provenance overlap, not geometry/tag parity or an exhaustive audit of
all Overture themes**. Other-footway mapping is especially incomplete: it uses
transportation class/subclass candidates plus matching infrastructure raw tags.
Additional mappings/themes could recover more features. The reports separately
record reference IDs found anywhere in the three queried types, without claiming
that those records retain the right category or attributes. The input dates also
differ, so unmatched IDs must not automatically be called ingestion losses.

## Freshness and suitability

Overture transportation is published monthly. More specifically, every tested
transportation whole-feature source record reported OSM input version
`2026-10-10`, and every tested infrastructure record reported
`2026-10-04T00:00:00.000Z`. These are source-version metadata, not the last-edit
times of individual features. The October 21 release must not be presented as
an October 29/30 OSM snapshot.

Overture is therefore a plausible source for normalized pedestrian geometry and
much kerb/accessibility data, but it does **not meet the requested approximately
one-day update lag** as a sole source. Using it would require schema/GERS/source-ID
adaptation and coverage validation, rather than applying Geofabrik OSM diffs to
its records. Neither a production Overture adapter nor release-changelog updates
were implemented in this sandbox.

The previous buffered-PBF estimate remains 20.45–20.69 MB incoming source data per
normal Curitiba update and 107.18–107.29 MB for Milan, including the incoming PBF
cache and regional changes. It excludes cache upload and initial/recovery regional
downloads. Its known reference-only fallback safety gaps remain unresolved.

## Acquisition decision suggested by this sample

| Source strategy | Curitiba incoming source data | Milan incoming source data | Freshness in the test |
| --- | ---: | ---: | --- |
| Compact filtered Overpass query processed by OSMnx | 5.58 MB | 13.55 MB | Current server watermarks, within minutes |
| Buffered PBF cache restore plus daily regional changes | 20.45–20.69 MB | 107.18–107.29 MB | Daily Geofabrik snapshots/diffs |
| Overture cold area read, segments + infrastructure + metadata | 50.01 MB | 98.76 MB | Monthly release; observed OSM input versions October 10 / October 4 |

MB means 1,000,000 bytes. This compares measured successful filtered-query bodies
with the earlier buffered-PBF normal-run estimate and a measured cold Overture
read. It does not compare identical source representations, include all CI
traffic, hide provider failures, or claim a globally optimal Overture projection.

Filtered daily full acquisition is substantially smaller than restoring the
complete metropolitan source PBF in these tests: roughly 73% lower incoming
source bytes for Curitiba and 87% lower for Milan. This makes a tested bbox/tag
query with local exact filtering a promising alternative to small-PBF spatial
replication for OSWM. The observed public-service failures still justify a PBF
fallback. A production query adapter and any provider/cutover changes require
separate implementation and validation; none are deployed here.

Overture is a credible normalized-data option with useful kerb/accessibility
coverage, but would require accepting its release/input lag and adapting its
schema and source identities. It is not the sole source for the requested
approximately one-day lag.

## Reproduction

With the core's locked Python dependencies:

```sh
python sandbox/test_source_benchmark.py
python sandbox/source_benchmark.py --city curitiba --snapshot live \
  --work /tmp/oswm-source-curitiba-new
python sandbox/source_benchmark.py --city milan --snapshot live \
  --work /tmp/oswm-source-milan-new
python sandbox/source_benchmark.py --city curitiba --snapshot live \
  --variants bbox_two_queries --work /tmp/oswm-source-curitiba-two-new
python sandbox/overture_probe.py --city curitiba --release 2026-10-21.0 \
  --boundary /path/to/node/data/boundaries/polygon.geojson \
  --config /path/to/node/config.py --work /tmp/oswm-overture-curitiba-new
```

Use fresh empty sandbox directories. Bbox queries and public-service load are
bounded. No commands install acquired inputs into a production node or invoke a
publisher.

The compact machine-readable outcome is
[`source_acquisition_summary_20261031.json`](pilots/source_acquisition_summary_20261031.json).

Primary sources:

- <https://osmnx.readthedocs.io/en/stable/user-reference.html>
- <https://docs.overturemaps.org/guides/transportation/>
- <https://docs.overturemaps.org/schema/reference/base/infrastructure/>
- <https://docs.overturemaps.org/schema/reference/base/types/infrastructure_class/>
- <https://docs.overturemaps.org/getting-data/overturemaps-py/>
- <https://wiki.openstreetmap.org/wiki/Overpass_API>
