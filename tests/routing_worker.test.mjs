import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';


const workerSource = readFileSync(
    new URL('../routing/routing_worker.js', import.meta.url),
    'utf8'
);

test('configurable cutoff controls validate and generate bands', () => {
    const html = readFileSync(new URL('../routing/routing_demo.html', import.meta.url), 'utf8');
    const source = html.slice(html.indexOf('function readIsochroneCutoffs()'),
        html.indexOf('const routingRoot ='));
    const values = { isochroneStart: '5', isochroneStep: '5', isochroneCount: '2' };
    const context = { document: { getElementById: id => ({ value: values[id] }) } };
    vm.runInNewContext(source, context);
    const read = () => Array.from(context.readIsochroneCutoffs());
    assert.deepEqual(read(), [5, 10, 15]);
    for (const id of Object.keys(values)) {
        const previous = values[id];
        for (const empty of ['', '   ']) {
            values[id] = empty;
            assert.throws(read, /Use whole minutes/, `${id} must reject blank input`);
        }
        values[id] = previous;
    }
    values.isochroneStart = '10'; values.isochroneStep = '3'; values.isochroneCount = '4';
    assert.deepEqual(read(), [10, 13, 16, 19, 22]);
    assert.equal(context.isochroneBands(read()).length, 5);
    values.isochroneCount = '0';
    assert.deepEqual(read(), [10]);
    values.isochroneStart = '120';
    assert.deepEqual(read(), [120]);
    values.isochroneCount = '1';
    assert.throws(read, /120 minutes/);
    values.isochroneStart = '5'; values.isochroneCount = '12';
    assert.throws(read, /0–11/);
    values.isochroneCount = '2';
    for (const invalid of ['', '0', '-1', '1.5', 'Infinity']) {
        values.isochroneStep = invalid;
        assert.throws(read);
    }
});


function fixtureGraph(accessibleWeights = [111.2, 111.2, Infinity, 111.2]) {
    const nodeCount = 3;
    const edgeCount = 4;
    const profileCount = 2;
    const segmentCount = 2;
    const sections = [
        new Float64Array([0, 0.001, 0.002]),
        new Float64Array([0, 0, 0]),
        new Uint32Array([0, 1, 3, 4]),
        new Uint32Array([1, 0, 2, 1]),
        new Float32Array([
            111.2, 111.2, 111.2, 111.2,
            ...accessibleWeights
        ]),
        new Uint32Array([0, 1]),
        new Uint32Array([1, 2]),
        new Uint32Array([0, 2]),
        new Uint32Array([0, 1])
    ];
    const headerBytes = 192;
    const totalBytes = sections.reduce(
        (total, section) => total + section.byteLength,
        headerBytes
    );
    const buffer = new ArrayBuffer(totalBytes);
    const bytes = new Uint8Array(buffer);
    bytes.set(new TextEncoder().encode('OSWMGB02'));
    const view = new DataView(buffer);
    view.setUint32(8, 2, true);
    view.setUint32(12, headerBytes, true);
    view.setUint32(16, nodeCount, true);
    view.setUint32(20, edgeCount, true);
    view.setUint32(24, profileCount, true);
    view.setUint32(28, segmentCount, true);
    view.setUint32(32, 1, true);
    view.setUint32(36, 1, true);
    view.setUint32(40, 2, true);
    const headerOffsets = [48, 56, 64, 72, 80, 88, 96, 104, 112];
    let offset = headerBytes;
    for (let index = 0; index < sections.length; index += 1) {
        view.setBigUint64(headerOffsets[index], BigInt(offset), true);
        bytes.set(
            new Uint8Array(
                sections[index].buffer,
                sections[index].byteOffset,
                sections[index].byteLength
            ),
            offset
        );
        offset += sections[index].byteLength;
    }
    [0, 0, 0.002, 0, 0.00001].forEach((value, index) => {
        view.setFloat64(136 + index * 8, value, true);
    });
    return buffer;
}


