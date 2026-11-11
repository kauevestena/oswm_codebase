import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import FinderModule from 'geojson-path-finder';
import { createNgraph } from '../benchmarks/routing_benchmark.mjs';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const Finder = FinderModule.default ?? FinderModule;

test('all benchmark adapters preserve directional costs on a serialized fixture', () => {
    const directory = mkdtempSync(join(tmpdir(), 'oswm-benchmark-test-'));
    try {
        const build = spawnSync(process.env.PYTHON || 'python', ['-', directory], {
            cwd: ROOT, encoding: 'utf8', input: `
import json, sys
from pathlib import Path
from routing.binary_graph import build_binary_graph
from routing.profile_rules import ROUTING_PROFILES
from routing.profile_validation import public_profile_metadata
class Line:
    geom_type = 'LineString'
    def __init__(self, coordinates): self.coords = coordinates
metadata = public_profile_metadata(ROUTING_PROFILES)
payload = {'distance_profile_id': 'distance', 'profiles': {key: metadata[key] for key in ('distance', 'wheelchair')}}
rows = [{'geometry': Line([(0,0),(.001,0)]), 'edge_kind':'sidewalk', 'length_m':111.2,
         'wheelchair_grade_fwd':90, 'wheelchair_grade_bwd':20},
        {'geometry': Line([(.001,0),(.002,0)]), 'edge_kind':'sidewalk', 'length_m':111.2,
         'wheelchair_grade_fwd':45, 'wheelchair_grade_bwd':45, 'wheelchair_allow_bwd':False}]
root = Path(sys.argv[1])
graph = build_binary_graph(rows, payload, root/'network.oswmg')
payload.update(graph_sha256=graph['sha256'], graph_profile_order=graph['profile_order'], ruleset_version='fixture', ruleset_hash='fixture')
(root/'profiles.json').write_text(json.dumps(payload))
` });
        assert.equal(build.status, 0, build.stderr);
        const result = spawnSync(process.execPath, ['--expose-gc', resolve(ROOT, 'benchmarks/routing_benchmark.mjs'),
            '--graph', join(directory, 'network.oswmg'), '--profiles', join(directory, 'profiles.json'),
            '--output', join(directory, 'result.json'), '--route-count', '8', '--snap-count', '4', '--repeats', '2'],
        { cwd: ROOT, encoding: 'utf8' });
        assert.equal(result.status, 0, result.stderr);
        const report = JSON.parse(readFileSync(join(directory, 'result.json')));
        assert.equal(report.engines.length, 5);
        for (const engine of report.engines) for (const profile of engine.profiles) {
            assert.equal(profile.routing_mismatches, 0, `${engine.engine}/${profile.profile_id} route mismatch`);
            assert.equal(profile.snapping_mismatches, 0, `${engine.engine}/${profile.profile_id} snap mismatch`);
            if (profile.routing.n) assert.equal(profile.routing.n, 16);
            if (profile.snapping.n) assert.equal(profile.snapping.n, 8);
        }
        assert.ok(report.engines[0].profiles[1].answers.includes(null), 'fixture exercises blocked travel');
        assert.ok(report.engines[0].profiles[1].answers.some(value => value > 0), 'fixture exercises allowed travel');
    } finally { rmSync(directory, { recursive: true, force: true }); }
});

test('pinned GeoJSON Path Finder compaction can discard a cheaper parallel corridor', () => {
    const coordinates = [[0,0],[.001,.003],[.002,0],[.001,0],[-.0001,0],[.0021,0]];
    const edges = [[0,1,400],[1,2,400],[0,3,150],[3,2,150],[0,4,50],[2,5,50]];
    const collection = { type:'FeatureCollection', features:edges.map(([a,b,cost]) => ({
        type:'Feature', properties:{a,b,forward:[cost],backward:[cost]},
        geometry:{type:'LineString',coordinates:[coordinates[a],coordinates[b]]}
    })) };
    const point = i => ({type:'Feature',properties:{},geometry:{type:'Point',coordinates:coordinates[i]}});
    const finder = new Finder(collection, {weight:(_a,_b,p) => ({forward:p.forward[0],backward:p.backward[0]})});
    assert.equal(finder.findPath(point(0), point(2)).weight, 800);
    const other = createNgraph(collection, 0);
    assert.deepEqual(other.router.find(0, 2).map(node => node.id).reverse(), [0,3,2]);
    // The fixture's shorter path is 150 + 150 = 300; recorded mismatches must
    // remain visible, rather than timing this as an equally correct solution.
});
