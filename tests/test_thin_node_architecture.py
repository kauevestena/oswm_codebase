from __future__ import annotations

import json
from pathlib import Path

import yaml

from build_provenance import write_manifest
from runtime_assets import publish_runtime


ROOT = Path(__file__).resolve().parents[1]
REVISION = "a" * 40


def test_runtime_bundle_is_self_contained(tmp_path):
    manifest = publish_runtime(tmp_path, ROOT)

    assert manifest["runtime_contract"] == 1
    assert (tmp_path / "oswm_runtime/assets/branding/branding.js").is_file()
    assert (tmp_path / "oswm_runtime/webmap/snapshot/snapshot_control.js").is_file()
    assert (tmp_path / "oswm_runtime/routing/routing_demo.html").is_file()
    assert (tmp_path / "oswm_runtime/hazard_analysis/hazard_analysis.html").is_file()

    webmap = (ROOT / "webmap/webmap_base.html").read_text(encoding="utf-8")
    assert "oswm_runtime/assets/" in webmap
    assert "oswm_runtime/webmap/snapshot/" in webmap
    assert "oswm_codebase/assets/" not in webmap


def test_build_manifest_records_exact_core_and_product_state(tmp_path, monkeypatch):
    (tmp_path / "config.py").write_text('CITY_NAME = "Fixture"\n', encoding="utf-8")
    runtime = tmp_path / "oswm_runtime"
    runtime.mkdir()
    (runtime / "runtime_manifest.json").write_text(
        json.dumps({"runtime_contract": 1}), encoding="utf-8"
    )
    (tmp_path / "map.html").write_text("map\n", encoding="utf-8")
    (tmp_path / "webmap_params.json").write_text("{}\n", encoding="utf-8")
    for relative in (
        "data/tiles/tile_generation_report.json",
        "data/routing/metadata.json",
        "data/hazard_analysis/metadata.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    report = tmp_path / "data/basemaps/generation_report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "renderer_version": 3,
                "style_basis": {
                    "light": "OpenFreeMap Positron",
                    "dark": "OpenFreeMap Dark Matter",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OSWM_CORE_REVISION", REVISION)
    payload = write_manifest(tmp_path, mode="rebuild")

    assert payload["core"]["sha"] == REVISION
    assert payload["build_contract"] == 1
    assert payload["products"]["webmap"] is True
    assert payload["products"]["basemaps"]["renderer_version"] == 3
    assert json.loads((tmp_path / "oswm-build.json").read_text())["core"]["sha"] == REVISION


def test_reusable_builder_checks_out_core_ephemerally():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/node_build.yml").read_text(encoding="utf-8")
    )
    assert workflow is not None
    source = (ROOT / ".github/workflows/node_build.yml").read_text(encoding="utf-8")
    assert "repository: kauevestena/oswm_codebase" in source
    assert "path: oswm_codebase" in source
    assert "submodules: false" in source
    assert "OSWM_CORE_REVISION=$(git -C oswm_codebase rev-parse HEAD)" in source
    assert 'OSWM_THIN_NODE: "1"' in source
    assert "python oswm_codebase/node_outputs.py --root . require" in source

    setup = (ROOT / "runners/setup.sh").read_text(encoding="utf-8")
    assert "OSWM_THIN_NODE" in setup
    assert '*) "$PYTHON_BIN" oswm_codebase/special_updates.py ;;' in setup
