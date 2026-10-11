"""Offline provider tests using real binary PBFs and OSMnx geometry parsing."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import ast
import hashlib
import json
import os
import sys

import osmium
import osmnx
import geopandas as gpd
import pytest
from shapely.geometry import box, mapping

import pbf_acquisition as pbf
from overpass_acquisition import OverpassAcquisitionError, features_from_polygon_with_failover
from time_utils import isoformat_utc


AOI = box(-1, -1, 1, 1)
TAGS = {"highway": ["footway", "pedestrian", "residential"], "kerb": True}
# Crossing way: both end nodes are outside the AOI. Multipolygon: its outer
# ring encloses the AOI; its member ways have no tags. Node/way IDs overlap.
XML = '''<osm version="0.6">
  <node id="1" lat="0" lon="-2"/>
  <node id="2" lat="0" lon="2"/>
  <node id="3" lat="0" lon="0"><tag k="kerb" v="lowered"/><tag k="name" v="広島"/></node>
  <node id="4" lat="-2" lon="-2"/>
  <node id="5" lat="-2" lon="2"/>
  <node id="6" lat="2" lon="2"/>
  <node id="7" lat="2" lon="-2"/>
  <node id="8" lat="-0.2" lon="-0.2"/>
  <node id="9" lat="-0.2" lon="0.2"/>
  <node id="10" lat="0.2" lon="0.2"/>
  <node id="11" lat="0.2" lon="-0.2"/>
  <node id="12" lat="10" lon="10"><tag k="kerb" v="raised"/></node>
  <way id="3"><nd ref="1"/><nd ref="2"/><tag k="highway" v="footway"/><tag k="footway" v="sidewalk"/></way>
  <way id="4"><nd ref="4"/><nd ref="5"/><nd ref="6"/><nd ref="7"/><nd ref="4"/></way>
  <way id="5"><nd ref="8"/><nd ref="9"/><nd ref="10"/><nd ref="11"/><nd ref="8"/></way>
  <way id="6"><nd ref="1"/><nd ref="3"/><tag k="highway" v="residential"/></way>
  <way id="7"><nd ref="8"/><nd ref="9"/><nd ref="10"/><nd ref="8"/><tag k="highway" v="footway"/></way>
  <way id="8"><nd ref="1"/><nd ref="2"/><tag k="waterway" v="stream"/></way>
  <relation id="20"><member type="way" ref="4" role="outer"/><member type="way" ref="5" role="inner"/><tag k="type" v="multipolygon"/><tag k="highway" v="pedestrian"/></relation>
</osm>'''


def write_pbf(directory, *, xml=XML, timestamp=None, name="source"):
    source = directory / f"{name}.osm"
    source.write_text(xml)
    header = osmium.io.Header()
    if timestamp is not False:
        header.set("osmosis_replication_timestamp", timestamp or isoformat_utc())
    target = directory / f"{name}.osm.pbf"
    with osmium.SimpleWriter(str(target), header=header) as writer:
        for item in osmium.FileProcessor(source):
            writer.add(item)
    return target


def catalog_entry(identifier, bounds, url=None):
    return {
        "geometry": mapping(box(*bounds)),
        "properties": {"id": identifier, "urls": {"pbf": url or f"https://download.geofabrik.de/{identifier}-latest.osm.pbf"}},
    }


def test_real_binary_pbf_preserves_osmnx_ids_tags_and_geometry(tmp_path):
    path = write_pbf(tmp_path)
    result = pbf.features_from_pbf(osmnx, path, AOI, TAGS)
    expected = osmnx.features_from_xml(tmp_path / "source.osm", polygon=AOI, tags=TAGS)
    assert set(result.index) == {("node", 3), ("way", 3), ("way", 6), ("way", 7), ("relation", 20)}
    assert result.crs == expected.crs
    assert result.index.names == expected.index.names
    for identity in expected.index:
        assert result.loc[identity].geometry.equals(expected.loc[identity].geometry)
    assert result.loc[("node", 3), "name"] == "広島"
    assert result.loc[("way", 3), "footway"] == "sidewalk"
    assert result.loc[("way", 3)].geometry.bounds == (-2, 0, 2, 0)
    assert result.loc[("way", 7)].geometry.geom_type == "LineString"
    assert len(result.loc[("relation", 20)].geometry.interiors) == 1


def test_relation_enclosing_aoi_survives_when_each_outer_member_is_outside(tmp_path):
    xml = XML.replace('<way id="4"><nd ref="4"/><nd ref="5"/><nd ref="6"/><nd ref="7"/><nd ref="4"/></way>', '')
    ways = ''.join(f'<way id="{identifier}"><nd ref="{a}"/><nd ref="{b}"/></way>'
                   for identifier, a, b in [(40, 4, 5), (41, 5, 6), (42, 6, 7), (43, 7, 4)])
    xml = xml.replace('<relation id="20">', ways + '<relation id="20">')
    xml = xml.replace('<member type="way" ref="4" role="outer"/>',
                      ''.join(f'<member type="way" ref="{i}" role="outer"/>' for i in range(40, 44)))
    path = write_pbf(tmp_path, xml=xml)
    result = pbf.features_from_pbf(osmnx, path, AOI, TAGS)
    assert ("relation", 20) in result.index
    assert len(result.loc[("relation", 20)].geometry.interiors) == 1


@pytest.mark.parametrize("xml", [
    '<osm version="0.6"><way id="1"><nd ref="99"/><tag k="highway" v="footway"/></way></osm>',
    '<osm version="0.6"><relation id="1"><member type="way" ref="99" role="outer"/><tag k="type" v="multipolygon"/><tag k="highway" v="pedestrian"/></relation></osm>',
])
def test_incomplete_references_fail_instead_of_publishing_partial_data(tmp_path, xml):
    path = write_pbf(tmp_path, xml=xml)
    with pytest.raises(pbf.PbfAcquisitionError, match="Incomplete"):
        pbf.features_from_pbf(osmnx, path, AOI, TAGS)


def test_empty_and_corrupt_pbf_fail(tmp_path):
    path = write_pbf(tmp_path)
    with pytest.raises(pbf.PbfAcquisitionError, match="No matching"):
        pbf.features_from_pbf(osmnx, path, AOI, {"missing": True})
    with pytest.raises(osmnx._errors.InsufficientResponseError):
        pbf.features_from_pbf(osmnx, path, box(30, 30, 31, 31), TAGS)
    path.write_bytes(b"not a pbf")
    with pytest.raises(RuntimeError):
        pbf.features_from_pbf(osmnx, path, AOI, TAGS)


def test_region_must_cover_whole_aoi_and_use_public_pbf():
    index = {"features": [
        catalog_entry("too-small", (-0.5, -0.5, 0.5, 0.5)),
        catalog_entry("large", (-10, -10, 10, 10)),
        catalog_entry("small", (-2, -2, 2, 2)),
        catalog_entry("private", (-1, -1, 1, 1), "https://osm-internal.download.geofabrik.de/private.pbf"),
    ]}
    assert pbf.select_region(index, AOI)[0] == "small"
    assert pbf.select_region(index, AOI, "large")[0] == "large"
    with pytest.raises(pbf.PbfAcquisitionError, match="covers the complete"):
        pbf.select_region(index, AOI, "too-small")
    with pytest.raises(pbf.PbfAcquisitionError):
        pbf.select_region(index, AOI.union(box(20, 20, 21, 21)))


def test_empty_catalogue_boundaries_use_individual_geojson_and_covering_parents():
    asia = catalog_entry("asia", (-20, -20, 20, 20))
    japan = catalog_entry("japan", (-3, -3, 3, 3))
    chugoku = catalog_entry("chugoku", (-2, -2, 2, 2))
    america = catalog_entry("america", (30, 30, 40, 40))
    irrelevant = catalog_entry("missing-american-region", (31, 31, 32, 32))
    documents = {item["properties"]["id"]: item["geometry"] for item in [japan, chugoku]}
    for entry, parent in [(japan, "asia"), (chugoku, "japan"), (irrelevant, "america")]:
        entry["geometry"] = {"type": "MultiPolygon", "coordinates": [[[]]]}
        entry["properties"]["parent"] = parent
    calls = []
    def load(url):
        identifier = url.rsplit("/", 1)[-1].removesuffix(".geojson")
        calls.append(identifier)
        return documents[identifier]
    index = {"features": [chugoku, irrelevant, japan, america, asia]}
    assert pbf.select_region(index, AOI, boundary_loader=load)[0] == "chugoku"
    assert calls == ["japan", "chugoku"]
    documents["japan"] = mapping(box(5, 5, 6, 6))
    calls.clear()
    assert pbf.select_region(index, AOI, boundary_loader=load)[0] == "asia"
    assert calls == ["japan"]


@pytest.mark.parametrize("timestamp,minimum,reason", [
    (False, None, "no valid replication"),
    ("2026-10-01T00:00:00Z", None, "older than"),
    ("2026-10-11T00:00:00Z", None, "future"),
    ("2026-10-09T00:00:00Z", datetime(2026, 10, 9, 12, tzinfo=timezone.utc), "predates"),
])
def test_snapshot_validation(tmp_path, timestamp, minimum, reason):
    path = write_pbf(tmp_path, timestamp=timestamp)
    with pytest.raises(pbf.PbfAcquisitionError, match=reason):
        pbf._snapshot_timestamp(path, now=datetime(2026, 10, 10, tzinfo=timezone.utc), max_age_hours=72, minimum_timestamp=minimum)


def test_end_to_end_fallback_cache_and_provenance(tmp_path, monkeypatch):
    path = write_pbf(tmp_path)
    index = {"features": [catalog_entry("test-region", (-3, -3, 3, 3))]}
    downloads = []

    def download(url, destination, **kwargs):
        downloads.append(url)
        data = json.dumps(index).encode() if url == pbf.INDEX_URL else path.read_bytes()
        Path(destination).write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    monkeypatch.setattr(pbf, "_download", download)
    options = {"cache_dir": tmp_path / "cache"}
    first = pbf.features_from_polygon_pbf(osmnx, AOI, TAGS, **options)
    second = pbf.features_from_polygon_pbf(osmnx, AOI, TAGS, **options)
    info = first.attrs[pbf.PROVENANCE_KEY]
    assert info["provider"] == "geofabrik_pbf"
    assert info["region"] == "test-region"
    assert info["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert info["snapshot_timestamp"]
    assert info["cache_hit"] is False
    assert second.attrs[pbf.PROVENANCE_KEY]["cache_hit"] is True
    assert len([url for url in downloads if url != pbf.INDEX_URL]) == 1
    assert set(first.index) == set(second.index)
    # A checksum mismatch forces a fresh download.
    next((tmp_path / "cache").glob("*.pbf")).write_bytes(b"corrupted")
    third = pbf.features_from_polygon_pbf(osmnx, AOI, TAGS, **options)
    assert third.attrs[pbf.PROVENANCE_KEY]["cache_hit"] is False
    assert len([url for url in downloads if url != pbf.INDEX_URL]) == 2
    assert not list((tmp_path / "cache").glob("features-*"))


def test_stale_replacement_does_not_overwrite_good_cache(tmp_path, monkeypatch):
    source = write_pbf(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()

    def download(url, destination, **kwargs):
        data = source.read_bytes()
        Path(destination).write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    monkeypatch.setattr(pbf, "_download", download)
    kwargs = dict(max_download_bytes=10**6, max_age_hours=72, minimum_timestamp=None)
    target, _, checksum, _ = pbf._cached_snapshot("https://example.test/test.pbf", cache, **kwargs)
    metadata_path = next(cache.glob("*.json"))
    metadata = json.loads(metadata_path.read_text())
    metadata["downloaded_at"] = isoformat_utc(datetime.now(timezone.utc) - timedelta(days=2))
    metadata_path.write_text(json.dumps(metadata))
    source = write_pbf(tmp_path, name="stale", timestamp="2000-01-01T00:00:00Z")
    with pytest.raises(pbf.PbfAcquisitionError, match="older than"):
        pbf._cached_snapshot("https://example.test/test.pbf", cache, **kwargs)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == checksum
    assert not list(cache.glob("download-*"))


@pytest.mark.parametrize("content_length,chunks", [("100", [b"data"]), ("0", [b"12345", b"67890"])])
def test_download_limit_with_and_without_content_length(tmp_path, monkeypatch, content_length, chunks):
    class Response:
        headers = {"Content-Length": content_length}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, **kwargs): return iter(chunks)
    monkeypatch.setattr(pbf.requests, "get", lambda *a, **kw: Response())
    with pytest.raises(pbf.PbfAcquisitionError, match="exceed"):
        pbf._download("https://example.test/a.pbf", tmp_path / "part", max_bytes=8)


def test_pbf_runs_only_after_all_overpass_attempts_and_restores_settings(monkeypatch):
    calls = []
    fake = SimpleNamespace(settings=SimpleNamespace(overpass_url="original"))
    def overpass(*args):
        calls.append(fake.settings.overpass_url)
        raise RuntimeError("offline")
    def fallback(*args, **kwargs):
        assert fake.settings.overpass_url == "original"
        calls.append("pbf")
        return "pbf features"
    fake.features_from_polygon = overpass
    monkeypatch.setattr(pbf, "features_from_polygon_pbf", fallback)
    assert features_from_polygon_with_failover(fake, AOI, TAGS, endpoints=("one", "two"), sleep=lambda _: None, pbf_options={}) == "pbf features"
    assert calls == ["one", "one", "two", "two", "pbf"]
    fake.features_from_polygon = lambda *a: "live features"
    assert features_from_polygon_with_failover(fake, AOI, TAGS, pbf_options={}) == "live features"
    assert calls.count("pbf") == 1


def test_disabled_pbf_and_combined_failure(monkeypatch):
    fake = SimpleNamespace(settings=SimpleNamespace(overpass_url="original"))
    def unavailable(*args, **kwargs): raise RuntimeError("provider unavailable")
    fake.features_from_polygon = unavailable
    monkeypatch.setattr(pbf, "features_from_polygon_pbf", unavailable)
    for options in [None, {}]:
        with pytest.raises(OverpassAcquisitionError) as error:
            features_from_polygon_with_failover(fake, AOI, TAGS, endpoints=("one",), attempts_per_endpoint=1, pbf_options=options)
        assert "one attempt 1" in str(error.value)
        assert ("Geofabrik PBF" in str(error.value)) == (options is not None)
        assert fake.settings.overpass_url == "original"
    assert pbf.pbf_options_from_config({"PBF_FALLBACK_ENABLED": False}) is None
    assert pbf.pbf_options_from_config(SimpleNamespace())["region"] == "auto"


def load_function(relative_path, name, namespace):
    """Run the actual entry point without importing a live node's config."""
    path = Path(__file__).resolve().parents[1] / relative_path
    function = next(item for item in ast.parse(path.read_text()).body if isinstance(item, ast.FunctionDef) and item.name == name)
    namespace["__file__"] = str(path)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize("fail", [False, True])
