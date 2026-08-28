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