function createWorkerHarness(buffer) {
    let messageListener = null;
    const replies = [];
    const workerScope = {
        addEventListener(type, listener) {
            if (type === 'message') messageListener = listener;
        },
        postMessage(message) {
            replies.push(message);
        }
    };
    vm.runInNewContext(workerSource, {
        self: workerScope,
        fetch: async () => ({
            ok: true,
            arrayBuffer: async () => buffer.slice(0)
        }),
        TextDecoder,
        console
    }, { filename: 'routing_worker.js' });

    let requestId = 0;
    return async function request(type, payload = {}) {
        assert.ok(messageListener, 'worker registered its message listener');
        const id = ++requestId;
        await messageListener({ data: { id, type, ...payload } });
        const reply = replies.shift();
        assert.equal(reply.id, id);
        if (!reply.ok) throw new Error(reply.error);
        return reply.result;
    };
}


function geometryRings(geometry) {
    const polygons = geometry.type === 'Polygon'
        ? [geometry.coordinates]
        : geometry.coordinates;
    return polygons.flat();
}


function signedRingArea(ring) {
    let area = 0;
    for (let index = 0; index < ring.length - 1; index += 1) {
        area += ring[index][0] * ring[index + 1][1]
            - ring[index + 1][0] * ring[index][1];
    }
    return area / 2;
}


function geometryArea(geometry) {
    const polygons = geometry.type === 'Polygon'
        ? [geometry.coordinates]
        : geometry.coordinates;
    return polygons.reduce((total, polygon) => (
        total + signedRingArea(polygon[0])
        + polygon.slice(1).reduce((holes, ring) => holes + signedRingArea(ring), 0)
    ), 0);
}


test('worker snaps through the grid and routes over typed arrays', async () => {
    const request = createWorkerHarness(fixtureGraph());
    const graph = await request('init', {
        graphUrl: 'fixture.oswmg',
        profileOrder: ['distance', 'accessible'],
        profileHeuristicScales: [1, 1]
    });
    assert.equal(graph.nodeCount, 3);
    assert.equal(graph.segmentCount, 2);

    const start = await request('snap', { coordinates: [0.0002, 0.0001] });
    const end = await request('snap', { coordinates: [0.0018, -0.0001] });
    assert.equal(start.segmentId, 0);
    assert.equal(end.segmentId, 1);
    assert.ok(Math.abs(start.coordinates[0] - 0.0002) < 1e-9);
    assert.ok(Math.abs(end.coordinates[0] - 0.0018) < 1e-9);

    const result = await request('route', {
        start,
        end,
        profileId: 'distance',
        comparisonProfileId: null
    });
    assert.ok(result.primary);
    assert.equal(result.primary.path.length, 3);
    assert.ok(result.primary.distanceM > 177 && result.primary.distanceM < 179);
});


test('worker preserves directional barriers and computes a fallback baseline', async () => {
    const request = createWorkerHarness(fixtureGraph());
    await request('init', {
        graphUrl: 'fixture.oswmg',
        profileOrder: ['distance', 'accessible'],
        profileHeuristicScales: [1, 1]
    });
    const start = await request('snap', { coordinates: [0.0002, 0] });
    const end = await request('snap', { coordinates: [0.0018, 0] });
    const result = await request('route', {
        start,
        end,
        profileId: 'accessible',
        comparisonProfileId: null,
        fallbackProfileId: 'distance'
    });
    assert.equal(result.primary, null);
    assert.ok(result.comparison);
});

test('profile-aware snapping skips blocked segments and bounds the access distance', async () => {
    const request = createWorkerHarness(fixtureGraph([111.2, 111.2, Infinity, Infinity]));
    await request('init', {
        graphUrl: 'fixture.oswmg', profileOrder: ['distance', 'accessible']
    });
    const click = [0.0018, 0];
    const baseline = await request('snap', { coordinates: click, profileId: 'distance' });
    const accessible = await request('snap', { coordinates: click, profileId: 'accessible' });
    assert.equal(baseline.segmentId, 1);
    assert.equal(accessible.segmentId, 0);
    assert.ok(accessible.distanceM > 88 && accessible.distanceM < 90);
    assert.deepEqual(Array.from(accessible.inputCoordinates), click);
    await assert.rejects(request('snap', {
        coordinates: click, profileId: 'accessible', maxDistanceM: 50
    }), /within 50 m/);
    await assert.rejects(request('snap', {
        coordinates: click, profileId: 'nonexistent'
    }), /Unknown routing profile/);
});