def test_full_acquisition_uses_snapshot_cutoff_and_preserves_raw_on_failure(tmp_path, monkeypatch, fail):
    from time_utils import parse_timestamp
    import time

    source = write_pbf(tmp_path)
    features = pbf.features_from_pbf(osmnx, source, AOI, TAGS)
    snapshot = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)
    previous = snapshot - timedelta(days=1)
    acquisition = {"provider": "geofabrik_pbf", "snapshot_timestamp": isoformat_utc(snapshot), "sha256": "checksum"}
    features.attrs[pbf.PROVENANCE_KEY] = acquisition
    boundary = gpd.GeoDataFrame(geometry=[AOI], crs=4326)
    raw = {name: str(tmp_path / f"{name}.parquet") for name in ["sidewalks", "kerbs"]}
    for path in raw.values(): Path(path).write_bytes(b"previous raw data")
    boundary_path = tmp_path / "boundary.geojson"
    boundary_path.touch()
    registry = {}
    reports = {}

    def acquire(*args, **kwargs):
        assert kwargs["pbf_options"]["minimum_timestamp"] == previous
        if fail: raise OverpassAcquisitionError("all providers unavailable")
        return features

    monkeypatch.setitem(sys.modules, "watcher_lib", SimpleNamespace(_load_last_processed_time=lambda key: previous))
    monkeypatch.setenv("OSWM_FORCE_FULL_FETCH", "1")
    main = load_function("getting_data.py", "main", dict(
        os=os, gpd=SimpleNamespace(read_file=lambda path: boundary), ox=osmnx,
        layer_tags_dict={"sidewalks": {"footway": ["sidewalk"]}, "kerbs": {"kerb": ["lowered"]}},
        paths_dict={"data_raw": raw}, boundaries_folderpath=str(tmp_path),
        boundaries_geojson_path=str(boundary_path), boundaries_path=str(boundary_path),
        boundaries_infos_path=str(tmp_path / "infos.json"), CITY_NAME="Test",
        OTHER_FOOTWAY_EXCLUSION_RULES={}, updating_infos_path=str(tmp_path / "registry.json"),
        create_folder_if_not_exists=lambda path: None,
        dump_json=lambda data, path: reports.update({str(path): data}),
        save_geoparquet=lambda frame, path: frame.to_parquet(path),
        merge_list_of_dictionaries=lambda items: TAGS,
        features_from_polygon_with_failover=acquire,
        pbf_options_from_config=pbf.pbf_options_from_config, PROVENANCE_KEY=pbf.PROVENANCE_KEY,
        record_datetime=lambda key, value=None: registry.update({key: value}),
        parse_timestamp=parse_timestamp, formatted_datetime_now=isoformat_utc,
        gen_updating_infotable_page=lambda: None, time=time.monotonic, sleep=lambda _: None,
    ))
    if fail:
        with pytest.raises(OverpassAcquisitionError): main()
        assert all(Path(path).read_bytes() == b"previous raw data" for path in raw.values())
        assert not registry
        assert str(tmp_path / "acquisition.json") not in reports
    else:
        main()
        assert registry["Data Fetching"] == snapshot
        assert reports[str(tmp_path / "acquisition.json")] == acquisition
        assert gpd.read_parquet(raw["sidewalks"])["id"].tolist() == [3]
        assert gpd.read_parquet(raw["kerbs"])["id"].tolist() == [3]


