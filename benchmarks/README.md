# Routing benchmark

This compares the actual OSWM worker functions with pinned client-side JavaScript
libraries on one canonical graph. The recorded Milan run is in
[`../routing/benchmark_results.json`](../routing/benchmark_results.json), and its
tables appear in the public [format guide](../routing/oswmg_guide.html#benchmark).

## Reproduce a run

Use Node 22 or newer and install the development dependencies with `npm ci`.
Pass a node's matching binary graph and profile metadata:

```bash
npm run benchmark:routing -- \
  --graph ../milan/data/routing/network.oswmg \
  --profiles ../milan/data/routing/profiles.json \
  --dataset Milan \
  --output routing/benchmark_results.json
python -m routing.generate_oswmg_guide
```

The recorded run uses Milan's processed data and cached slope evidence from
commit `7bd414cce789d33fd060459b36d746c9e658f987`, regenerated in a sandbox with
routing policy 1.2.0. To reproduce that input, check out that node revision in a
separate directory, place this core revision in its `oswm_codebase` directory,
and run `python oswm_codebase/generation/routing_demo_gen.py` from the sandbox
node root. This uses the node's normal generation pipeline and existing slope
cache. Check the resulting SHA-256 against the recorded graph hash before
claiming reproduction of this exact dataset. Passing the live node's older
graph is a different policy/input and is recorded as such.

Defaults are seed 20261110, 30 vertex pairs, eight snapping positions per
profile, and three measured repetitions. Override them with `--seed`,
`--route-count`, `--snap-count`, and `--repeats`. Each engine runs in a fresh
process, with three route and two snapping warm-ups. The same seeded pairs
are sampled uniformly from the largest distance-profile connected component;
these are city-wide queries, not a representative survey of short pedestrian
trips. Accessibility profiles may disconnect some pairs.

## What is compared

| Operation | Implementations |
|---|---|
| Directional weighted network routing | OSWM A*, GeoJSON Path Finder 2.1.0, ngraph.path A* |
| Nearest usable segment within 100 m | OSWM grid index, Turf linear scan, Turf + RBush |
| Parse/setup | Binary typed-array initialization; GeoJSON parsing; each library's graph/index construction |
| Isochrones | OSWM-only diagnostic, three origins per profile with 5/10/15-minute cutoffs |

All routers receive the same Float32 costs, including blocked directions. The
alternative GeoJSON contains the same canonical segment topology and costs;
profiling and grading are already done for every contender. JSON conversion is
outside query timing. A* uses an admissible geographic heuristic for OSWM and
ngraph. GeoJSON Path Finder uses its native compaction and Dijkstra search.
No library is deliberately changed to an inefficient implementation.

Turf's `shortestPath` accepts polygon obstacles and constructs a grid; it does
not consume this weighted pedestrian graph. It therefore has no network-routing
score. Indexed Turf is included so the full-scan result is not presented as the
only way to use Turf. Nearest-point calculations use Turf's great-circle model
and OSWM's local planar model, with a 0.1 m result-distance tolerance.

Route search uses existing vertex endpoints, eliminating differences in
partial-edge attachment. Route cost tolerance is the greater of 0.05 equivalent
metres or 0.001% relative error. Alternative equal-cost paths are allowed.
OSWM's timed call also constructs route coordinates and physical distance;
ngraph's timed call returns node IDs. Result-cost validation is outside timing.

GeoJSON Path Finder 2.1.0 can discard a cheaper parallel corridor during
compaction. `tests/routing_benchmark.test.mjs` includes a minimal reproducer
returning cost 800 where a cost-300 route exists. Recorded cost disagreements
remain visible and disqualify claims about equally correct route solutions.
The independent ngraph comparison cross-checks the OSWM route costs.

## Interpretation and limits

These are Node/V8 CPU measurements of browser-capable code, not browser or
end-to-end UI latency. Module imports, input file reads, HTTP transfer,
worker messaging and rendering are excluded. Parse/setup columns are single
observations; query columns summarize repeated measurements. The binary's
complete initialization is included in its parse column.

Payload comparisons report raw bytes, gzip level 6 and Brotli quality 5.
Memory deltas follow explicit GC in isolated child processes and exclude the
common reference graph and module imports. They are approximate incremental
process measurements, not browser peak memory. Isochrone timings have no
warm-up and no cross-library equivalence claim.

Results record versions, CPU/runtime, queries, seed, checksums, profile rules,
cost agreement and both successful/unreachable outcomes. They describe this
dataset and machine; repeat the benchmark in target browsers/devices before
making broader performance guarantees. Large datasets are temporary inputs and
are not committed to the core repository.
