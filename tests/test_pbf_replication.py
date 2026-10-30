"""Real binary snapshots and change files exercise the replication state machine."""

from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import osmium
import osmnx
import pytest
import requests
from shapely.geometry import box

import pbf_replication as replica
from pbf_acquisition import features_from_pbf
from replication_pipeline import difference, fingerprint


URL = "https://download.geofabrik.de/test-latest.osm.pbf"
BASE = "https://download.geofabrik.de/test-updates"
NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
TIMES = {100: "2026-10-27T21:00:00Z", 101: "2026-10-28T21:00:00Z", 102: "2026-10-29T21:00:00Z"}
N1 = '<node id="1" version="1" lat="0" lon="-0.5"/>'
N2 = '<node id="2" version="1" lat="0" lon="0.5"/>'
N3 = '<node id="3" version="1" lat="0" lon="0"><tag k="kerb" v="lowered"/></node>'
N4 = '<node id="4" version="1" lat="0.5" lon="0"/>'
W10 = '<way id="10" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/><tag k="footway" v="sidewalk"/></way>'
W11 = '<way id="11" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>'
W12 = '<way id="12" version="1"><nd ref="2"/><nd ref="4"/><tag k="highway" v="construction"/></way>'
R20 = '<relation id="20" version="1"><member type="way" ref="10" role=""/><member type="way" ref="11" role=""/><tag k="type" v="route"/></relation>'
MOVED = N1.replace('version="1"', 'version="2"').replace('lat="0"', 'lat="0.1"')
NEW = '<node id="5" version="1" lat="0.2" lon="0.2"><tag k="kerb" v="raised"/></node>'
RETAGGED = W12.replace('version="1"', 'version="2"').replace('construction', 'footway')
REMOVED = W10.replace('version="1"', 'version="2"').replace('v="footway"', 'v="service"').replace('<tag k="footway" v="sidewalk"/>', '')
REL = R20.replace('version="1"', 'version="2"').replace('<member type="way" ref="11" role=""/>', '')
SNAPSHOTS = {
    100: N1 + N2 + N3 + N4 + W10 + W11 + W12 + R20,
    101: MOVED + N2 + N4 + NEW + W10 + W11 + RETAGGED + R20,
    102: MOVED + N2 + N4 + NEW + REMOVED + W11 + RETAGGED + REL,
}
DIFFS = {
    101: f'<create>{NEW}</create><modify>{MOVED}{RETAGGED}</modify>'
         '<delete><node id="3" version="2" visible="false"/></delete>',
    102: f'<modify>{REMOVED}{REL}</modify>',
}


def write_snapshot(tmp, seq, *, base=BASE):
    xml = tmp / f"{seq}.osm"
    xml.write_text('<osm version="0.6">' + SNAPSHOTS[seq] + '</osm>')
    header = osmium.io.Header()
    for key, value in {"base_url": base, "sequence_number": str(seq), "timestamp": TIMES[seq]}.items():
        header.set("osmosis_replication_" + key, value)
    path = tmp / f"{seq}.osm.pbf"
    with osmium.SimpleWriter(str(path), header=header) as writer:
        for obj in osmium.FileProcessor(xml):
            writer.add(obj)
    return path


@pytest.fixture
def server(tmp_path):
    snapshots = {s: write_snapshot(tmp_path, s) for s in TIMES}
    resources = {URL: snapshots[102].read_bytes(), URL.replace('latest', '261027'): snapshots[100].read_bytes()}
    for seq, stamp in TIMES.items():
        resources[f"{BASE}/{replica.sequence_path(seq)}.state.txt"] = f"sequenceNumber={seq}\ntimestamp={stamp}\n".encode()
    resources[f"{BASE}/state.txt"] = resources[f"{BASE}/000/000/102.state.txt"]
    for seq, xml in DIFFS.items():
        resources[f"{BASE}/{replica.sequence_path(seq)}.osc.gz"] = gzip.compress(
            ('<osmChange version="0.6">' + xml + '</osmChange>').encode())
    calls = []

    def fetch(url, destination, *, max_bytes):
        calls.append(url)
        if url not in resources:
            response = requests.Response()
            response.status_code = 404
            raise requests.HTTPError("missing", response=response)
        data = resources[url]
        if len(data) > max_bytes:
            raise replica.ReplicationError("size budget")
        destination.write_bytes(data)
        return hashlib.sha256(data).hexdigest()
    return snapshots, resources, calls, fetch


def sync(tmp, server, **kwargs):
    return replica.sync_source(URL, tmp / "cache", now=NOW, fetch=server[3], **kwargs)


def test_two_real_binary_advances_equal_independent_snapshots_and_then_noop(tmp_path, server):
    first, report = sync(tmp_path, server, bootstrap_url=URL.replace('latest', '261027'), target_sequence=101)
    assert report["diffs_applied"] == 1
    assert replica.semantic_digest(first) == replica.semantic_digest(server[0][101])
    second, report = sync(tmp_path, server)
    assert report["from_sequence"] == 101 and report["sequence"] == 102
    assert report["diffs_applied"] == 1
    assert replica.semantic_digest(second) == replica.semantic_digest(server[0][102])
    calls = len(server[2])
    third, report = sync(tmp_path, server)
    assert third == second and report["diffs_applied"] == 0
    assert server[2][calls:] == [BASE + "/state.txt"]
    assert len(list((tmp_path / "cache").glob("source-*.osm.pbf"))) == 1