def test_completeness_pbf_fallback_persists_only_roads_and_provenance(tmp_path, monkeypatch):
    source = write_pbf(tmp_path)
    features = pbf.features_from_pbf(osmnx, source, AOI, TAGS)
    provenance = {"provider": "geofabrik_pbf", "snapshot_timestamp": isoformat_utc()}
    features.attrs[pbf.PROVENANCE_KEY] = provenance
    calls = []

    def unavailable(*args): raise TimeoutError("Overpass unavailable")
    def fallback(*args, **kwargs):
        calls.append("pbf")
        return features

    monkeypatch.setattr(osmnx, "features_from_polygon", unavailable)
    monkeypatch.setattr(pbf, "features_from_polygon_pbf", fallback)
    cache = tmp_path / "roads.parquet"
    load = load_function("data_quality/completeness/completeness_lib.py", "fetch_or_load_roads", dict(
        os=os, gpd=gpd, box=box, ROADS_CACHE_PATH=str(cache), ROAD_HIGHWAY_TYPES=["residential"],
        node_config=SimpleNamespace(OVERPASS_ATTEMPTS_PER_ENDPOINT=1, OVERPASS_BACKOFF_SECONDS=0),
        DEFAULT_OVERPASS_ENDPOINTS=("offline",),
        features_from_polygon_with_failover=features_from_polygon_with_failover,
        pbf_options_from_config=pbf.pbf_options_from_config, PROVENANCE_KEY=pbf.PROVENANCE_KEY,
        create_folder_if_not_exists=lambda path: Path(path).mkdir(exist_ok=True),
        dump_json=lambda data, path: Path(path).write_text(json.dumps(data)),
    ))
    roads = load(AOI.bounds, silent=True)
    assert set(roads.geometry.geom_type) == {"LineString"}
    assert list(roads.columns) == ["geometry"]
    assert json.loads(Path(f"{cache}.source.json").read_text()) == provenance
    assert len(load(AOI.bounds, silent=True)) == len(roads)
    assert calls == ["pbf"]
