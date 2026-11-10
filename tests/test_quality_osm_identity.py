"""Compile real quality reports without acquisition or an existing node checkout."""

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from bs4 import BeautifulSoup
import geopandas as gpd
from shapely.geometry import LineString, Point, box, mapping


ROOT = Path(__file__).resolve().parents[1]


def test_improper_geometry_reports_keep_source_osm_identity(tmp_path):
    core = tmp_path / "oswm_codebase"
    for relative in (
        "constants.py", "functions.py", "boundary_acquisition.py", "time_utils.py",
        "branding.py", "assets/branding/manifest.json", "data_quality/dq_funcs.py",
        "data_quality/quality_dicts.py", "data_quality/quality_check_compiling.py",
        "data_quality/temporal_lookup.py",
    ):
        target = core / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    shutil.copy2(ROOT / "other/templates/config.py", tmp_path / "config.py")

    def write_json(relative, value):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    boundary = box(9.1, 45.4, 9.3, 45.6)
    write_json("data/boundaries/infos.json", {
        "center": [9.2, 45.5], "bbox": list(boundary.bounds),
    })
    write_json("data/boundaries/polygon.geojson", mapping(boundary))
    write_json("quality_check/feature_keys.json", {})

    # Milan regression IDs, with small synthetic geometries. A polygon way is
    # still a way; a polygon relation is still a relation. Neither is a node.
    frames = {
        "sidewalks": [
            {"element": "node", "id": 1483978639, "geometry": Point(9.17, 45.42)},
            {"element": "way", "id": 257167910, "geometry": box(9.25, 45.44, 9.26, 45.45)},
            {"element": "relation", "id": 900000001, "geometry": box(9.18, 45.47, 9.19, 45.48)},
        ],
        "kerbs": [
            {"element": "way", "id": 23156005,
             "geometry": LineString([(9.19, 45.50), (9.20, 45.51)])},
        ],
        "crossings": [
            {"element": "node", "id": 900000002, "geometry": Point(9.21, 45.49)},
        ],
        "other_footways": [],
    }
    expected = {}
    for category, records in frames.items():
        frame = gpd.GeoDataFrame(
            records, columns=["element", "id", "geometry"], crs="EPSG:4326",
        )
        for relative in (f"data/raw/{category}.parquet", f"data/processed/{category}.parquet"):
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(target)
        if records:
            target = tmp_path / f"data/data_quality/improper_geoms/{category}_improper_geoms.parquet"
            target.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(target)
            expected[category] = {row["id"]: row["element"] for row in records}

    for folder in ("disjointed", "crossings_lacking_kerbs", "kerb_on_top_of_non_crossing"):
        (tmp_path / "data/data_quality" / folder).mkdir(parents=True)

    result = subprocess.run(
        [sys.executable, str(core / "data_quality/quality_check_compiling.py")],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(core)},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    for category, identities in expected.items():
        report = BeautifulSoup((
            tmp_path / f"quality_check/pages/{category}/improper_geometries.html"
        ).read_text(encoding="utf-8"), "html.parser")
        links = {link.get("href") for link in report.find_all("a")}
        query = report.find("textarea", id="op-query-text").get_text()
        with (tmp_path / f"quality_check/tables/{category}/improper_geometries.csv").open() as handle:
            csv_rows = list(csv.DictReader(handle))
        json_rows = json.loads((
            tmp_path / f"quality_check/json/{category}/improper_geometries.json"
        ).read_text())
        assert {int(row["osm_id"]): row["feat_type"] for row in csv_rows} == identities
        assert {row["osm_id"]: row["feat_type"] for row in json_rows} == identities

        map_data = json.loads((
            tmp_path / f"quality_check/maps/{category}/improper_geometries.geojson"
        ).read_text())
        map_features = {feature["properties"]["id"]: feature for feature in map_data["features"]}
        assert set(map_features) == set(identities)
        for identifier, element in identities.items():
            url = f"https://www.openstreetmap.org/{element}/{identifier}"
            assert url in links
            assert any(f"editor=id&{element}={identifier}#map=" in link for link in links)
            assert str(identifier) in next(
                line for line in query.splitlines() if line.strip().startswith(f"{element}(")
            )
            properties = map_features[identifier]["properties"]
            assert properties["feat_type"] == element
            assert properties["osm_url"] == url
            assert f"editor=id&{element}={identifier}#map=" in properties["id_url"]
            assert f"objects={element[0]}{identifier}" in properties["josm_url"]
