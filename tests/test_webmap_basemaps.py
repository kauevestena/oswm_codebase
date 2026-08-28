from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_webmap_uses_generated_raster_pmtiles_without_carto():
    library = (ROOT / "webmap/webmap_lib.py").read_text(encoding="utf-8")
    template = (ROOT / "webmap/webmap_base.html").read_text(encoding="utf-8")
    generator = (ROOT / "webmap/create_webmap_new.py").read_text(encoding="utf-8")
    runner = (ROOT / "runners/daily.sh").read_text(encoding="utf-8")
    snapshot_i18n = (ROOT / "webmap/snapshot/snapshot_i18n.js").read_text(
        encoding="utf-8"
    )

    assert "basemaps.cartocdn.com" not in library
    assert 'f"pmtiles://{basemap_light_path}"' in library
    assert 'f"pmtiles://{basemap_dark_path}"' in library
    assert 'params["basemaps"]' in generator
    assert 'id="basemap-selector"' in template
    assert "style.sources.osm.url" in template
    assert runner.index("raster_basemap_gen.py") < runner.index("create_webmap_new.py")
    assert "CARTO" not in snapshot_i18n


def test_all_production_maps_use_node_scoped_pmtiles_basemaps():
    expected = {
        "data_quality/dq_funcs.py": "data/basemaps/light.pmtiles",
        "data_quality/completeness/completeness_lib.py": "data/basemaps/dark.pmtiles",
        "datahub/acquisition/generate_acquisition.py": "data/basemaps/light.pmtiles",
        "hazard_analysis/hazard_analysis.html": "data/basemaps/light.pmtiles",
        "routing/routing_demo.html": "data/basemaps/light.pmtiles",
    }
    for relative, archive in expected.items():
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert archive in content
        assert "pmtiles://" in content
        assert "OpenFreeMap" in content


def test_production_sources_do_not_reference_carto_basemaps():
    production_roots = (
        "data_quality",
        "datahub",
        "docs",
        "hazard_analysis",
        "routing",
        "webmap",
    )
    forbidden = ("basemaps." + "cartocdn.com", "CART" + "O")
    offenders = []
    for root_name in production_roots:
        for path in (ROOT / root_name).rglob("*"):
            if path.suffix.lower() not in {".html", ".js", ".json", ".md", ".py"}:
                continue
            content = path.read_text(encoding="utf-8")
            if any(token in content for token in forbidden):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
