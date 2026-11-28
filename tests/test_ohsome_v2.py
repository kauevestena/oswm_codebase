from datetime import datetime, timezone
from io import BytesIO

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from shapely import LineString

from ohsome_v2 import BASE_URL, HistoryUnavailable, historical_layers


class Response:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code, self.payload, self.content = status, payload, content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def json(self):
        return self.payload

    def iter_content(self, **kwargs):
        yield self.content


class Session:
    def __init__(self, metadata, posts):
        self.metadata, self.posts, self.calls = metadata, iter(posts), []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.metadata

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return next(self.posts)


def parquet(start=datetime(2025, 1, 1, tzinfo=timezone.utc), empty=False):
    values = {
        "osm_type": ["way"], "osm_id": [7], "edit_timestamp": [start],
        "valid_to_timestamp": [datetime(2222, 1, 1, tzinfo=timezone.utc)],
        "geom": [LineString([(9, 45), (9.01, 45.01)]).wkb],
    }
    table = pa.table(values)
    dest = BytesIO()
    pq.write_table(table.slice(0, 0) if empty else table, dest)
    return dest.getvalue()


AOI = [9, 45, 9.02, 45.02]
DATE = "2026-08-01"
METADATA = Response(payload={"temporalExtent": {"start": "2020-01-01T00:00:00Z", "end": "2026-11-28T00:00:00Z"}})


def test_request_contract_and_empty_layer(monkeypatch):
    monkeypatch.setenv("OHSOME_API_KEY", "test-only")
    session = Session(METADATA, [Response(content=parquet()), Response(content=parquet(empty=True)), Response(content=parquet())])
    result = historical_layers(AOI, DATE, session=session, sleep=lambda _: None)
    assert [len(layer) for layer in result] == [1, 0, 1]
    assert len(session.calls) == 4
    for method, url, kwargs in session.calls:
        assert url.startswith(BASE_URL + "/")
        assert kwargs["headers"] == {"Authorization": "test-only"}
        assert not kwargs["allow_redirects"]
        if method == "POST":
            assert kwargs["json"]["time"] == DATE + "T00:00:00Z"
            assert kwargs["json"]["aoi"] == AOI
            assert kwargs["json"]["clip"] is True


@pytest.mark.parametrize("failure", [Response(401), Response(403), Response(429), Response(503),
                                     Response(content=b"truncated"), Response(content=parquet(datetime(2026, 8, 2, tzinfo=timezone.utc)))])
def test_auth_quota_schema_or_invalid_timestamp_return_no_partial_history(monkeypatch, failure):
    monkeypatch.setenv("OHSOME_API_KEY", "test-only")
    session = Session(METADATA, [Response(content=parquet()), failure])
    with pytest.raises(HistoryUnavailable, match="history was not updated"):
        historical_layers(AOI, DATE, session=session, sleep=lambda _: None)
    assert len(session.calls) == 3


def test_no_key_no_network_and_stale_metadata_prevents_extract(monkeypatch):
    monkeypatch.delenv("OHSOME_API_KEY", raising=False)
    session = Session(METADATA, [])
    with pytest.raises(HistoryUnavailable, match="requires OHSOME_API_KEY"):
        historical_layers(AOI, DATE, session=session)
    assert not session.calls
    monkeypatch.setenv("OHSOME_API_KEY", "test-only")
    with pytest.raises(HistoryUnavailable, match="does not cover"):
        historical_layers(AOI, "2026-12-01", session=session)
    assert len(session.calls) == 1


@pytest.fixture
def completeness(monkeypatch):
    import importlib.util
    from pathlib import Path
    import sys
    from types import SimpleNamespace

    # A core-only checkout has no node config. Load the helper in isolation.
    monkeypatch.setitem(sys.modules, "constants", SimpleNamespace(
        CITY_NAME="Test", boundaries_geojson_path="", sidewalks_path="", processed_folderpath="",
    ))
    monkeypatch.setitem(sys.modules, "functions", SimpleNamespace(
        get_boundaries_infos=None, create_folder_if_not_exists=None, dump_json=None,
    ))
    source = Path(__file__).resolve().parents[1] / "data_quality/completeness/completeness_lib.py"
    spec = importlib.util.spec_from_file_location("completeness_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_historical_measurements_include_a_line_crossing_node_box(monkeypatch, completeness):
    import geopandas as gpd
    import mercantile
    from shapely.geometry import box
    import ohsome_v2

    target = mercantile.tile(9.4, 45.65, completeness.MAX_ZOOM)
    w, s, e, n = mercantile.bounds(target)
    dx, dy = (e - w) / 4, (n - s) / 4
    bounds = [w + dx, s + dy, e - dx, n - dy]
    monkeypatch.setattr(completeness, "_CITY_BOUNDARY_GEOM", box(*bounds))
    crossing = LineString([(w + dx / 2, s + 2 * dy), (w + 2 * dx, s + 2 * dy)])
    frame = gpd.GeoDataFrame(geometry=[crossing], crs="EPSG:4326")
    calls = []

    def provider_clip(aoi, date):
        calls.append((aoi, date))
        clipped = gpd.clip(frame, box(*aoi))
        return (clipped, clipped.iloc[:0], clipped.iloc[:0])

    monkeypatch.setattr(ohsome_v2, "historical_layers", provider_clip)
    (roads, footways, sidewalks), method = completeness._measure_v2_history(bounds, DATE, silent=True)
    assert calls == [([w, s, e, n], DATE)]
    target_id = f"{target.z}/{target.x}/{target.y}"
    expected = frame.to_crs(method["length_crs"]).length.iloc[0]
    truncated = gpd.clip(frame, box(*bounds)).to_crs(method["length_crs"]).length.iloc[0]
    assert roads[target_id] == pytest.approx(expected)
    assert roads[target_id] > truncated
    assert footways[target_id] == sidewalks[target_id] == 0
    assert method["measurement_zoom"] == target.z
    assert method["snapshot_timestamp"] == DATE + "T00:00:00Z"
    assert method["aoi_bbox_wgs84"] == [w, s, e, n]
    assert tuple(method["filters"].values()) == ohsome_v2.FILTERS


def test_backfill_does_not_replace_a_valid_archived_date(monkeypatch, completeness):

    monkeypatch.setattr(completeness, "get_current_timestamp", lambda: "2026-11-28")

    def unexpected(*args, **kwargs):
        pytest.fail("An existing historical observation should block work before acquisition")

    monkeypatch.setattr(completeness, "compute_local_snapshot", unexpected)
    with pytest.raises(ValueError, match="already has an observation"):
        completeness.run_completeness_analysis(AOI, {"timestamps": [DATE]}, historical_date=DATE)
