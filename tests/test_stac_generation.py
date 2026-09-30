from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, shape

from metadata.metadata_generation import generate_metadata
from metadata.stac_generation import generate_stac, main, validate_stac
from metadata.stac_validation import validate_document
from node_outputs import stage_profile


def write_json(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def read(root, relative):
    return json.loads((root / relative).read_text())


def snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in (root / "stac").rglob("*.json")}


@pytest.fixture
def node(tmp_path):
    (tmp_path / "config.py").write_text(
        'CITY_NAME = "Milan"\nUSERNAME = "oswm-test"\nREPO_NAME = "milan"\n'
        'METADATA_TIMEZONE = "Europe/Rome"\nSTAC_ENABLED = True\n'
        'STAC_LICENSES = {"processed": "ODbL-1.0", "routing": "ODbL-1.0"}\n'
    )
    write_json(tmp_path, "data/boundaries/infos.json", {"bbox": [-10, -10, 50, 70]})
    write_json(tmp_path, "data/updates/registry.json", {
        "Data Fetching": "2026-09-27T06:00:00Z",
        "Data Pre-Processing": "27/09/2026 10:00:00",
        "Wiki check for keys": "2026-09-29T14:00:00Z",
    })
    processed = tmp_path / "data/processed"
    processed.mkdir(parents=True)
    frame = gpd.GeoDataFrame({"id": [1, 2]}, geometry=[
        LineString([(9.1, 45.4), (9.15, 45.45)]),
        LineString([(9.15, 45.45), (9.2, 45.5)]),
    ], crs="EPSG:4326")
    frame.to_crs(32632).to_parquet(processed / "sidewalks.parquet")
    gpd.GeoDataFrame({"id": []}, geometry=[], crs="EPSG:4326").to_parquet(processed / "crossings.parquet")
    routing = tmp_path / "data/routing"
    routing.mkdir()
    frame.rename_geometry("shape").to_parquet(routing / "network.parquet")
    write_json(tmp_path, "data/routing/metadata.json", {"generated_at": "2026-09-27T09:00:00Z"})
    write_json(tmp_path, "data/routing/profiles.json", {"profiles": {"distance": {}}})
    tiles = tmp_path / "data/tiles"
    tiles.mkdir()
    (tiles / "sidewalks.pmtiles").write_bytes(b"display-pmtiles-test-fixture")
    digest = hashlib.sha256((processed / "sidewalks.parquet").read_bytes()).hexdigest()
    write_json(tmp_path, "data/tiles/tile_generation_report.json", {
        "sidewalks": {"status": "ok", "source_sha256": digest},
    })
    generate_metadata(tmp_path)
    return tmp_path


def test_schema_valid_catalog_uses_product_dates_and_actual_geometries(node):
    summary = generate_stac(node)
    assert summary["collections"] == 2
    assert validate_stac(node) == []
    assert {entry["reason"] for entry in summary["skipped"]} >= {"empty geometry"}
    item = read(node, "stac/processed--sidewalks/current.json")
    routing = read(node, "stac/routing--network/current.json")
    assert item["properties"]["datetime"] == "2026-09-27T08:00:00Z"
    assert routing["properties"]["datetime"] == "2026-09-27T09:00:00Z"
    assert item["properties"]["oswm:source_fetched_at"] == "2026-09-27T06:00:00Z"
    assert item["bbox"] == pytest.approx([9.1, 45.4, 9.2, 45.5])
    assert item["properties"]["oswm:feature_count"] == 2
    assert item["geometry"]["type"] == "Polygon"
    assert shape(item["geometry"]).exterior.is_ccw
    assert item["assets"]["visual"]["roles"] == ["visual"]
    assert "profiles" in routing["assets"]
    assert item["assets"]["data"]["href"] == "https://oswm-test.github.io/milan/data/processed/sidewalks.parquet"
    for path in (node / "stac").rglob("*.json"):
        assert validate_document(json.loads(path.read_text())) == []


def test_static_catalog_links_can_be_walked_without_a_server(node):
    generate_stac(node)
    root = node / "stac/catalog.json"
    catalog = read(node, "stac/catalog.json")
    children = [link for link in catalog["links"] if link["rel"] == "child"]
    assert len(children) == 2
    for link in children:
        collection_path = root.parent / link["href"]
        collection = json.loads(collection_path.read_text())
        item_link = next(link for link in collection["links"] if link["rel"] == "item")
        item = json.loads((collection_path.parent / item_link["href"]).read_text())
        assert item["collection"] == collection["id"]
        assert collection["extent"]["spatial"]["bbox"] == [item["bbox"]]


