from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from node_outputs import REQUIRED_OUTPUTS
from pipeline_decision import CODEBASE_REVISION_KEY, RAW_OUTPUTS
from runtime_assets import COPY_TREES, SNAPSHOT_FILES, publish_runtime
from runtime_validation import Assets, CSS_URL


ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPTS = (
    "runtime_assets.py",
    "patch_readme_homepage.py",
    "build_provenance.py",
    "datahub/watcher/watcher_lib.py",
    "datahub/acquisition/generate_acquisition.py",
    "getting_data.py",
    "getting_feature_versioning_data.py",
    "filtering_adapting_data.py",
    "generation/vec_tiles_gen.py",
    "generation/raster_basemap_gen.py",
    "generation/vrt.py",
    "webmap/snapshot/generate_snapshot_summary.py",
    "webmap/create_webmap_new.py",
    "data_quality/tag_values_checking.py",
    "data_quality/quality_check_compiling.py",
    "data_quality/completeness/completeness_runner.py",
    "data_quality/external_qc.py",
    "dashboard/statistics_generation.py",
    "generation/routing_demo_gen.py",
    "generation/routing_tiles_gen.py",
    "generation/hazard_tiles_gen.py",
    "metadata/metadata_generation.py",
    "metadata/stac_generation.py",
    "datahub/API/generate_api.py",
    "datahub/datahub_index_generator.py",
)

LEGACY_HOMEPAGE_PATHS = (
    "assets/branding/favicon_homepage.png",
    "assets/branding/logos/project_logo_100px.png",
    "assets/homepage/oswm_webmap_img.png",
    "assets/homepage/oswm_route_img.png",
    "assets/homepage/oswm_statistics_img.png",
    "assets/homepage/oswm_quality_check_img.png",
    "assets/homepage/oswm_datahub_img.png",
    "assets/homepage/oswm_hazard_img.png",
    "routing/routing_demo.html",
    "hazard_analysis/hazard_analysis.html",
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
if relative == os.environ.get("FAIL_STEP"):
    raise SystemExit(1)
if relative == "runtime_assets.py":
    path = root / "oswm_runtime/runtime_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"runtime_contract": 1}\\n')
if relative == "build_provenance.py":
    path = root / "oswm-build.json"
    path.write_text('{"core": {"sha": "fixture"}}\\n')
if relative == "datahub/watcher/watcher_lib.py":
    with (root / "watcher_calls.log").open("a") as handle:
        handle.write(" ".join(sys.argv[1:]) + "\\n")
    if "--render-only" in sys.argv or "--render-current" in sys.argv:
        raise SystemExit(0)
    raise SystemExit(int(os.environ.get("WATCHER_EXIT", "0")))
if relative == "getting_data.py":
    for item in %r:
        path = root / item
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("raw\\n")
if relative == "filtering_adapting_data.py":
    for item in %r:
        if item.startswith("data/raw/") or item == "data/boundaries/polygon.geojson":
            continue
        path = root / item
        path.parent.mkdir(parents=True, exist_ok=True)
        if item == "data/hazard_analysis/terrain.json":
            path.write_text('{"available": false}\\n')
        else:
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
            if relative == "data/hazard_analysis/terrain.json":
                path.write_text('{"available": false}\n')
            else:
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
    versioning = tmp_path / "data/updates/versioning"
    versioning.mkdir(parents=True)
    (versioning / "index.json").write_text("{}\n")
    result = _run(tmp_path, revision="new", watcher_exit=1)
    assert result.returncode == 0, result.stdout + result.stderr
    events = (tmp_path / "events.log").read_text()
    assert "getting_data.py" in events
    assert "getting_feature_versioning_data.py" in events
    assert "filtering_adapting_data.py" in events
    assert events.count("datahub/watcher/watcher_lib.py") == 2


def test_weekly_runner_regenerates_versioning_consumers():
    weekly = (ROOT / "runners/weekly.sh").read_text()
    versioning = weekly.index("getting_feature_versioning_data.py")
    filtering = weekly.index("filtering_adapting_data.py")
    quality = weekly.index("quality_check_compiling.py")
    statistics = weekly.index("statistics_generation.py")
    metadata = weekly.index("metadata_generation.py")
    assert versioning < filtering < quality < statistics < metadata


def test_no_change_runner_skips_osm_dependent_generation(tmp_path):
    _prepare_fixture(tmp_path, complete=True, recorded_revision="same")
    result = _run(tmp_path, revision="same", watcher_exit=0)
    assert result.returncode == 0, result.stdout + result.stderr
    events = (tmp_path / "events.log").read_text()
    assert "getting_data.py" not in events
    assert "filtering_adapting_data.py" not in events
    assert "metadata/metadata_generation.py" in events
    assert events.index("metadata/metadata_generation.py") < events.index("metadata/stac_generation.py") < events.index("datahub/API/generate_api.py")
    assert events.count("datahub/watcher/watcher_lib.py") == 1


def test_stac_failure_prevents_pipeline_success(tmp_path, monkeypatch):
    _prepare_fixture(tmp_path, complete=True, recorded_revision="same")
    monkeypatch.setenv("FAIL_STEP", "metadata/stac_generation.py")
    result = _run(tmp_path, revision="same")
    assert result.returncode != 0
    assert "stac_generation" in (tmp_path / "data/updates/pipeline_failures.txt").read_text()
    assert "Pipeline Success" not in json.loads((tmp_path / "data/updates/registry.json").read_text())


@pytest.mark.parametrize("complete", [False, True], ids=["generate", "skip"])
def test_homepage_patch_failure_prevents_pipeline_success(tmp_path, monkeypatch, complete):
    _prepare_fixture(tmp_path, complete=complete, recorded_revision="same")
    monkeypatch.setenv("FAIL_STEP", "patch_readme_homepage.py")

    result = _run(tmp_path, revision="same")

    assert result.returncode != 0
    assert "patch_readme_homepage" in (tmp_path / "data/updates/pipeline_failures.txt").read_text()
    registry = json.loads((tmp_path / "data/updates/registry.json").read_text())
    assert "Pipeline Success" not in registry


def _prepare_homepage_fixture(root: Path, mode: str) -> None:
    _prepare_fixture(
        root,
        complete=mode != "generate",
        recorded_revision="old" if mode == "rebuild" else "same",
    )
    core = root / "oswm_codebase"
    for relative in (
        "patch_readme_homepage.py", "functions.py", "constants.py", "modules_info.py",
        "boundary_acquisition.py", "branding.py", "homepage_links.py",
        "runtime_assets.py", "runtime_validation.py",
    ):
        shutil.copy2(ROOT / relative, core / relative)
    for source, _ in COPY_TREES:
        shutil.copytree(ROOT / source, core / source)
    for relative in (
        "webmap/oswm_legend_control.js",
        *("webmap/snapshot/" + name for name in SNAPSHOT_FILES),
        *(path.relative_to(ROOT).as_posix() for path in (ROOT / "webmap/theme_charts").glob("*.js")),
    ):
        destination = core / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)

    configuration = (ROOT / "other/templates/config.py").read_text()
    (root / "config.py").write_text(
        configuration + '\nCITY_NAME = "Hiroshima, Japan"\n'
        'USERNAME = "opensidewalkmap"\nREPO_NAME = "hiroshima"\n'
    )
    # Keep the failed node's homepage verbatim, including all ten legacy URLs.
    # Source: https://github.com/opensidewalkmap/hiroshima/blob/b22bf2c/index.html
    shutil.copy2(ROOT / "tests/fixtures/hiroshima-index.html", root / "index.html")
    (root / "README.md").write_text("# <CITYNAME>Hiroshima, Japan<CITYNAME> node\n")

    # Data-generator substitutes must leave homepage and runtime publication to
    # their real scripts; these are otherwise part of the output-contract stub.
    filtering = core / "filtering_adapting_data.py"
    data_outputs = tuple(path for path in REQUIRED_OUTPUTS if path not in {
        "index.html", "oswm_runtime/runtime_manifest.json",
    })
    filtering.write_text(
        filtering.read_text().replace(repr(REQUIRED_OUTPUTS), repr(data_outputs))
    )
    if mode == "skip":
        publish_runtime(root, core)