def test_node_move_deletion_filter_transition_and_negative_control(tmp_path, server):
    result, _ = sync(tmp_path, server, bootstrap_url=URL.replace('latest', '261027'), target_sequence=101)
    tags = {"highway": "footway", "kerb": True}
    before = features_from_pbf(osmnx, server[0][100], box(-1, -1, 1, 1), tags)
    after = features_from_pbf(osmnx, result, box(-1, -1, 1, 1), tags)
    assert not before.loc[("way", 10)].geometry.equals(after.loc[("way", 10)].geometry)
    assert ("node", 3) not in after.index and ("node", 5) in after.index
    assert ("way", 12) not in before.index and ("way", 12) in after.index
    assert replica.semantic_digest(server[0][100]) != replica.semantic_digest(result)
    expected = features_from_pbf(osmnx, server[0][101], box(-1, -1, 1, 1), tags)
    normalize = lambda f: f.reset_index().rename(columns={"osmid": "id"})
    assert fingerprint(normalize(after)) == fingerprint(normalize(expected))
    assert difference(normalize(before), normalize(after)) == {"added": 2, "removed": 1, "modified": 1}


def test_catchup_applies_two_missing_days(tmp_path, server):
    result, report = sync(tmp_path, server, bootstrap_url=URL.replace('latest', '261027'))
    assert report["diffs_applied"] == 2
    assert replica.semantic_digest(result) == replica.semantic_digest(server[0][102])


def test_missing_diff_and_evicted_or_corrupt_cache_rebootstrap(tmp_path, server):
    del server[1][BASE + "/000/000/101.osc.gz"]
    result, report = sync(tmp_path, server, bootstrap_url=URL.replace('latest', '261027'), target_sequence=100)
    result, report = sync(tmp_path, server)
    assert report["recovery"] == "bootstrap: required diff unavailable"
    assert report["sequence"] == 102
    result.write_bytes(b"corrupt")
    result, report = sync(tmp_path, server)
    assert report["sequence"] == 102 and report["recovery"].startswith("bootstrap")
    result.unlink()
    _, report = sync(tmp_path, server)
    assert report["sequence"] == 102


@pytest.mark.parametrize("failure", ["malformed", "wrong-sequence", "regressed-time", "future", "stale", "minimum", "budget"])
def test_failure_never_advances_last_good_checkpoint(tmp_path, server, failure):
    _, _ = sync(tmp_path, server, bootstrap_url=URL.replace('latest', '261027'), target_sequence=100)
    pointer = (tmp_path / "cache/current.json").read_bytes()
    params = {}
    if failure == "malformed":
        server[1][BASE + "/000/000/101.osc.gz"] = b"not gzip"
    elif failure == "wrong-sequence":
        server[1][BASE + "/000/000/101.state.txt"] = b"sequenceNumber=99\ntimestamp=2026-10-28T21:00:00Z"
    elif failure == "regressed-time":
        server[1][BASE + "/000/000/101.state.txt"] = b"sequenceNumber=101\ntimestamp=2026-10-26T21:00:00Z"
    elif failure == "future":
        server[1][BASE + "/state.txt"] = b"sequenceNumber=102\ntimestamp=2027-01-01T00:00:00Z"
    elif failure == "stale":
        params["max_age_hours"] = 1
    elif failure == "minimum":
        params["minimum_timestamp"] = NOW
    else:
        params["max_diff_bytes"] = 1
    with pytest.raises((replica.ReplicationError, OSError, RuntimeError)):
        sync(tmp_path, server, **params)
    assert (tmp_path / "cache/current.json").read_bytes() == pointer
    assert not list((tmp_path / "cache").glob("candidate-*"))


def test_foreign_region_header_and_bootstrap_rejected(tmp_path, server):
    with pytest.raises(replica.ReplicationError, match="same Geofabrik region"):
        sync(tmp_path, server, bootstrap_url="https://example.com/another.osm.pbf")
    with pytest.raises(replica.ReplicationError, match="match the region"):
        replica.read_header(server[0][100], "https://download.geofabrik.de/other-updates")


def test_canonical_features_detect_changes_with_equal_counts_and_accept_empty_layers():
    frame = gpd.GeoDataFrame({"element": ["node"], "id": [1], "kerb": ["lowered"]},
                             geometry=gpd.points_from_xy([0], [0]), crs=4326)
    changed = frame.copy()
    changed["kerb"] = "raised"
    assert fingerprint(frame) != fingerprint(changed)
    assert difference(frame, changed) == {"added": 0, "removed": 0, "modified": 1}
    assert fingerprint(frame.iloc[:0])["count"] == 0
