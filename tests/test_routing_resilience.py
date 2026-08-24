from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString


ROOT = Path(__file__).resolve().parents[1]


def test_temporal_lookup_uses_element_namespace_and_collapses_segments():
    sys.path.insert(0, str(ROOT / "data_quality"))
    try:
        from temporal_lookup import build_temporal_lookup, temporal_attributes
    finally:
        sys.path.pop(0)

    frame = pd.DataFrame(
        {
            "element": ["node", "way", "way"],
            "id": [42, 42, 42],
            "age": [3, 7, 7],
            "last_update": ["node-date", "old-segment", "way-date"],
        }
    )

    lookup = build_temporal_lookup(frame)

    assert len(lookup) == 2
    assert temporal_attributes(lookup, SimpleNamespace(element="node", id=42))["age"] == 3
    assert temporal_attributes(lookup, SimpleNamespace(element="way", id=42)) == {
        "age": 7,
        "last_update": "way-date",
    }


def _load_routing_tiles_module(monkeypatch, tmp_path):
    constants = SimpleNamespace(
        TILES_MIN_ZOOM=9,
        TILES_MAX_ZOOM=19,
        data_folderpath=str(tmp_path / "data"),
        routing_parquet_path=str(tmp_path / "data/routing/network.parquet"),
        routing_tiles_path=str(tmp_path / "data/routing/network.pmtiles"),
        routing_tiles_report_path=str(
            tmp_path / "data/routing/tile_generation_report.json"
        ),
        routing_metadata_path=str(tmp_path / "data/routing/metadata.json"),
    )
    monkeypatch.setitem(sys.modules, "constants", constants)
    spec = importlib.util.spec_from_file_location(
        "routing_tiles_gen_test", ROOT / "generation/routing_tiles_gen.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_routing_tiles_stages_geoparquet_as_flatgeobuf(monkeypatch, tmp_path):
    module = _load_routing_tiles_module(monkeypatch, tmp_path)
    source = tmp_path / "network.parquet"
    staging = tmp_path / "network.fgb"
    frame = gpd.GeoDataFrame(
        {"edge_kind": ["sidewalk"]},
        geometry=[LineString([(0, 0), (1, 1)])],
        crs="EPSG:4326",
    )
    frame.to_parquet(source)

    assert module._flatgeobuf_source(source, staging) == staging
    staged = gpd.read_file(staging)
    assert list(staged["edge_kind"]) == ["sidewalk"]
    assert staged.crs.to_epsg() == 4326