@pytest.mark.parametrize("mode", ["generate", "rebuild", "skip"])
def test_daily_runner_repairs_legacy_hiroshima_homepage(tmp_path, mode):
    _prepare_homepage_fixture(tmp_path, mode)
    homepage = tmp_path / "index.html"
    parser = Assets()
    parser.feed(homepage.read_text())
    legacy_urls = {"oswm_codebase/" + path for path in LEGACY_HOMEPAGE_PATHS}
    assert set(parser.urls) & legacy_urls == legacy_urls

    result = _run(tmp_path, revision="same")

    assert result.returncode == 0, result.stdout + result.stderr
    decision = json.loads((tmp_path / "data/updates/pipeline_decision.json").read_text())
    assert decision["mode"] == mode
    parser = Assets()
    parser.feed(homepage.read_text())
    assert not (set(parser.urls) & legacy_urls)
    for path in LEGACY_HOMEPAGE_PATHS:
        runtime_url = "oswm_runtime/" + path
        assert runtime_url in parser.urls
        assert (tmp_path / runtime_url).is_file()
    background_url = "oswm_runtime/assets/homepage/sidewalk_background2.jpg"
    assert background_url in CSS_URL.findall("\n".join(parser.code))
    assert (tmp_path / background_url).is_file()

    # Check the publishable tree after discarding the ephemeral build engine.
    shutil.rmtree(tmp_path / "oswm_codebase")
    validation = subprocess.run(
        [sys.executable, str(ROOT / "runtime_validation.py"), "--root", str(tmp_path)],
        text=True, capture_output=True, timeout=30,
    )
    assert validation.returncode == 0, validation.stdout + validation.stderr
    assert json.loads(validation.stdout)["runtime_errors"] == []


