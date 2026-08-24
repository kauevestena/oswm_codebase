from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from boundary_acquisition import BoundaryAcquisitionError, resolve_boundary
from node_outputs import (
    REQUIRED_OUTPUTS,
    REQUIRED_PUBLIC_PAGES,
    missing_required,
    VERSIONING_OUTPUTS,
    missing_versioning,
    required_outputs,
    reset_derived,
    reset_initialization,
    stage_profile,
)
from overpass_acquisition import features_from_polygon_with_failover
from pipeline_decision import CODEBASE_REVISION_KEY, decide
from special_updates import synchronize
from time_utils import isoformat_utc, parse_timestamp


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_output_wiper_runs_from_node_root(tmp_path):
    data = tmp_path / "data"
    nested = data / "nested"
    nested.mkdir(parents=True)
    (data / "obsolete.geojson").write_text("{}\n")
    (nested / "product.geojson").write_text("{}\n")
    (data / "sidewalks_versioning.json").write_text("{}\n")

    result = subprocess.run(
        [sys.executable, str(ROOT / "other/wipers/wipe_changed_stuff.py")],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (data / "obsolete.geojson").exists()
    assert (nested / "product.geojson").is_file()
    assert (data / "updates/versioning/sidewalks_versioning.json").is_file()


def test_generated_output_manifest_includes_all_public_entry_pages():
    expected = {
        "index.html",
        "map.html",
        "statistics/index.html",
        "hub/index.html",
        "hub/API/index.html",
        "hub/acquisition/index.html",
        "hub/watcher/index.html",
    }
    assert expected <= set(REQUIRED_PUBLIC_PAGES)
    assert {
        "hub/watcher/feed.xml",
        "hub/watcher/changesets.xml",
        "hub/acquisition/results.json",
    } <= set(REQUIRED_OUTPUTS)


def test_versioning_manifest_requires_every_layer_product(tmp_path):
    assert missing_versioning(tmp_path) == list(VERSIONING_OUTPUTS)
    for relative in VERSIONING_OUTPUTS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n")
    assert missing_versioning(tmp_path) == []


def test_generated_output_manifest_expands_statistics_specs(tmp_path):
    spec = tmp_path / "statistics_specs/sidewalks/width.json"
    spec.parent.mkdir(parents=True)
    spec.write_text("{}\n")
    assert "statistics/sidewalks/width.html" in required_outputs(tmp_path)


def test_available_terrain_rasters_are_required(tmp_path):
    terrain = tmp_path / "data/hazard_analysis"
    terrain.mkdir(parents=True)
    (terrain / "terrain.json").write_text(json.dumps({
        "available": True,
        "profiles": {
            "wheelchair": {
                "path": "data/hazard_analysis/terrain_wheelchair.png"
            }
        },
    }))

    assert "data/hazard_analysis/terrain_wheelchair.png" in required_outputs(tmp_path)
    assert "data/hazard_analysis/terrain_wheelchair.png" in missing_required(tmp_path)


def test_daily_stage_forces_declared_terrain_rasters(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(
        "data/hazard_analysis/terrain_*.png\n", encoding="utf-8"
    )
    terrain = tmp_path / "data/hazard_analysis"
    terrain.mkdir(parents=True)
    (terrain / "terrain_wheelchair.png").write_bytes(b"png")
    (terrain / "terrain.json").write_text(json.dumps({
        "available": True,
        "profiles": {
            "wheelchair": {
                "path": "data/hazard_analysis/terrain_wheelchair.png"
            }
        },
    }))

    stage_profile(tmp_path, "daily")

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=tmp_path,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    assert "data/hazard_analysis/terrain.json" in staged
    assert "data/hazard_analysis/terrain_wheelchair.png" in staged


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_utc_timestamps_are_iso_and_legacy_values_use_node_timezone():
    assert isoformat_utc(datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)) == "2026-01-02T03:04:00Z"
    parsed = parse_timestamp("02/01/2026 03:04:00", "Europe/Rome")
    assert parsed == datetime(2026, 1, 2, 2, 4, tzinfo=timezone.utc)


def test_boundary_lookup_uses_exact_relation_and_keeps_metadata():
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse([
            {
                "osm_id": 44915,
                "class": "boundary",
                "type": "administrative",
                "importance": 0.8,
                "geojson": {"type": "Polygon", "coordinates": []},
            }
        ])

    geometry, metadata = resolve_boundary(
        "Milan, Italy", relation_id=44915, request_get=get, sleep=lambda _: None
    )
    assert calls[0][0].endswith("/lookup")
    assert calls[0][1]["params"]["osm_ids"] == "R44915"
    assert geometry["type"] == "Polygon"
    assert metadata["requested_relation_id"] == 44915
    assert "geojson" not in metadata


def test_boundary_lookup_rejects_non_polygon_relation():
    with pytest.raises(BoundaryAcquisitionError):
        resolve_boundary(
            "Milan, Italy",
            relation_id=44915,
            attempts=1,
            request_get=lambda *_args, **_kwargs: FakeResponse([
                {"osm_id": 44915, "geojson": {"type": "Point", "coordinates": [0, 0]}}
            ]),
            sleep=lambda _: None,
        )


def test_overpass_failover_is_bounded_and_restores_settings():
    calls = []
    fake = SimpleNamespace(settings=SimpleNamespace(overpass_url="original"))

    def fetch(_polygon, _tags):
        calls.append(fake.settings.overpass_url)
        if fake.settings.overpass_url == "one":
            raise RuntimeError("provider unavailable")
        return "features"

    fake.features_from_polygon = fetch
    result = features_from_polygon_with_failover(
        fake,
        object(),
        {},
        endpoints=("one", "two"),
        attempts_per_endpoint=2,
        backoff_seconds=0,
        sleep=lambda _: None,
    )
    assert result == "features"
    assert calls == ["one", "one", "two"]
    assert fake.settings.overpass_url == "original"


def test_derived_reset_removes_stale_products_but_preserves_weekly_dictionary(tmp_path):
    (tmp_path / "config.py").write_text('CITY_NAME = "Test"\n')
    (tmp_path / "oswm_codebase").mkdir()
    (tmp_path / "data/tiles").mkdir(parents=True)
    (tmp_path / "data/tiles/obsolete.pmtiles").write_text("old")
    (tmp_path / "quality_check").mkdir()
    (tmp_path / "quality_check/index.json").write_text("old")
    (tmp_path / "quality_check/keys_without_wiki.json").write_text("{}\n")
    removed = reset_derived(tmp_path)
    assert "data/tiles" in removed
    assert not (tmp_path / "data/tiles/obsolete.pmtiles").exists()
    assert not (tmp_path / "quality_check/index.json").exists()
    assert (tmp_path / "quality_check/keys_without_wiki.json").read_text() == "{}\n"


def test_initialization_reset_is_dry_run_first_and_recreates_empty_registry(tmp_path):
    (tmp_path / "config.py").write_text('CITY_NAME = "Test"\n')
    (tmp_path / "oswm_codebase").mkdir()
    (tmp_path / "data/raw").mkdir(parents=True)
    (tmp_path / "data/raw/curitiba.parquet").write_text("old")
    report = reset_initialization(tmp_path, apply=False)
    assert report["mode"] == "dry-run"
    assert (tmp_path / "data/raw/curitiba.parquet").exists()
    reset_initialization(tmp_path, apply=True)
    assert json.loads((tmp_path / "data/updates/registry.json").read_text()) == {}


def test_special_update_renders_crons_and_preserves_node_workflows(tmp_path):
    core = tmp_path / "core"
    node = tmp_path / "node"
    (core / "workflows").mkdir(parents=True)
    (node / ".github/workflows").mkdir(parents=True)
    (core / "workflows/manifest.json").write_text(json.dumps({
        "managed": ["workflows/data_daily_updating.yml", "workflows/weekly.yml"],
        "retired": ["workflows/manual_stash.yml"],
    }))
    (core / "workflows/data_daily_updating.yml").write_text('cron: "__OSWM_DAILY_CRON__"\n')
    (core / "workflows/weekly.yml").write_text('cron: "__OSWM_WEEKLY_CRON__"\n')
    (node / "config.py").write_text(
        'NODE_DAILY_CRON = "17 3 * * *"\nNODE_WEEKLY_CRON = "43 4 * * 0"\n'
    )
    custom = node / ".github/workflows/node_launch_readiness.yml"
    custom.write_text("custom\n")
    retired = node / ".github/workflows/manual_stash.yml"
    retired.write_text("old\n")
    synchronize(node, core)
    assert "17 3 * * *" in (node / ".github/workflows/data_daily_updating.yml").read_text()
    assert "43 4 * * 0" in (node / ".github/workflows/weekly.yml").read_text()
    assert custom.read_text() == "custom\n"
    assert not retired.exists()


def _make_complete_node(root: Path, revision: str) -> None:
    from node_outputs import REQUIRED_OUTPUTS

    for relative in REQUIRED_OUTPUTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == "data/hazard_analysis/terrain.json":
            path.write_text(json.dumps({"available": False}))
        else:
            path.write_text("ready\n")
    registry = root / "data/updates/registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({CODEBASE_REVISION_KEY: revision}))


def test_pipeline_decision_distinguishes_cold_skip_and_core_rebuild(tmp_path, monkeypatch):
    monkeypatch.setenv("OSWM_CODEBASE_REVISION", "new")
    assert decide(tmp_path, watcher_status=0)["mode"] == "generate"
    _make_complete_node(tmp_path, "new")
    assert decide(tmp_path, watcher_status=0)["mode"] == "skip"
    (tmp_path / "data/updates/registry.json").write_text(
        json.dumps({CODEBASE_REVISION_KEY: "old"})
    )
    decision = decide(tmp_path, watcher_status=0)
    assert decision["mode"] == "rebuild"
    assert decision["reason"] == "codebase_revision_changed"


def test_force_regeneration_overrides_no_change(tmp_path, monkeypatch):
    monkeypatch.setenv("OSWM_CODEBASE_REVISION", "same")
    _make_complete_node(tmp_path, "same")
    assert decide(tmp_path, watcher_status=0, force=True)["mode"] == "generate"


def test_workflow_contracts_are_parseable_scoped_and_serialized():
    workflow_paths = sorted((ROOT / "workflows").glob("*.yml"))
    assert workflow_paths
    combined = "\n".join(path.read_text() for path in workflow_paths)
    for path in workflow_paths:
        assert yaml.safe_load(path.read_text()) is not None
    assert "git add .\n" not in combined
    assert "git add -A" not in combined
    assert "git commit --amend" not in combined
    assert "git push --force" not in combined
    for name in (
        "setup.yml", "data_daily_updating.yml", "weekly.yml",
        "special_updates.yml", "customizable.yml", "update_codebase.yml",
    ):
        assert "group: oswm-node-writer-${{ github.repository }}" in (
            ROOT / "workflows" / name
        ).read_text()
    assert "actions/deploy-pages@v4" in (ROOT / "workflows/pages.yml").read_text()
    assert "other/auxiliary_scripts/validate_tiles.py" in (
        ROOT / "workflows/data_daily_updating.yml"
    ).read_text()
    manifest = json.loads((ROOT / "workflows/manifest.json").read_text())
    assert "workflows/deploy_pages.yml" in manifest["retired"]


def test_tile_generation_limit_matches_managed_workflow_guard():
    assert "MAX_TILE_FILESIZE_BYTES = 95 * 1024 * 1024" in (
        ROOT / "constants.py"
    ).read_text()
    for name in (
        "setup.yml",
        "data_daily_updating.yml",
        "weekly.yml",
        "customizable.yml",
    ):
        assert "validate-sizes --max-mib 95" in (
            ROOT / "workflows" / name
        ).read_text()


def test_runtime_lock_is_exact_and_reproducible():
    requirements = [
        line.strip()
        for line in (ROOT / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#") and not line.startswith(" ")
    ]
    assert requirements
    assert all("==" in item or ";" in item for item in requirements)
