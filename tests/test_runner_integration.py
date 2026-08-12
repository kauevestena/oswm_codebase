from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from node_outputs import REQUIRED_OUTPUTS
from pipeline_decision import CODEBASE_REVISION_KEY


ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPTS = (
    "datahub/watcher/watcher_lib.py",
    "datahub/acquisition/generate_acquisition.py",
    "getting_data.py",
    "getting_feature_versioning_data.py",
    "filtering_adapting_data.py",
    "generation/vec_tiles_gen.py",
    "generation/vrt.py",
    "webmap/snapshot/generate_snapshot_summary.py",
    "webmap/create_webmap_new.py",
    "data_quality/tag_values_checking.py",
    "data_quality/quality_check_compiling.py",
    "data_quality/completeness/completeness_runner.py",
    "data_quality/external_qc.py",
    "dashboard/statistics_generation.py",
    "generation/routing_demo_gen.py",
    "generation/hazard_tiles_gen.py",
    "metadata/metadata_generation.py",
    "datahub/API/generate_api.py",
    "datahub/datahub_index_generator.py",
)


def _prepare_fixture(root: Path, *, complete: bool, recorded_revision: str | None) -> None:
    core = root / "oswm_codebase"
    (root / "config.py").write_text('CITY_NAME = "Fixture"\n')
    for relative in ("runners/daily.sh", "pipeline_decision.py", "node_outputs.py", "time_utils.py"):
        destination = core / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)

    stub = '''from pathlib import Path
import os, sys
root = Path.cwd()
relative = Path(__file__).resolve().relative_to(root / "oswm_codebase").as_posix()
with (root / "events.log").open("a") as handle:
    handle.write(relative + "\\n")
if relative == "datahub/watcher/watcher_lib.py":
    if "--render-only" in sys.argv:
        raise SystemExit(0)
    raise SystemExit(int(os.environ.get("WATCHER_EXIT", "0")))
if relative == "getting_data.py":
    for item in %r:
        path = root / item
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("raw\\n")
if relative == "filtering_adapting_data.py":
    for item in %r:
        path = root / item
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ready\\n")
''' % (
        (
            "data/raw/sidewalks.parquet", "data/raw/crossings.parquet",
            "data/raw/kerbs.parquet", "data/raw/other_footways.parquet",
            "data/boundaries/polygon.geojson",
        ),
        REQUIRED_OUTPUTS,
    )
    for relative in RUNNER_SCRIPTS:
        path = core / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stub, encoding="utf-8")

    if complete:
        for relative in REQUIRED_OUTPUTS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("ready\n")
    registry = root / "data/updates/registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps({CODEBASE_REVISION_KEY: recorded_revision} if recorded_revision else {})
    )


def _run(root: Path, *, revision: str, watcher_exit: int = 0, force: bool = False):
    environment = os.environ.copy()
    environment.update({
        "PYTHON": sys.executable,
        "OSWM_CODEBASE_REVISION": revision,
        "WATCHER_EXIT": str(watcher_exit),
        "OSWM_FORCE_REGEN": "true" if force else "false",
    })
    return subprocess.run(
        ["bash", "oswm_codebase/runners/daily.sh"],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_cold_runner_fetches_then_generates_complete_contract(tmp_path):
    _prepare_fixture(tmp_path, complete=False, recorded_revision=None)
    result = _run(tmp_path, revision="new", watcher_exit=1)
    assert result.returncode == 0, result.stdout + result.stderr
    events = (tmp_path / "events.log").read_text()
    assert "getting_data.py" in events
    assert "filtering_adapting_data.py" in events
    assert events.count("datahub/watcher/watcher_lib.py") == 2


def test_no_change_runner_skips_osm_dependent_generation(tmp_path):
    _prepare_fixture(tmp_path, complete=True, recorded_revision="same")
    result = _run(tmp_path, revision="same", watcher_exit=0)
    assert result.returncode == 0, result.stdout + result.stderr
    events = (tmp_path / "events.log").read_text()
    assert "getting_data.py" not in events
    assert "filtering_adapting_data.py" not in events
    assert "metadata/metadata_generation.py" in events
    assert events.count("datahub/watcher/watcher_lib.py") == 1


def test_codebase_change_rebuilds_derived_products_without_redownload(tmp_path):
    _prepare_fixture(tmp_path, complete=True, recorded_revision="old")
    result = _run(tmp_path, revision="new", watcher_exit=0)
    assert result.returncode == 0, result.stdout + result.stderr
    events = (tmp_path / "events.log").read_text()
    assert "getting_data.py" not in events
    assert "filtering_adapting_data.py" in events
    assert events.count("datahub/watcher/watcher_lib.py") == 2
    registry = json.loads((tmp_path / "data/updates/registry.json").read_text())
    assert registry[CODEBASE_REVISION_KEY] == "new"