def test_missing_basemaps_force_rebuild_during_no_change_cycle(tmp_path):
    _prepare_fixture(tmp_path, complete=True, recorded_revision="same")
    for relative in (
        "data/basemaps/light.pmtiles",
        "data/basemaps/dark.pmtiles",
        "data/basemaps/generation_report.json",
    ):
        (tmp_path / relative).unlink()

    result = _run(tmp_path, revision="same", watcher_exit=0)

    assert result.returncode == 0, result.stdout + result.stderr
    decision = json.loads(
        (tmp_path / "data/updates/pipeline_decision.json").read_text()
    )
    events = (tmp_path / "events.log").read_text()
    assert decision["mode"] == "rebuild"
    assert decision["reason"] == "derived_outputs_missing"
    assert "generation/raster_basemap_gen.py" in events
    assert "webmap/create_webmap_new.py" in events


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


def test_lima_forced_rebuild_preserves_acquisition_without_refetching_raw_data(tmp_path, monkeypatch):
    _prepare_fixture(tmp_path, complete=True, recorded_revision="same")
    # Lima's state at the migration run: complete raw inputs and an earlier
    # successful Overpass acquisition. Rebuilding must not redownload them.
    registry_path = tmp_path / "data/updates/registry.json"
    registry = json.loads(registry_path.read_text())
    registry["Data Fetching"] = "2026-10-13T13:21:12Z"
    registry_path.write_text(json.dumps(registry))
    acquisition = tmp_path / "data/updates/acquisition.json"
    acquisition.write_text(json.dumps({
        "provider": "overpass", "acquired_at": "2026-10-13T13:21:12Z",
    }))
    preserved = {path: (tmp_path / path).read_bytes() for path in RAW_OUTPUTS}
    preserved["data/updates/acquisition.json"] = acquisition.read_bytes()
    # Any accidental acquisition would fail just as it did in the live run.
    monkeypatch.setenv("FAIL_STEP", "getting_data.py")

    result = _run(tmp_path, revision="same", watcher_exit=0, force=True)

    assert result.returncode == 0, result.stdout + result.stderr
    decision = json.loads((tmp_path / "data/updates/pipeline_decision.json").read_text())
    assert (decision["mode"], decision["reason"]) == ("rebuild", "forced")
    events = (tmp_path / "events.log").read_text().splitlines()
    assert "getting_data.py" not in events
    for step in ("runtime_assets.py", "filtering_adapting_data.py",
                 "generation/routing_tiles_gen.py", "generation/hazard_tiles_gen.py",
                 "datahub/acquisition/generate_acquisition.py", "build_provenance.py"):
        assert step in events
    assert (tmp_path / "watcher_calls.log").read_text().splitlines() == ["", "--render-only"]
    assert all((tmp_path / path).read_bytes() == content for path, content in preserved.items())
    registry = json.loads(registry_path.read_text())
    assert registry["Data Fetching"] == "2026-10-13T13:21:12Z"
    assert registry[CODEBASE_REVISION_KEY] == "same"
    assert registry["Pipeline Success"]


@pytest.mark.parametrize("missing_raw", RAW_OUTPUTS)
def test_forced_rebuild_requires_acquisition_when_any_raw_input_is_missing(tmp_path, monkeypatch, missing_raw):
    _prepare_fixture(tmp_path, complete=True, recorded_revision="same")
    (tmp_path / missing_raw).unlink()
    monkeypatch.setenv("FAIL_STEP", "getting_data.py")

    result = _run(tmp_path, revision="same", watcher_exit=0, force=True)

    assert result.returncode != 0
    assert "getting_data" in (tmp_path / "data/updates/pipeline_failures.txt").read_text()
    assert "getting_data.py" in (tmp_path / "events.log").read_text().splitlines()
    assert "Pipeline Success" not in json.loads((tmp_path / "data/updates/registry.json").read_text())
    assert "--render-current" not in (tmp_path / "watcher_calls.log").read_text()


@pytest.mark.parametrize("watcher_exit", [1, 2])
def test_forced_run_still_acquires_changes_or_inconclusive_data(tmp_path, watcher_exit):
    _prepare_fixture(tmp_path, complete=True, recorded_revision="same")

    result = _run(tmp_path, revision="same", watcher_exit=watcher_exit, force=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "getting_data.py" in (tmp_path / "events.log").read_text().splitlines()
    assert (tmp_path / "watcher_calls.log").read_text().splitlines() == ["", "--render-current"]


def test_refresh_renders_current_watcher_only_after_step_failure_guard():
    daily = (ROOT / "runners/daily.sh").read_text()
    failure_guard = daily.index('if [ "${#FAILED_STEPS[@]}" -ne 0 ]')
    render_current = daily.index("watcher_lib.py --render-current")
    require = daily.index("node_outputs.py --root . require", render_current)
    assert failure_guard < render_current < require


def test_watcher_exposes_comparable_changeset_scopes():
    watcher = (ROOT / "datahub/watcher/watcher_lib.py").read_text()
    assert '"changeset_changes_count": changes_count' in watcher
    assert '"oswm_changes_count": oswm_changes_count' in watcher
    assert "Whole changeset" in watcher
    assert "OSWM edits in node (Add/Mod/Del)" in watcher
