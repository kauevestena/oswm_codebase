/** Reproducible CPU benchmark for the actual OSWM worker and browser libraries.
 * Run with --expose-gc. Each engine runs in a fresh process; no network timing.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir, cpus, platform, arch, totalmem } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { gzipSync, brotliCompressSync, constants as zlibConstants } from 'node:zlib';
import { performance } from 'node:perf_hooks';
import { nearestPointOnLine } from '@turf/nearest-point-on-line';
import PathFinderModule from 'geojson-path-finder';
import createGraph from 'ngraph.graph';
import { aStar } from 'ngraph.path';
import RBush from 'rbush';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PathFinder = PathFinderModule.default ?? PathFinderModule;
const ENGINES = ['oswm', 'geojson-path-finder', 'ngraph.path', 'turf', 'turf-rbush'];
const LABELS = { oswm: 'OSWM .oswmg', 'geojson-path-finder': 'GeoJSON Path Finder',
    'ngraph.path': 'ngraph.path A*', turf: 'Turf linear scan', 'turf-rbush': 'Turf + RBush' };

export function loadWorker(buffer, profileOrder) {
    const source = readFileSync(join(ROOT, 'routing/routing_worker.js'), 'utf8');
    // Execute unchanged worker functions with normal V8 globals. Browser
    // messaging, transfer and rendering are intentionally outside this test.
    const factory = new Function('self', 'fetch', source + `\nreturn {
        initialize, parseGraph, snapToNetwork, routeForProfile, isochroneRequest
    };`);
    const worker = factory({ addEventListener() {}, postMessage() {} }, async () => ({
        ok: true, arrayBuffer: async () => buffer
    }));
    return { worker, initialize: () => worker.initialize({ graphUrl: 'local', profileOrder,
        profileHeuristicScales: profileOrder.map(() => 1) }) };
}

export function edgeId(graph, source, target) {
    let low = graph.adjacencyOffsets[source], high = graph.adjacencyOffsets[source + 1];
    while (low < high) {
        const middle = (low + high) >>> 1;
        if (graph.targets[middle] < target) low = middle + 1; else high = middle;
    }
    return graph.targets[low] === target && low < graph.adjacencyOffsets[source + 1] ? low : -1;
}

export function geojsonFromGraph(graph) {
    const coordinate = node => [graph.longitudes[node], graph.latitudes[node]];
    return { type: 'FeatureCollection', features: Array.from(graph.segmentA, (a, segment) => {
        const b = graph.segmentB[segment];
        const forward = edgeId(graph, a, b), backward = edgeId(graph, b, a);
        const cost = edge => Array.from({ length: graph.profileCount }, (_, p) => {
            const value = graph.weights[p * graph.directedEdgeCount + edge];
            return Number.isFinite(value) ? value : null;
        });
        return { type: 'Feature', properties: { a, b, forward: cost(forward), backward: cost(backward) },
            geometry: { type: 'LineString', coordinates: [coordinate(a), coordinate(b)] } };
    }) };
}

export function stats(values) {
    const sorted = values.slice().sort((a, b) => a - b);
    const percentile = q => sorted[Math.max(0, Math.ceil(sorted.length * q) - 1)] ?? null;
    return { n: values.length, median_ms: percentile(.5), p95_ms: percentile(.95),
        min_ms: sorted[0] ?? null, max_ms: sorted.at(-1) ?? null };
}

function distance(a, b) {
    const rad = Math.PI / 180, r = 6371008.8;
    const x = Math.sin((b[1] - a[1]) * rad / 2) ** 2
        + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin((b[0] - a[0]) * rad / 2) ** 2;
    return 2 * r * Math.asin(Math.min(1, Math.sqrt(x)));
}

function samples(graph, routeCount, snapCount, seed) {
    const parent = Uint32Array.from({ length: graph.nodeCount }, (_, i) => i);
    const find = node => { while (parent[node] !== node) { parent[node] = parent[parent[node]]; node = parent[node]; } return node; };
    for (let a = 0; a < graph.nodeCount; a++) {
        for (let e = graph.adjacencyOffsets[a]; e < graph.adjacencyOffsets[a + 1]; e++) {
            if (Number.isFinite(graph.weights[e])) parent[find(a)] = find(graph.targets[e]);
        }
    }
    const counts = new Map();
    for (let a = 0; a < graph.nodeCount; a++) counts.set(find(a), (counts.get(find(a)) || 0) + 1);
    const largest = [...counts].sort((a, b) => b[1] - a[1])[0][0];
    const nodes = Array.from(parent, (_, a) => a).filter(a => find(a) === largest);
    let state = seed >>> 0;
    const randomNode = () => { state = (Math.imul(1664525, state) + 1013904223) >>> 0; return nodes[state % nodes.length]; };
    const routes = Array.from({ length: routeCount }, () => {
        const a = randomNode(); let b = randomNode();
        while (a === b) b = randomNode();
        return [a, b];
    });
    const snaps = Array.from({ length: snapCount }, () => {
        const node = randomNode();
        return [graph.longitudes[node] + 8 / (111195 * Math.cos(graph.latitudes[node] * Math.PI / 180)),
            graph.latitudes[node] + 5 / 111195];
    });
    return { routes, snaps, largest_component_nodes: nodes.length };
}

export function createNgraph(collection, profileIndex) {
    const graph = createGraph();
    for (const feature of collection.features) {
        const { a, b, forward, backward } = feature.properties;
        graph.addNode(a, feature.geometry.coordinates[0]);
        graph.addNode(b, feature.geometry.coordinates[1]);
        graph.addLink(a, b, forward); graph.addLink(b, a, backward);
    }
    const router = p => aStar(graph, { oriented: true,
        blocked: (_from, _to, link) => link.data[p] === null,
        distance: (_from, _to, link) => link.data[p],
        heuristic: (from, to) => distance(from.data, to.data) * .999999 });
    return { graph, router: router(profileIndex), forProfile: router };
}

function pathWeight(ids, graph, profileIndex) {
    if (!ids.length) return null;
    let total = 0;
    for (let i = 1; i < ids.length; i++) {
        const e = edgeId(graph, ids[i - 1], ids[i]);
        if (e < 0) return Infinity;
        total += graph.weights[profileIndex * graph.directedEdgeCount + e];
    }
    return total;
}

export function turfSnap(collection, point, profileIndex, tree = null, outgoing = null) {
    const dx = 100.01 / (111195 * Math.cos(point[1] * Math.PI / 180));
    const dy = 100.01 / 111195;
    const candidates = tree ? tree.search({ minX: point[0] - dx, maxX: point[0] + dx,
        minY: point[1] - dy, maxY: point[1] + dy }).map(item => item.feature) : collection.features;
    let best = null;
    for (const feature of candidates) {
        const { forward, backward } = feature.properties;
        if (forward[profileIndex] === null && backward[profileIndex] === null) continue;
        const snapped = nearestPointOnLine(feature, point, { units: 'meters' });
        if (outgoing) {
            const [a, b] = feature.geometry.coordinates;
            if (distance(snapped.geometry.coordinates, a) < 1e-5 && !outgoing.has(feature.properties.a)) continue;
            if (distance(snapped.geometry.coordinates, b) < 1e-5 && !outgoing.has(feature.properties.b)) continue;
        }
        const metres = snapped.properties.pointDistance ?? snapped.properties.dist;
        if (metres <= 100 && (!best || metres < best.distanceM)) {
            best = { coordinates: snapped.geometry.coordinates, distanceM: metres };
        }
    }
    return best;
}

function makeTree(collection) {
    return new RBush().load(collection.features.map(feature => {
        const [a, b] = feature.geometry.coordinates;
        return { minX: Math.min(a[0], b[0]), maxX: Math.max(a[0], b[0]),
            minY: Math.min(a[1], b[1]), maxY: Math.max(a[1], b[1]), feature };
    }));
}

async function runEngine(options) {
    const setupStart = performance.now();
    const raw = readFileSync(options.graph);
    const buffer = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
    const metadata = JSON.parse(readFileSync(options.profiles, 'utf8'));
    const order = metadata.graph_profile_order;
    const workerApi = loadWorker(buffer, order);
    const graph = workerApi.worker.parseGraph(buffer);
    const queries = JSON.parse(readFileSync(options.queries, 'utf8'));
    // Reference arrays and validation data are loaded before measuring each
    // alternative representation, and excluded from its memory delta.
    global.gc?.();
    const memoryBefore = process.memoryUsage();
    const jsonInput = options.engine === 'oswm' ? null : readFileSync(options.geojson, 'utf8');
    const loadStart = performance.now();
    let collection;
    if (options.engine === 'oswm') await workerApi.initialize();
    else collection = JSON.parse(jsonInput);
    const parseMs = performance.now() - loadStart;
    const buildStart = performance.now();
    let tree, ngraph;
    if (options.engine === 'turf-rbush') tree = makeTree(collection);
    if (options.engine === 'ngraph.path') ngraph = createNgraph(collection, 0);
    const sharedBuildMs = performance.now() - buildStart;
    const firstSegment = new Int32Array(graph.nodeCount).fill(-1);
    for (let s = 0; s < graph.segmentCount; s++) {
        firstSegment[graph.segmentA[s]] = s; firstSegment[graph.segmentB[s]] = s;
    }
    const nodeSnap = node => ({ segmentId: firstSegment[node],
        t: graph.segmentA[firstSegment[node]] === node ? 0 : 1 });
    const rows = [];
    for (let p = 0; p < order.length; p++) {
        const profileStart = performance.now();
        let finder;
        const outgoing = new Set();
        if (['turf', 'turf-rbush'].includes(options.engine)) for (const feature of collection.features) {
            const props = feature.properties;
            if (props.forward[p] !== null) outgoing.add(props.a);
            if (props.backward[p] !== null) outgoing.add(props.b);
        }
        if (options.engine === 'geojson-path-finder') finder = new PathFinder(collection, {
            tolerance: graph.tolerance,
            weight: (_a, _b, props) => ({ forward: props.forward[p] ?? 0, backward: props.backward[p] ?? 0 })
        });
        if (ngraph) finder = ngraph.forProfile(p);
        const profileBuildMs = performance.now() - profileStart;
        const times = [], answers = [];
        const point = id => ({ type: 'Feature', properties: {}, geometry: { type: 'Point',
            coordinates: [graph.longitudes[id], graph.latitudes[id]] } });
        const route = ([a, b]) => {
            if (options.engine === 'oswm') return workerApi.worker.routeForProfile(nodeSnap(a), nodeSnap(b), order[p]);
            if (options.engine === 'geojson-path-finder') return finder.findPath(point(a), point(b));
            return finder.find(a, b);
        };
        if (['oswm', 'geojson-path-finder', 'ngraph.path'].includes(options.engine)) {
            for (const query of queries.routes.slice(0, 3)) route(query);
            for (let repeat = 0; repeat < options.repeats; repeat++) {
                for (const query of queries.routes) {
                    const start = performance.now(), result = route(query);
                    times.push(performance.now() - start);
                    // ngraph returns a destination-to-origin node list.
                    const weight = ngraph ? (result.length < 2 ? null : pathWeight(result.map(node => node.id).reverse(), graph, p))
                        : result?.weight ?? null;
                    answers.push(weight);
                }
            }
        }
        const snapTimes = [], snapAnswers = [];
        if (['oswm', 'turf', 'turf-rbush'].includes(options.engine)) {
            const snap = coordinate => {
                if (options.engine !== 'oswm') return turfSnap(collection, coordinate, p, tree, outgoing);
                try { return workerApi.worker.snapToNetwork(coordinate, { profileId: order[p] }); }
                catch { return null; }
            };
            for (const query of queries.snaps.slice(0, 2)) snap(query);
            for (let repeat = 0; repeat < options.repeats; repeat++) {
                for (const query of queries.snaps) {
                    const start = performance.now(), result = snap(query);
                    snapTimes.push(performance.now() - start);
                    snapAnswers.push(result);
                }
            }
        }
        const isoTimes = [], isoBandCounts = [];
        if (options.engine === 'oswm') {
            for (const [node] of queries.routes.slice(0, 3)) {
                const start = performance.now();
                const result = workerApi.worker.isochroneRequest({ origin: nodeSnap(node),
                    profileId: order[p], speedKmh: metadata.profiles[order[p]].speed_kmh,
                    cutoffsMinutes: [5, 10, 15] });
                isoTimes.push(performance.now() - start);
                isoBandCounts.push(result.features.length);
            }
        }
        rows.push({ profile_id: order[p], profile_setup_ms: profileBuildMs,
            routing: stats(times), snapping: stats(snapTimes), answers, snap_answers: snapAnswers,
            isochrone: stats(isoTimes), isochrone_band_counts: isoBandCounts });
    }
    global.gc?.();
    const memoryAfter = process.memoryUsage();
    return { engine: options.engine, label: LABELS[options.engine],
        input_parse_ms: parseMs, shared_setup_ms: sharedBuildMs,
        memory_delta_bytes: Object.fromEntries(['heapUsed', 'arrayBuffers', 'rss'].map(key => [key, memoryAfter[key] - memoryBefore[key]])),
        total_process_work_ms: performance.now() - setupStart, profiles: rows };
}

function argumentsFromCLI() {
    const options = {};
    for (let i = 2; i < process.argv.length; i += 2) options[process.argv[i].slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = process.argv[i + 1];
    for (const key of ['graph', 'profiles', 'output']) if (!options[key] && !options.engine) throw new Error(`Missing --${key}`);
    options.routeCount = Number(options.routeCount || 30);
    options.snapCount = Number(options.snapCount || 8);
    options.repeats = Number(options.repeats || 3);
    options.seed = Number(options.seed || 20261110);
    for (const key of ['routeCount', 'snapCount', 'repeats']) {
        if (!Number.isInteger(options[key]) || options[key] <= 0) throw new Error(`${key} must be a positive integer`);
    }
    return options;
}

async function main() {
    const options = argumentsFromCLI();
    if (options.engine) { process.stdout.write(JSON.stringify(await runEngine(options))); return; }
    const raw = readFileSync(options.graph);
    const buffer = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
    const metadata = JSON.parse(readFileSync(options.profiles, 'utf8'));
    const sha256 = createHash('sha256').update(raw).digest('hex');
    assert.equal(sha256, metadata.graph_sha256, 'graph checksum must match profile metadata');
    const { worker } = loadWorker(buffer, metadata.graph_profile_order);
    const graph = worker.parseGraph(buffer);
    const querySet = samples(graph, options.routeCount, options.snapCount, options.seed);
    const json = Buffer.from(JSON.stringify(geojsonFromGraph(graph)));
    const lock = JSON.parse(readFileSync(join(ROOT, 'package-lock.json'), 'utf8'));
    const directory = mkdtempSync(join(tmpdir(), 'oswm-benchmark-'));
    const engines = [];
    try {
        writeFileSync(join(directory, 'network.json'), json);
        writeFileSync(join(directory, 'queries.json'), JSON.stringify(querySet));
        for (const engine of ENGINES) {
            process.stderr.write(`Benchmarking ${LABELS[engine]}…\n`);
            const result = spawnSync(process.execPath, ['--expose-gc', fileURLToPath(import.meta.url),
                '--engine', engine, '--graph', resolve(options.graph), '--profiles', resolve(options.profiles),
                '--geojson', join(directory, 'network.json'), '--queries', join(directory, 'queries.json'),
                '--repeats', String(options.repeats)], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 });
            if (result.status !== 0) throw new Error(`${engine}: ${result.stderr || result.error}`);
            engines.push(JSON.parse(result.stdout));
        }
    } finally { rmSync(directory, { recursive: true, force: true }); }
    const reference = engines[0];
    for (const engine of engines.slice(1)) for (let p = 0; p < metadata.graph_profile_order.length; p++) {
        const baseline = reference.profiles[p], row = engine.profiles[p];
        row.routing_mismatches = row.answers.filter((answer, i) => {
            const expected = baseline.answers[i];
            return answer === null || expected === null ? answer !== expected
                : !Number.isFinite(answer) || Math.abs(answer - expected) > Math.max(.05, expected * 1e-5);
        }).length;
        row.snapping_mismatches = row.snap_answers.filter((answer, i) => {
            const expected = baseline.snap_answers[i];
            return !answer || !expected ? Boolean(answer) !== Boolean(expected)
                : Math.abs(answer.distanceM - expected.distanceM) > .1;
        }).length;
    }
    for (const engine of engines) for (const row of engine.profiles) {
        row.routing_successes = row.answers.filter(value => value !== null && Number.isFinite(value)).length;
        row.snapping_successes = row.snap_answers.filter(Boolean).length;
        row.routing_mismatches ??= 0;
        row.snapping_mismatches ??= 0;
        delete row.snap_answers;
        if (engine.engine !== 'oswm') delete row.answers;
    }
    const report = { schema_version: 1, generated_at: new Date().toISOString(),
        dataset: options.dataset || 'OSWM network', graph_sha256: sha256,
        dataset_source: options.datasetSource || null,
        worker_sha256: createHash('sha256').update(readFileSync(join(ROOT, 'routing/routing_worker.js'))).digest('hex'),
        benchmark_script_sha256: createHash('sha256').update(readFileSync(fileURLToPath(import.meta.url))).digest('hex'),
        ruleset_version: metadata.ruleset_version, ruleset_hash: metadata.ruleset_hash,
        environment: { runtime: process.version, v8: process.versions.v8, platform: platform(), arch: arch(),
            cpu: cpus()[0]?.model, logical_cpus: cpus().length, ram_bytes: totalmem() },
        versions: Object.fromEntries(['@turf/nearest-point-on-line', 'geojson-path-finder', 'ngraph.path', 'ngraph.graph', 'rbush']
            .map(name => [name, lock.packages[`node_modules/${name}`].version])),
        counts: { nodes: graph.nodeCount, directed_edges: graph.directedEdgeCount, segments: graph.segmentCount,
            profiles: graph.profileCount, largest_component_nodes: querySet.largest_component_nodes },
        methodology: { seed: options.seed, route_pairs: options.routeCount, snap_points: options.snapCount,
            repeats: options.repeats, route_warmups: 3, snap_warmups: 2,
            route_endpoints: 'Existing vertices in largest distance-profile component; shared across all profiles and engines',
            snapping: 'Same 100 m access radius; 8 m east and 5 m north of seeded vertices; outbound eligibility',
            costs: 'Identical precomputed Float32 directional costs for all routers; null is blocked in the derived GeoJSON',
            scope: 'Node/V8 CPU benchmark of client-side libraries; excludes browser rendering, messaging, network latency and library download',
            correctness: 'Route cost tolerance max(0.05 equivalent m, 1e-5 relative); snap distance tolerance 0.1 m; alternative shortest paths allowed',
            isochrones: 'OSWM-only diagnostic: first three route origins, cutoffs 5/10/15 minutes; no warm-up, messaging or rendering; no cross-framework equivalence claim',
            startup: 'Single CPU observation in each fresh process; input file reads excluded; OSWM parse includes worker initialization',
            known_comparator_limit: 'GeoJSON Path Finder 2.1.0 can discard a cheaper parallel corridor during compaction; a pinned-version regression fixture reproduces 800 versus 300 equivalent metres. Cost mismatches disqualify equivalently-correct speed claims.',
            memory: 'Fresh child per engine; GC before/after; deltas are approximate and exclude shared reference graph and runtime/module imports' },
        payload_bytes: { oswmg: raw.length, geojson: json.length,
            oswmg_gzip: gzipSync(raw, {level: 6}).length, geojson_gzip: gzipSync(json, {level: 6}).length,
            oswmg_brotli: brotliCompressSync(raw, {params: {[zlibConstants.BROTLI_PARAM_QUALITY]: 5}}).length,
            geojson_brotli: brotliCompressSync(json, {params: {[zlibConstants.BROTLI_PARAM_QUALITY]: 5}}).length },
        queries: querySet, engines };
    writeFileSync(options.output, JSON.stringify(report, null, 2) + '\n');
    process.stderr.write(`Wrote ${options.output}\n`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