def test_deterministic_generation_and_pruning_preserve_manual_files(node):
    generate_stac(node)
    initial = snapshot(node)
    generate_stac(node)
    assert snapshot(node) == initial
    write_json(node, "stac/manual.json", {"note": "preserve me"})
    (node / "data/routing/network.parquet").unlink()
    generate_stac(node)
    assert not (node / "stac/routing--network/current.json").exists()
    assert (node / "stac/manual.json").is_file()
    assert validate_stac(node) == []


@pytest.mark.parametrize("report", [{}, {"sidewalks": {"status": "ok", "source_sha256": "old-source"}}])
def test_missing_or_stale_tile_provenance_omits_visual_asset(node, report):
    write_json(node, "data/tiles/tile_generation_report.json", report)
    generate_stac(node)
    item = read(node, "stac/processed--sidewalks/current.json")
    assert "visual" not in item["assets"]


def test_unrelated_maintenance_does_not_advance_dataset_date(node):
    generate_stac(node)
    before = read(node, "stac/processed--sidewalks/current.json")["properties"]["datetime"]
    registry = read(node, "data/updates/registry.json")
    registry["Wiki check for keys"] = "2027-01-01T00:00:00Z"
    write_json(node, "data/updates/registry.json", registry)
    generate_metadata(node)
    generate_stac(node)
    assert read(node, "stac/processed--sidewalks/current.json")["properties"]["datetime"] == before


def test_unknown_product_time_fails_before_replacing_catalog(node):
    generate_stac(node)
    before = snapshot(node)
    registry = read(node, "data/updates/registry.json")
    registry.pop("Data Pre-Processing")
    write_json(node, "data/updates/registry.json", registry)
    with pytest.raises(ValueError, match="timestamp"):
        generate_stac(node)
    assert snapshot(node) == before


def test_modified_data_requires_fresh_metadata_and_preserves_catalog(node):
    generate_stac(node)
    before = snapshot(node)
    path = node / "data/processed/sidewalks.parquet"
    frame = gpd.read_parquet(path)
    frame["changed"] = True
    frame.to_parquet(path)
    with pytest.raises(ValueError, match="Stale metadata"):
        generate_stac(node)
    assert snapshot(node) == before
    assert any("stale asset data" in error for error in validate_stac(node))


def test_point_layer_has_valid_footprint(node):
    path = node / "data/processed/kerbs.parquet"
    gpd.GeoDataFrame(geometry=[Point(9.12, 45.44)], crs="EPSG:4326").to_parquet(path)
    generate_metadata(node)
    generate_stac(node)
    item = read(node, "stac/processed--kerbs/current.json")
    assert item["geometry"]["type"] == "Point"
    assert validate_document(item) == []


def test_missing_collection_link_and_corrupt_dates_are_rejected(node):
    generate_stac(node)
    path = "stac/processed--sidewalks/current.json"
    item = read(node, path)
    broken = copy.deepcopy(item)
    broken["properties"]["datetime"] = "not-a-date"
    assert validate_document(broken)
    (node / "stac/processed--sidewalks/collection.json").unlink()
    assert any("missing STAC link target" in error for error in validate_stac(node))


def test_unmanaged_collision_is_not_overwritten(node):
    write_json(node, "stac/catalog.json", {"owner": "manual"})
    with pytest.raises(ValueError, match="unmanaged"):
        generate_stac(node)
    assert read(node, "stac/catalog.json") == {"owner": "manual"}
    assert len(snapshot(node)) == 1


def test_disabled_pilot_prunes_owned_catalog_only(node):
    generate_stac(node)
    write_json(node, "stac/manual.json", {"note": "manual"})
    with (node / "config.py").open("a") as handle:
        handle.write("\nSTAC_ENABLED = False\n")
    assert main(["--node-root", str(node), "--if-enabled"]) == 0
    assert not (node / "stac/catalog.json").exists()
    assert read(node, "stac/manual.json") == {"note": "manual"}


def test_license_selection_controls_product_families(node):
    with (node / "config.py").open("a") as handle:
        handle.write('\nSTAC_LICENSES = {"processed": "ODbL-1.0"}\n')
    assert generate_stac(node)["collections"] == 1
    with (node / "config.py").open("a") as handle:
        handle.write('\nSTAC_LICENSES = {"processed": {"id": "other"}}\n')
    with pytest.raises(ValueError, match="license URL"):
        generate_stac(node)


def test_cli_and_weekly_staging_include_generated_catalog(node):
    script = Path(__file__).resolve().parents[1] / "metadata/stac_generation.py"
    result = subprocess.run([sys.executable, str(script), "--node-root", str(node)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    checked = subprocess.run([sys.executable, str(script), "--node-root", str(node), "--validate-only"], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    subprocess.run(["git", "init", "-q"], cwd=node, check=True)
    stage_profile(node, "weekly")
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=node, text=True)
    assert "stac/catalog.json" in staged