test('snapping reports an unavailable profile instead of returning an unusable origin', async () => {
    const request = createWorkerHarness(fixtureGraph([Infinity, Infinity, Infinity, Infinity]));
    await request('init', {
        graphUrl: 'fixture.oswmg', profileOrder: ['distance', 'accessible']
    });
    await assert.rejects(request('snap', {
        coordinates: [0.0002, 0], profileId: 'accessible'
    }), /No usable network segment/);
});


test('worker builds nested accessibility-adjusted isochrone polygons', async () => {
    const request = createWorkerHarness(fixtureGraph());
    await request('init', {
        graphUrl: 'fixture.oswmg',
        profileOrder: ['distance', 'accessible'],
        profileHeuristicScales: [1, 1]
    });
    const origin = await request('snap', { coordinates: [0.0002, 0] });
    const result = await request('isochrone', {
        origin,
        profileId: 'distance',
        speedKmh: 5,
        cutoffsMinutes: [1, 2, 3]
    });

    assert.equal(result.type, 'FeatureCollection');
    assert.deepEqual(
        Array.from(result.features, feature => feature.properties.minutes),
        [1, 2, 3]
    );
    assert.equal(result.metadata.time_semantics, 'accessibility_adjusted');
    assert.equal(result.metadata.direction, 'outbound');
    assert.equal(result.metadata.polygonization.method, 'rasterized_reachable_network_buffer');
    const areas = [];
    for (const feature of result.features) {
        assert.ok(['Polygon', 'MultiPolygon'].includes(feature.geometry.type));
        assert.equal(feature.properties.approximate, true);
        for (const ring of geometryRings(feature.geometry)) {
            assert.ok(ring.length >= 4);
            assert.deepEqual(Array.from(ring[0]), Array.from(ring[ring.length - 1]));
            assert.equal(
                new Set(ring.slice(0, -1).map(coordinates => coordinates.join(','))).size,
                ring.length - 1,
                'polygon rings do not repeat a vertex'
            );
            for (const coordinates of ring) {
                assert.ok(Array.from(coordinates).every(Number.isFinite));
            }
        }
        areas.push(geometryArea(feature.geometry));
    }
    assert.ok(areas.every((area, index) => index === 0 || area >= areas[index - 1]));
});


test('isochrone search honors directional profile barriers', async () => {
    const request = createWorkerHarness(fixtureGraph());
    await request('init', {
        graphUrl: 'fixture.oswmg',
        profileOrder: ['distance', 'accessible'],
        profileHeuristicScales: [1, 1]
    });
    const origin = await request('snap', { coordinates: [0.0002, 0] });
    const distance = await request('isochrone', {
        origin,
        profileId: 'distance',
        speedKmh: 5,
        cutoffsMinutes: [3]
    });
    const accessible = await request('isochrone', {
        origin,
        profileId: 'accessible',
        speedKmh: 5,
        cutoffsMinutes: [3]
    });

    assert.ok(distance.features.length);
    assert.ok(accessible.features.length);
    assert.ok(distance.metadata.visited_nodes > accessible.metadata.visited_nodes);
});


test('higher accessibility resistance consumes more of the time budget', async () => {
    const request = createWorkerHarness(fixtureGraph([556, 556, 556, 556]));
    await request('init', {
        graphUrl: 'fixture.oswmg',
        profileOrder: ['distance', 'accessible'],
        profileHeuristicScales: [1, 0]
    });
    const origin = await request('snap', { coordinates: [0.0002, 0] });
    const distance = await request('isochrone', {
        origin,
        profileId: 'distance',
        speedKmh: 5,
        cutoffsMinutes: [3]
    });
    const accessible = await request('isochrone', {
        origin,
        profileId: 'accessible',
        speedKmh: 5,
        cutoffsMinutes: [3]
    });

    assert.ok(
        geometryArea(distance.features[0].geometry)
        > geometryArea(accessible.features[0].geometry)
    );
    assert.ok(distance.metadata.visited_nodes > accessible.metadata.visited_nodes);
});


test('polygon tracing separates corner-touching rings', () => {
    const context = {
        self: { addEventListener() {}, postMessage() {} },
        TextDecoder,
        console
    };
    vm.runInNewContext(workerSource, context, { filename: 'routing_worker.js' });
    const selfTouchingRing = [
        [0, 0], [4, 0], [4, 4], [2, 4],
        [2, 3], [1, 3], [1, 4], [2, 4],
        [0, 4], [0, 0]
    ];
    const rings = context.splitRingAtRepeatedVertices(selfTouchingRing);

    assert.equal(rings.length, 2);
    assert.deepEqual(
        Array.from(rings, ring => signedRingArea(ring)).sort((left, right) => left - right),
        [-1, 16]
    );
    for (const ring of rings) {
        assert.equal(
            new Set(Array.from(ring).slice(0, -1).map(point => point.join(','))).size,
            ring.length - 1
        );
    }
});

