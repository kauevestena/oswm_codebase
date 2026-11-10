"""Exercise preprocessing with the sparse tag schema found in new small nodes."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import geopandas as gpd
import pytest
from shapely.geometry import LineString


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("with_aliases", [False, True])
def test_preprocessing_handles_missing_optional_tags(tmp_path, with_aliases):
    core = tmp_path / "oswm_codebase"
    for relative in (
        "constants.py", "functions.py", "boundary_acquisition.py",
        "time_utils.py", "filtering_adapting_data.py",
    ):
        target = core / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    shutil.copy2(ROOT / "other/templates/config.py", tmp_path / "config.py")

    sidewalks = [
        {"id": index + 1, "element": "way", "highway": "footway",
         "footway": "sidewalk",
         "geometry": LineString([(9.420 + index * .001, 45.634),
                                 (9.421 + index * .001, 45.634)])}
        for index in range(3)
    ]
    if with_aliases:
        for row, surface, smoothness in zip(
            sidewalks,
            ["Petit_Pavê", "asphalt", None],
            ["concrete:plates", "good", None],
        ):
            row.update(surface=surface, smoothness=smoothness)

    records = {
        "sidewalks": sidewalks,
        "crossings": [
            {"id": 10, "element": "way", "highway": "footway",
             "footway": "crossing",
             "geometry": LineString([(9.421, 45.63399), (9.421, 45.63401)])},
        ],
        "kerbs": [],
        "other_footways": [
            {"id": 20, "element": "way", "highway": "path",
             "geometry": LineString([(9.423, 45.634), (9.4232, 45.6342)])},
        ],
    }
    for category, rows in records.items():
        frame = (gpd.GeoDataFrame(rows, crs="EPSG:4326") if rows else
                 gpd.GeoDataFrame(columns=["id", "element", "geometry"], crs="EPSG:4326"))
        target = tmp_path / f"data/raw/{category}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(target)

    result = subprocess.run(
        [sys.executable, str(core / "filtering_adapting_data.py")],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(core)},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    for category, rows in records.items():
        processed = gpd.read_parquet(tmp_path / f"data/processed/{category}.parquet")
        assert len(processed) == len(rows)
        if rows:
            assert processed.crs.to_epsg() == 4326
            assert processed["id"].tolist() == [row["id"] for row in rows]
            assert processed["element"].tolist() == ["way"] * len(rows)

    processed = gpd.read_parquet(tmp_path / "data/processed/sidewalks.parquet")
    keys = json.loads((tmp_path / "quality_check/feature_keys.json").read_text())
    if with_aliases:
        assert processed["surface"].tolist() == ["sett", "asphalt", "?"]
        assert processed["smoothness"].tolist() == ["?", "good", "?"]
    else:
        assert "surface" not in processed and "smoothness" not in processed
        assert "surface" not in keys["sidewalks"] and "smoothness" not in keys["sidewalks"]
    assert (tmp_path / "data/updates/index.html").is_file()
