# Overpass change-query sandbox

Branch: `sandbox/overpass-change-queries`; draft [PR #63](https://github.com/kauevestena/oswm_codebase/pull/63).
This experiment does not change a node repository, production source, publisher,
or schedule. It is stacked on the earlier [source benchmark](SOURCE_ACQUISITION_BENCHMARK.md).

## Decision

Use **daily filtered full acquisition plus local change detection** as the
default for the current hosted-runner migration. Both cities completed that
route. The daily Milan delta timed out on both endpoints, and Curitiba's daily
delta could not be replayed against an independent historical bootstrap.
Receiving a small XML response is not sufficient evidence of correct updates.
Keep `adiff` as a sandbox experiment; it may be useful with persistent local
state, but this test has not validated a complete overnight update.
**No replay of a non-empty live delta was validated in this experiment.**
Full acquisition is also subject to public endpoint availability: Milan's later
repeat failed before an independent full control could be obtained. A failed
run must retain the last verified data and retry later; it must not publish an
empty dataset or treat an error as "nothing changed". This sandbox does not
install or schedule a production migration.

## What is being tested

Use `[adiff:"START","END"] ... out meta geom;`, rather than upserting everything
whose own timestamp is recent. An augmented diff describes changes to a query's
result: `create` includes existing objects entering the query; `delete` includes
still-visible objects leaving it. A way's geometry can change while its version
stays the same. The [Overpass manual](https://dev.overpass-api.de/overpass-doc/en/analysis/museum.html)
and [format specification](https://wiki.openstreetmap.org/wiki/Overpass_API/Augmented_Diffs)
describe these cases. Changes to nested relation members do not necessarily emit
the parent relation, so the cache retains references and reconstructs geometry.

The query uses the configured city bbox and the union of pedestrian/kerb tags
and completeness-road classes. Tagged relation roots are restricted to
`multipolygon`/`boundary`, which are the relation types OSMnx processes as
features. All transitive down-references are retained with `>>`. The exact node
polygon, exclusion rules and category priority are then applied locally.
This tests the existing five city-layer contract, not a new expanded municipal
network boundary. Changing the boundary/tags/configuration requires a new seed.

The source graph retains element type/ID, tags, coordinates and node/member
references. Contributor metadata is discarded. Versions are not an update gate.
Full-source and delta canonicalization use the same graph contract. Old action
records must match the cached baseline, references must resolve, and source
watermarks must cover the requested cutoff. Remarks, malformed XML, duplicates,
stale watermarks, missing references and unsupported actions reject the delta.

## Daily response probe and full-acquisition fallback

The [daily probe workflow](https://github.com/kauevestena/oswm_codebase/actions/runs/41343838674)
uses `66bd4556d2161c5164284a907080c5348cfa435e` and the fixed interval
**2026-10-31T00:00:00Z to 2026-11-01T00:00:00Z**. Cities run serially.

| City | Daily delta | Actions | Current full download | Historical replay |
|---|---:|---|---:|---|
| Curitiba | 26,026 B | 12 create, 143 modify, 9 delete | 5,582,735 B interpreter body | Blocked: historical bootstrap failed |
| Milan | No valid delta | Main and Private.coffee both timed out | 13,529,352 B interpreter body | Not attempted after delta failure |

Curitiba's daily response includes 42 same-version modifications, six objects
leaving the query while still visible and three actual OSM deletions. The daily
response was received and parsed; it is **not** a validated daily replay.

Curitiba's historical bootstrap returned HTTP 502 from the main endpoint and a
timeout from Private.coffee. Its current full acquisition succeeded. Including
the failed status response, the successful full-acquisition phase received
5,583,269 B. It produced all five layers, persisted/reloaded their summaries and
source graph, detected changes against the archived Oct29 source digests, and
skipped the rebuild when comparing the same newly acquired data again.
That Oct29-to-current comparison is not a fixed 24-hour parity result.

Milan's daily delta interpreter requests each hit the 80-second client read
timeout. Its current full download succeeded from the main endpoint in 55.298 s
including status probing/pause (43.662 s for the interpreter request). That phase
received 13,529,886 B including a 534 B status error body. All five layers were
produced, changed source digests requested a rebuild, and identical-data replay
skipped the rebuild. Curitiba's successful full phase took 43.755 s, including a
32.877 s interpreter request. These are individual public-server observations,
not controlled latency averages.

The complete reports are [Curitiba](pilots/curitiba_overpass_daily_probe_20261101.json)
and [Milan](pilots/milan_overpass_daily_probe_20261101.json). The source graphs are
workflow artifacts; they are deliberately not committed to git.

## Independent replay from a restored live cache

The [cached-replay workflow](https://github.com/kauevestena/oswm_codebase/actions/runs/41344713249)
uses `1cd47b22e324829987c2e17c41601dcbb3fab52e`. It restores the actual source
cache from the preceding workflow into a separate runner, verifies its checksum
and configuration identity, and gets an independent current full snapshot.
That snapshot's watermark fixes the end timestamp. It then applies an explicit
start/end augmented diff and compares **every canonical primitive** with the full
oracle. Equality of the complete graph is stronger than just equal layer counts.
Both states are processed through the same deterministic OSWM layer extraction.

| City | Actual replay interval (UTC) | Full graph parity | Live actions applied |
|---|---|---|---|
| Curitiba | 19:55:06 → 20:04:20 (554 s) | All 250,189 primitives identical | Zero; only the no-change path was exercised |
| Milan | Seed at 20:00:19; no newer control obtained | Blocked before delta application | None |

Curitiba's seed was restored in a different runner. The fresh full oracle and
the delta-updated graph have the same SHA-256. There were **no live source
changes during that interval**; this does not demonstrate successful replay of
the 164 actions observed in its separate daily probe. Forced timeout recovery
used the verified full oracle, preserved the baseline, and target-cutoff replay
made no new request.

Curitiba's fresh full interpreter response was 5,582,735 B. Its empty delta
interpreter response was 231 B, with 534 B of failed status response overhead
(765 B for the successful delta phase). The compressed seed payload is
5,049,875 B: estimated cache payload plus delta is 5,050,640 B, about **9.5% less
incoming data** than another full download before artifact packaging overhead.
The current sandbox then uploads another
5,049,875 B source-cache payload. That upload is an implementation cost, not a
fundamental requirement: immutable blob reuse could avoid reuploading an
unchanged payload if checkpoint/retention management were added. Full acquisition
can restore only the much smaller layer fingerprints instead of this graph.

These intervals are the elapsed time between real live snapshots, not overnight
replays. The full oracle is experiment overhead, not a request an operational
delta client would perform every time. Full graph SHA and action counts are in
the [Curitiba replay evidence](pilots/curitiba_overpass_cache_replay_20261101.json).

Milan restored its valid 556,379-object seed (11,752,470 B gzip), then failed
to obtain a fresh full oracle: the main interpreter returned HTTP 502 and
Private.coffee hit the 65-second read timeout. There was no valid later cutoff,
no short-interval delta request, and no new checkpoint. The cached-replay
workflow is **failed overall**, with Curitiba successful and Milan blocked.
This is an availability failure, not a measured mismatch between delta and full
data. Its complete [failed replay report](pilots/milan_overpass_cache_replay_20261101.json)
is retained alongside the successful daily full-acquisition result above.

## Local change detection and checkpoint behavior

The full-acquisition route fingerprints source IDs, normalized geometry and
retained OSWM tags separately for kerbs, sidewalks, crossings, other footways
and completeness roads. Any relevant layer/configuration change requests a
conservative rebuild; identical data skips it. This does not implement selective
downstream product regeneration. An operational full-download route only needs
the previous layer fingerprints (or existing raw layers); it does not need to
restore the entire primitive graph. The sandbox also retains a graph to test
incremental cache behavior and measure its transfer cost.

Cache preparation does not advance the checkpoint. A content-addressed gzip
payload is written before its pointer is atomically replaced. Replaying an
already committed query/cutoff performs no source request. Failed delta and full
requests preserve the last good cache. A forced delta timeout is tested against
an already fetched real full oracle without another public download; it is
reported as fault injection, not as a second live acquisition.

Fifteen client/transaction fixtures and seven existing meter/provenance checks
pass. One fixture exercises real OSMnx geometry construction: moving a node
changes the way geometry without modifying the way record. It also guards
against OSMnx mutating the canonical input records during feature extraction.
Fixtures validate the client protocol; live replay separately validates server
responses against full controls.

## Scope and operation

Public requests are bounded, city jobs are serial, and HTTP error responses are
retained in the evidence. A failing `/status` endpoint permits one interpreter
attempt after a short pause; interpreter HTTP errors are not recursively retried.
The current [public service guidance](https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances)
describes the main instance as overloaded. Availability observations here apply
to these sandbox attempts, not to every deployment of Overpass.

The sandbox full route can be run explicitly with:

```sh
python sandbox/change_query_probe.py --city curitiba --mode full --work /tmp/oswm-curitiba-full
```

All cutoffs, source/configuration identities, request outcomes, layer digests and
cache sizes are recorded in the per-city JSON evidence. Failed bytes are never
presented as a tiny successful dataset. Encoded response bodies exclude HTTP/TLS
framing; full test oracles are experiment overhead, and cache download/upload
costs are separate from the small delta response. No full regional PBF is used.

The pinned node config and polygon file contents were also compared with
observed current node mains (Curitiba `6f814cdce678d28a49a4722b424bbe2a9e1ed6b0`,
Milan `a2fa7e4d1f8aa354034a2382974316f4062b9327`) and match. Node mains can advance
through their existing pipelines independently; this experiment performs no
node write. The core main remained `44cafc7c0f582ee1732e515446ed11a418b13afa` at
the read-only check.

## Migration choice

Use the sandbox's explicit `--mode full` route as the basis for the next isolated
node integration. Acquire only the configured city features and dependencies,
derive all five layers, compare retained source fingerprints, and rebuild on a
relevant source/configuration change. Commit data and its successful cutoff only
after validation; keep the existing verified outputs when acquisition fails.
Keep the query-result delta route opt-in until a non-empty daily replay matches
independent full controls in both cities. With hosted runners, compare total
cache restoration/upload traffic before adopting it solely for bandwidth.

The daily probe workflow succeeded for both cities because both completed the
full fallback, not because both passed delta parity. The cached-replay workflow
has one pass and one availability failure. The archived JSON flags and errors,
rather than a workflow badge alone, determine which claims are supported.