function profileSwitchHarness(workerRequest) {
    const html = readFileSync(new URL('../routing/routing_demo.html', import.meta.url), 'utf8');
    const source = html.slice(html.indexOf('function showSnapNotice()'),
        html.indexOf("compareDistance.addEventListener('change'"));
    const elements = new Map();
    let routeCalls = 0;
    let isochroneCalls = 0;
    const context = vm.createContext({
        startClick: [0.0002, 0], endClick: [0.0018, 0],
        start: { coordinates: [0.0002, 0] }, end: { coordinates: [0.0018, 0] },
        markers: [], snapGeneration: 0, routeGeneration: 0, isochroneGeneration: 0,
        profileSelect: { value: 'wheelchair', addEventListener() {} },
        interactionMode: 'route', comparisonInfo: {}, routingStatus: {},
        isochroneData: {}, downloadIsochroneButton: {},
        workerRequest, updateProfileControls() {}, removeDisplayedPaths() {},
        removeIsochroneLayers() {}, hideRouteInfo() {}, showIsochroneMessage() {},
        addMarker() {}, updateReadyStatus() {}, selectedProfileLabel: () => 'Wheelchair',
        calculateRoute() { routeCalls += 1; },
        calculateIsochrone() { isochroneCalls += 1; },
        showNoRoute(message) { elements.set('error', { textContent: message }); },
        document: { getElementById(id) {
            if (!elements.has(id)) elements.set(id, {});
            return elements.get(id);
        } }
    });
    vm.runInContext(source, context);
    return { context, elements, routeCalls: () => routeCalls, isochroneCalls: () => isochroneCalls };
}

test('changing profiles resnaps original clicks with origin and destination roles', async () => {
    const requests = [];
    const harness = profileSwitchHarness(async (type, payload) => {
        requests.push({ type, ...payload });
        return { coordinates: [payload.coordinates[0], 0.0001], distanceM: 11 };
    });
    await harness.context.refreshProfileEndpoints();
    assert.equal(requests.length, 2);
    assert.equal(requests[0].profileId, 'wheelchair');
    assert.equal(requests[0].role, 'origin');
    assert.equal(requests[1].role, 'destination');
    assert.deepEqual(requests.map(request => Array.from(request.coordinates)), [[0.0002, 0], [0.0018, 0]]);
    assert.equal(harness.context.start.coordinates[1], 0.0001);
    assert.equal(harness.routeCalls(), 1);
    assert.match(harness.elements.get('snapNotice').textContent, /11 \/ 11 m/);
    harness.context.interactionMode = 'isochrone';
    harness.context.endClick = null;
    await harness.context.refreshProfileEndpoints();
    assert.equal(harness.isochroneCalls(), 1);
});

test('stale profile snaps cannot replace the latest result', async () => {
    const waiting = [];
    const harness = profileSwitchHarness((type, payload) => new Promise(resolve => {
        waiting.push(() => resolve({ coordinates: payload.coordinates, distanceM: 0 }));
    }));
    const earlier = harness.context.refreshProfileEndpoints();
    const latest = harness.context.refreshProfileEndpoints();
    waiting[2](); waiting[3]();
    await latest;
    assert.equal(harness.routeCalls(), 1);
    waiting[0](); waiting[1]();
    await earlier;
    assert.equal(harness.routeCalls(), 1);
});

test('failed profile snapping clears old endpoints and reports a useful reason', async () => {
    const harness = profileSwitchHarness(async () => { throw new Error('No usable network segment within 100 m'); });
    await harness.context.refreshProfileEndpoints();
    assert.equal(harness.context.start, null);
    assert.equal(harness.context.end, null);
    assert.equal(harness.routeCalls(), 0);
    assert.equal(harness.context.downloadIsochroneButton.disabled, true);
    assert.match(harness.elements.get('error').textContent, /within 100 m/);
    assert.deepEqual(Array.from(harness.context.startClick), [0.0002, 0]);
});
