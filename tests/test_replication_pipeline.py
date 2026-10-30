"""Experimental daily path: real city extraction, retries and legacy isolation."""

import json
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import geopandas as gpd
import pytest
import requests
from shapely.geometry import box, mapping
import yaml

import replication_pipeline as pipeline
from pipeline_decision import decide
from test_pbf_replication import URL, BASE, TIMES, write_snapshot


@pytest.fixture
def city(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/boundaries").mkdir(parents=True)
    Path("data/updates").mkdir()
    Path("config.py").write_text('CITY_NAME = "Curitiba"\n')
    gpd.GeoDataFrame(geometry=[box(-1, -1, 1, 1)], crs=4326).to_file("data/boundaries/polygon.geojson")
    cfg = SimpleNamespace(
        boundaries_geojson_path="data/boundaries/polygon.geojson",
        updating_infos_path="data/updates/registry.json", PBF_REGION="test",
        layer_tags_dict={"kerbs": {"kerb": ["lowered", "raised"]}, "sidewalks": {"footway": ["sidewalk"]},
                         "crossings": {"footway": ["crossing"]}, "other_footways": {"highway": ["footway"]}},
        OTHER_FOOTWAY_EXCLUSION_RULES={"access": ["private"]},
    )
    monkeypatch.setitem(sys.modules, "constants", cfg)

    def merged(items):
        result = {}
        for item in items:
            for key, values in item.items():
                values = [values] if isinstance(values, str) else values
                if values is True:
                    result[key] = True
                elif result.get(key) is not True:
                    result[key] = list(set(result.get(key, []) + values))
        return result
    monkeypatch.setitem(sys.modules, "functions", SimpleNamespace(merge_list_of_dictionaries=merged))
    import pbf_acquisition
    monkeypatch.setattr(pbf_acquisition, "_cached_json", lambda *a, **k: {"features": [
        {"geometry": mapping(box(-2, -2, 2, 2)), "properties": {"id": "test", "urls": {"pbf": URL}}}
    ]})
    source = write_snapshot(tmp_path, 101)
    import pbf_replication
    monkeypatch.setattr(pbf_replication, "sync_source", lambda *a, **k: (source, {
        "provider": pipeline.BACKEND, "sequence": 101, "snapshot_timestamp": TIMES[101],
        "checked_at": TIMES[102], "replication_url": BASE,
    }))

    def denied(*args, **kwargs):
        raise AssertionError("Network request in offline replica integration test")
    monkeypatch.setattr(requests.sessions.Session, "request", denied)
    monkeypatch.setenv("OSWM_OSM_UPDATE_BACKEND", pipeline.BACKEND)
    return source, cfg


def test_prepare_real_binary_geometry_then_retry_cannot_skip_unpublished_data(city):
    report = pipeline.prepare()
    assert report["needs_update"]
    assert report["city_fingerprints"]["crossings"]["count"] == 0
    assert report["city_fingerprints"][pipeline.ROADS]["count"] == 1
    pipeline.install_prepared()
    assert not Path("data/updates/acquisition.json").exists()
    # Simulate failure after installation: no publication checkpoint exists.
    assert pipeline.prepare()["needs_update"]
    pipeline.finalize()
    assert not pipeline.prepare()["needs_update"]
    assert json.loads(Path("data/updates/registry.json").read_text())["Data Fetching"] == TIMES[101]
    pipeline.render()  # Must not query ohsome, including while rendering feeds.
    assert "net snapshot differences" in Path("hub/watcher/index.html").read_text()


def test_stage_tampering_cannot_be_installed(city):
    pipeline.prepare()
    frame = gpd.read_parquet(pipeline.STAGING / "kerbs.parquet")
    frame["kerb"] = "tampered"
    frame.to_parquet(pipeline.STAGING / "kerbs.parquet")
    with pytest.raises(ValueError, match="changed after prepare"):
        pipeline.install_prepared()
    assert not Path("data/raw").exists()


def test_road_only_changes_and_missing_raw_inputs_require_generation(city):
    pipeline.prepare()
    pipeline.install_prepared()
    pipeline.finalize()
    acquisition = Path("data/updates/acquisition.json")
    published = json.loads(acquisition.read_text())
    published["city_fingerprints"][pipeline.ROADS]["sha256"] = "different-road-content"
    acquisition.write_text(json.dumps(published))
    assert pipeline.prepare()["needs_update"]
    pipeline.finalize()
    Path("data/raw/kerbs.parquet").unlink()
    assert pipeline.prepare()["needs_update"]


def test_render_preserves_existing_historical_feed(city):
    pipeline.prepare()
    root = Path("hub/watcher")
    root.mkdir(parents=True)
    (root / "changesets.xml").write_text("old historical feed")
    pipeline.render()
    assert (root / "changesets.xml").read_text() == "old historical feed"


def test_replica_changes_take_precedence_over_core_rebuild(city):
    pipeline.prepare()
    decision = decide(Path.cwd(), watcher_status=1, replication_report=pipeline.REPORT)
    assert decision["mode"] == "generate"
    assert decision["reason"] == "replication_city_changes"


def test_preview_workflow_has_no_publication_credentials_or_steps():
    root = Path(__file__).resolve().parents[1]
    source = (root / ".github/workflows/node_replication_preview.yml").read_text()
    workflow = yaml.safe_load(source)
    assert workflow["permissions"] == {"contents": "read"}
    assert "github.repository == 'kauevestena/opensidewalkmap_beta'" in workflow["jobs"]["preview"]["if"]
    runs = "\n".join(step.get("run", "") for step in workflow["jobs"]["preview"]["steps"])
    assert "git push" not in runs and "gh workflow" not in runs
    assert "persist-credentials: false" in source
    assert "actions/cache/restore@v4" in source and "actions/cache/save@v4" in source


def test_completeness_uses_source_date_cached_history_and_same_snapshot_roads(city, monkeypatch):
    pipeline.prepare()
    pipeline.install_prepared()
    _, cfg = city
    cfg.CITY_NAME = "Curitiba"
    cfg.sidewalks_path = "data/processed/sidewalks.parquet"
    cfg.processed_folderpath = "data/processed"
    helpers = sys.modules["functions"]
    helpers.get_boundaries_infos = lambda: {}
    helpers.create_folder_if_not_exists = lambda path: Path(path).mkdir(parents=True, exist_ok=True)
    helpers.dump_json = lambda value, path: Path(path).write_text(json.dumps(value))
    path = Path(__file__).resolve().parents[1] / "data_quality/completeness/completeness_lib.py"
    spec = importlib.util.spec_from_file_location("replica_completeness_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.get_current_timestamp() == TIMES[101][:10]
    assert len(module.fetch_or_load_roads((-1, -1, 1, 1))) == 1
    monkeypatch.setattr(module, "compute_local_snapshot", lambda *a, **k: ({}, {}, {}, {}))
    monkeypatch.setattr(module, "compute_ohsome_historical", lambda *a, **k: pytest.fail("ohsome queried"))
    bounds = (-49.3, -25.5, -49.299, -25.499)
    existing = module._init_results_structure(bounds, ["2020-01-01"])
    for zoom in existing["zoom_levels"].values():
        for tile in zoom["tiles"].values():
            tile["data"] = [{"timestamp": "2020-01-01", "historical_marker": 123}]
    result = module.run_completeness_analysis(bounds, existing_data=existing, silent=True)
    assert result["metadata"]["historical_backfill"] == "unavailable"
    assert TIMES[101][:10] in result["timestamps"]
    for zoom in result["zoom_levels"].values():
        for tile in zoom["tiles"].values():
            assert any(entry.get("historical_marker") == 123 for entry in tile["data"])
