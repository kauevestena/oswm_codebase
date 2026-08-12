import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';


const workerSource = readFileSync(
    new URL('../routing/routing_worker.js', import.meta.url),
    'utf8'
);


function fixtureGraph() {
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
            111.2, 111.2, Infinity, 111.2
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
