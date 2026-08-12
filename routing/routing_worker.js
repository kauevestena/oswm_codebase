const MAGIC = 'OSWMGB02';
const SCHEMA_VERSION = 2;
const HEADER_BYTES = 192;
const UINT32_MAX = 0xffffffff;
const EARTH_RADIUS_M = 6371008.8;
const DEG_TO_RAD = Math.PI / 180;

let graph = null;
let profileIndexes = new Map();
let heuristicScales = [];
let snapMarks = null;
let snapEpoch = 0;

self.addEventListener('message', async event => {
    const { id, type, ...payload } = event.data || {};
    try {
        let result;
        if (type === 'init') result = await initialize(payload);
        else if (type === 'snap') result = snapToNetwork(payload.coordinates);
        else if (type === 'route') result = routeRequest(payload);
        else throw new Error(`Unknown routing worker request: ${type}`);
        self.postMessage({ id, ok: true, result });
    } catch (error) {
        self.postMessage({
            id,
            ok: false,
            error: error instanceof Error ? error.message : String(error)
        });
    }
});

async function initialize({ graphUrl, profileOrder, profileHeuristicScales }) {
    const response = await fetch(graphUrl);
    if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText} loading routing graph`);
    }
    graph = parseGraph(await response.arrayBuffer());
    if (!Array.isArray(profileOrder) || profileOrder.length !== graph.profileCount) {
        throw new Error('Routing profiles do not match the binary graph.');
    }
    profileIndexes = new Map(profileOrder.map((profileId, index) => [profileId, index]));
    heuristicScales = profileOrder.map((_, index) => {
        const value = Number(profileHeuristicScales?.[index]);
        // Float32 edge weights can round a few ulps below their source value.
        // Keep the heuristic strictly conservative across those conversions.
        return Number.isFinite(value) && value >= 0
            ? Math.min(1, value) * 0.999999
            : 0;
    });
    snapMarks = new Uint32Array(graph.segmentCount);
    return {
        bounds: graph.bounds,
        nodeCount: graph.nodeCount,
        directedEdgeCount: graph.directedEdgeCount,
        segmentCount: graph.segmentCount,
        profileCount: graph.profileCount
    };
}

function parseGraph(buffer) {
    if (buffer.byteLength < HEADER_BYTES) {
        throw new Error('Routing graph is shorter than its header.');
    }
    const bytes = new Uint8Array(buffer, 0, 8);
    const magic = new TextDecoder().decode(bytes);
    const view = new DataView(buffer);
    if (magic !== MAGIC || view.getUint32(8, true) !== SCHEMA_VERSION) {
        throw new Error('Unsupported routing graph schema.');
    }
    if (view.getUint32(12, true) !== HEADER_BYTES) {
        throw new Error('Routing graph header size is invalid.');
    }

    const nodeCount = view.getUint32(16, true);
    const directedEdgeCount = view.getUint32(20, true);
    const profileCount = view.getUint32(24, true);
    const segmentCount = view.getUint32(28, true);
    const gridCols = view.getUint32(32, true);
    const gridRows = view.getUint32(36, true);
    const cellMembershipCount = view.getUint32(40, true);
    const offset = byteOffset => {
        const result = Number(view.getBigUint64(byteOffset, true));
        if (!Number.isSafeInteger(result) || result < HEADER_BYTES || result > buffer.byteLength) {
            throw new Error('Routing graph contains an invalid array offset.');
        }
        return result;
    };
    const offsets = [48, 56, 64, 72, 80, 88, 96, 104, 112].map(offset);
    const finalBytes = offsets[8] + cellMembershipCount * Uint32Array.BYTES_PER_ELEMENT;
    if (finalBytes > buffer.byteLength || offsets.some((value, index) => index && value < offsets[index - 1])) {
        throw new Error('Routing graph arrays are truncated or out of order.');
    }

    return {
        nodeCount,
        directedEdgeCount,
        profileCount,
        segmentCount,
        gridCols,
        gridRows,
        bounds: [
            view.getFloat64(136, true),
            view.getFloat64(144, true),
            view.getFloat64(152, true),
            view.getFloat64(160, true)
        ],
        tolerance: view.getFloat64(168, true),
        longitudes: new Float64Array(buffer, offsets[0], nodeCount),
        latitudes: new Float64Array(buffer, offsets[1], nodeCount),
        adjacencyOffsets: new Uint32Array(buffer, offsets[2], nodeCount + 1),
        targets: new Uint32Array(buffer, offsets[3], directedEdgeCount),
        weights: new Float32Array(buffer, offsets[4], profileCount * directedEdgeCount),
        segmentA: new Uint32Array(buffer, offsets[5], segmentCount),
        segmentB: new Uint32Array(buffer, offsets[6], segmentCount),
        cellOffsets: new Uint32Array(buffer, offsets[7], gridCols * gridRows + 1),
        cellSegments: new Uint32Array(buffer, offsets[8], cellMembershipCount)
    };
}

function requireGraph() {
    if (!graph) throw new Error('Routing graph has not finished loading.');
}

function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
}

function gridCoordinate(value, minimum, maximum, cells) {
    if (cells <= 1 || maximum <= minimum) return 0;
    return clamp(Math.floor((value - minimum) / (maximum - minimum) * cells), 0, cells - 1);
}

function projectedDistanceM(lon1, lat1, lon2, lat2, referenceLat) {
    const x = (lon2 - lon1) * DEG_TO_RAD * EARTH_RADIUS_M * Math.cos(referenceLat * DEG_TO_RAD);
    const y = (lat2 - lat1) * DEG_TO_RAD * EARTH_RADIUS_M;
    return Math.hypot(x, y);
}

function inspectSegment(segmentId, lon, lat, best) {
    if (snapMarks[segmentId] === snapEpoch) return best;
    snapMarks[segmentId] = snapEpoch;
    const a = graph.segmentA[segmentId];
    const b = graph.segmentB[segmentId];
    const scaleX = DEG_TO_RAD * EARTH_RADIUS_M * Math.cos(lat * DEG_TO_RAD);
    const scaleY = DEG_TO_RAD * EARTH_RADIUS_M;
    const ax = (graph.longitudes[a] - lon) * scaleX;
    const ay = (graph.latitudes[a] - lat) * scaleY;
    const bx = (graph.longitudes[b] - lon) * scaleX;
    const by = (graph.latitudes[b] - lat) * scaleY;
    const dx = bx - ax;
    const dy = by - ay;
    const denominator = dx * dx + dy * dy;
    const t = denominator > 0 ? clamp(-(ax * dx + ay * dy) / denominator, 0, 1) : 0;
    const distanceM = Math.hypot(ax + t * dx, ay + t * dy);
    if (distanceM >= best.distanceM) return best;
    return {
        segmentId,
        t,
        a,
        b,
        distanceM,
        coordinates: [
            graph.longitudes[a] + t * (graph.longitudes[b] - graph.longitudes[a]),
            graph.latitudes[a] + t * (graph.latitudes[b] - graph.latitudes[a])
        ]
    };
}

function snapToNetwork(coordinates) {
    requireGraph();
    const lon = Number(coordinates?.[0]);
    const lat = Number(coordinates?.[1]);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
        throw new Error('Snap coordinates must be finite longitude and latitude values.');
    }

    snapEpoch = (snapEpoch + 1) >>> 0;
    if (snapEpoch === 0) {
        snapMarks.fill(0);
        snapEpoch = 1;
    }
    const [minLon, minLat, maxLon, maxLat] = graph.bounds;
    const centerCol = gridCoordinate(lon, minLon, maxLon, graph.gridCols);
    const centerRow = gridCoordinate(lat, minLat, maxLat, graph.gridRows);
    const maximumRadius = Math.max(graph.gridCols, graph.gridRows);
    let best = { distanceM: Infinity };

    for (let radius = 0; radius < maximumRadius; radius += 1) {
        const firstCol = Math.max(0, centerCol - radius);
        const lastCol = Math.min(graph.gridCols - 1, centerCol + radius);
        const firstRow = Math.max(0, centerRow - radius);
        const lastRow = Math.min(graph.gridRows - 1, centerRow + radius);
        for (let row = firstRow; row <= lastRow; row += 1) {
            for (let col = firstCol; col <= lastCol; col += 1) {
                if (
                    radius > 0
                    && row !== firstRow
                    && row !== lastRow
                    && col !== firstCol
                    && col !== lastCol
                ) continue;
                const cellId = row * graph.gridCols + col;
                for (
                    let index = graph.cellOffsets[cellId];
                    index < graph.cellOffsets[cellId + 1];
                    index += 1
                ) {
                    best = inspectSegment(graph.cellSegments[index], lon, lat, best);
                }
            }
        }

        const west = minLon + firstCol / graph.gridCols * (maxLon - minLon);
        const east = minLon + (lastCol + 1) / graph.gridCols * (maxLon - minLon);
        const south = minLat + firstRow / graph.gridRows * (maxLat - minLat);
        const north = minLat + (lastRow + 1) / graph.gridRows * (maxLat - minLat);
        const containsTarget = lon >= west && lon <= east && lat >= south && lat <= north;
        const outsideDistances = [];
        if (firstCol > 0) outsideDistances.push(projectedDistanceM(lon, lat, west, lat, lat));
        if (lastCol < graph.gridCols - 1) outsideDistances.push(projectedDistanceM(lon, lat, east, lat, lat));
        if (firstRow > 0) outsideDistances.push(projectedDistanceM(lon, lat, lon, south, lat));
        if (lastRow < graph.gridRows - 1) outsideDistances.push(projectedDistanceM(lon, lat, lon, north, lat));
        if (
            containsTarget
            && Number.isFinite(best.distanceM)
            && (outsideDistances.length === 0 || best.distanceM <= Math.min(...outsideDistances))
        ) break;
    }
    if (!Number.isFinite(best.distanceM)) throw new Error('Routing graph has no snappable segments.');
    return best;
}

function edgeWeight(profileIndex, edgeId) {
    if (edgeId === UINT32_MAX) return Infinity;
    return graph.weights[profileIndex * graph.directedEdgeCount + edgeId];
}

function directedEdge(source, target) {
    let low = graph.adjacencyOffsets[source];
    let high = graph.adjacencyOffsets[source + 1];
    while (low < high) {
        const middle = (low + high) >> 1;
        const candidate = graph.targets[middle];
        if (candidate < target) low = middle + 1;
        else high = middle;
    }
    return low < graph.adjacencyOffsets[source + 1] && graph.targets[low] === target
        ? low
        : UINT32_MAX;
}

function partialWeight(weight, fraction) {
    if (fraction <= 1e-12) return 0;
    return Number.isFinite(weight) ? weight * fraction : Infinity;
}

function distanceMeters(lon1, lat1, lon2, lat2) {
    const phi1 = lat1 * DEG_TO_RAD;
    const phi2 = lat2 * DEG_TO_RAD;
    const deltaLat = (lat2 - lat1) * DEG_TO_RAD;
    const deltaLon = (lon2 - lon1) * DEG_TO_RAD;
    const value = Math.sin(deltaLat / 2) ** 2
        + Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLon / 2) ** 2;
    return 2 * EARTH_RADIUS_M * Math.atan2(
        Math.sqrt(value),
        Math.sqrt(Math.max(0, 1 - value))
    );
}

function pathDistanceM(path) {
    let result = 0;
    for (let index = 1; index < path.length; index += 1) {
        result += distanceMeters(
            path[index - 1][0],
            path[index - 1][1],
            path[index][0],
            path[index][1]
        );
    }
    return result;
}

class MinHeap {
    constructor() {
        this.nodes = [];
        this.priorities = [];
        this.lastPriority = Infinity;
    }

    get size() {
        return this.nodes.length;
    }

    push(priority, node) {
        let index = this.nodes.length;
        this.nodes.push(node);
        this.priorities.push(priority);
        while (index > 0) {
            const parent = (index - 1) >> 1;
            if (this.priorities[parent] <= priority) break;
            this.nodes[index] = this.nodes[parent];
            this.priorities[index] = this.priorities[parent];
            index = parent;
        }
        this.nodes[index] = node;
        this.priorities[index] = priority;
    }

    pop() {
        const result = this.nodes[0];
        this.lastPriority = this.priorities[0];
        const tailNode = this.nodes.pop();
        const tailPriority = this.priorities.pop();
        if (this.nodes.length) {
            let index = 0;
            while (true) {
                const left = index * 2 + 1;
                if (left >= this.nodes.length) break;
                const right = left + 1;
                const child = right < this.nodes.length
                    && this.priorities[right] < this.priorities[left]
                    ? right : left;
                if (this.priorities[child] >= tailPriority) break;
                this.nodes[index] = this.nodes[child];
                this.priorities[index] = this.priorities[child];
                index = child;
            }
            this.nodes[index] = tailNode;
            this.priorities[index] = tailPriority;
        }
        return result;
    }
}

function sanitizeSnap(snap) {
    const segmentId = Number(snap?.segmentId);
    const t = Number(snap?.t);
    if (!Number.isInteger(segmentId) || segmentId < 0 || segmentId >= graph.segmentCount) {
        throw new Error('Route endpoint references an invalid graph segment.');
    }
    if (!Number.isFinite(t) || t < 0 || t > 1) {
        throw new Error('Route endpoint has an invalid segment position.');
    }
    const a = graph.segmentA[segmentId];
    const b = graph.segmentB[segmentId];
    return {
        segmentId,
        t,
        a,
        b,
        coordinates: [
            graph.longitudes[a] + t * (graph.longitudes[b] - graph.longitudes[a]),
            graph.latitudes[a] + t * (graph.latitudes[b] - graph.latitudes[a])
        ]
    };
}

function routeForProfile(rawStart, rawEnd, profileId) {
    const profileIndex = profileIndexes.get(profileId);
    if (profileIndex === undefined) throw new Error(`Unknown routing profile: ${profileId}`);
    const start = sanitizeSnap(rawStart);
    const end = sanitizeSnap(rawEnd);
    const startAb = edgeWeight(profileIndex, directedEdge(start.a, start.b));
    const startBa = edgeWeight(profileIndex, directedEdge(start.b, start.a));
    const endAb = edgeWeight(profileIndex, directedEdge(end.a, end.b));
    const endBa = edgeWeight(profileIndex, directedEdge(end.b, end.a));

    let bestWeight = Infinity;
    let bestGoal = -1;
    let direct = false;
    if (start.segmentId === end.segmentId) {
        const delta = end.t - start.t;
        const candidate = delta >= 0
            ? partialWeight(startAb, delta)
            : partialWeight(startBa, -delta);
        if (candidate < bestWeight) {
            bestWeight = candidate;
            direct = true;
        }
    }

    const distances = new Float64Array(graph.nodeCount);
    distances.fill(Infinity);
    const previous = new Int32Array(graph.nodeCount);
    previous.fill(-1);
    const queue = new MinHeap();
    const scale = heuristicScales[profileIndex] || 0;
    const heuristic = node => scale * distanceMeters(
        graph.longitudes[node],
        graph.latitudes[node],
        end.coordinates[0],
        end.coordinates[1]
    );
    const addStart = (node, weight) => {
        if (weight < distances[node]) {
            distances[node] = weight;
            previous[node] = -2;
            queue.push(weight + heuristic(node), node);
        }
    };
    addStart(start.a, partialWeight(startBa, start.t));
    addStart(start.b, partialWeight(startAb, 1 - start.t));

    let visitedNodes = 0;
    while (queue.size) {
        const node = queue.pop();
        const currentPriority = queue.lastPriority;
        const expectedPriority = distances[node] + heuristic(node);
        if (currentPriority > expectedPriority + 1e-7) continue;
        if (currentPriority >= bestWeight) break;
        visitedNodes += 1;

        let terminal = Infinity;
        if (node === end.a) terminal = partialWeight(endAb, end.t);
        if (node === end.b) terminal = Math.min(terminal, partialWeight(endBa, 1 - end.t));
        if (distances[node] + terminal < bestWeight) {
            bestWeight = distances[node] + terminal;
            bestGoal = node;
            direct = false;
        }

        for (
            let edgeId = graph.adjacencyOffsets[node];
            edgeId < graph.adjacencyOffsets[node + 1];
            edgeId += 1
        ) {
            const weight = edgeWeight(profileIndex, edgeId);
            if (!Number.isFinite(weight)) continue;
            const target = graph.targets[edgeId];
            const candidate = distances[node] + weight;
            if (candidate < distances[target]) {
                distances[target] = candidate;
                previous[target] = node;
                queue.push(candidate + heuristic(target), target);
            }
        }
    }

    if (!Number.isFinite(bestWeight)) return null;
    let path;
    if (direct) {
        path = [start.coordinates, end.coordinates];
    } else {
        const nodePath = [];
        for (let node = bestGoal; node >= 0; node = previous[node]) {
            nodePath.push(node);
            if (previous[node] === -2) break;
        }
        nodePath.reverse();
        path = [start.coordinates];
        for (const node of nodePath) {
            const coordinate = [graph.longitudes[node], graph.latitudes[node]];
            const last = path[path.length - 1];
            if (coordinate[0] !== last[0] || coordinate[1] !== last[1]) path.push(coordinate);
        }
        const last = path[path.length - 1];
        if (end.coordinates[0] !== last[0] || end.coordinates[1] !== last[1]) {
            path.push(end.coordinates);
        }
        if (path.length === 1) path.push(end.coordinates);
    }
    return { path, weight: bestWeight, distanceM: pathDistanceM(path), visitedNodes };
}

function routeRequest({
    start,
    end,
    profileId,
    comparisonProfileId,
    fallbackProfileId
}) {
    requireGraph();
    const primary = routeForProfile(start, end, profileId);
    let comparison = null;
    if (comparisonProfileId) {
        comparison = routeForProfile(start, end, comparisonProfileId);
    } else if (!primary && fallbackProfileId) {
        comparison = routeForProfile(start, end, fallbackProfileId);
    }
    return {
        primary,
        comparison
    };
}
