from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import mapbox_vector_tile
from PIL import Image
from pmtiles.reader import MmapSource, Reader


ROOT = Path(__file__).resolve().parents[1]


def load_generator(tmp_path: Path, monkeypatch):
    constants = types.ModuleType("constants")
    constants.CITY_NAME = "Fixture City"
    constants.MAX_TILE_FILESIZE_BYTES = 95 * 1024 * 1024
    constants.basemap_folderpath = str(tmp_path / "data/basemaps")
    constants.basemap_light_path = str(tmp_path / "data/basemaps/light.pmtiles")
    constants.basemap_dark_path = str(tmp_path / "data/basemaps/dark.pmtiles")
    constants.basemap_report_path = str(
        tmp_path / "data/basemaps/generation_report.json"
    )
    functions = types.ModuleType("functions")
    functions.get_boundaries_bbox = lambda: [9.15, 45.46, 9.16, 45.47]
    monkeypatch.setitem(sys.modules, "constants", constants)
    monkeypatch.setitem(sys.modules, "functions", functions)
    name = f"raster_basemap_gen_{tmp_path.name}"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "generation/raster_basemap_gen.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_zoom_jobs_are_sorted_and_overzoom_from_z14(tmp_path, monkeypatch):
    module = load_generator(tmp_path, monkeypatch)
    bbox = [9.15, 45.46, 9.16, 45.47]
    jobs = module.output_jobs(bbox, 14, 16)
    assert jobs == sorted(jobs)
    _, _, x, y = next(job for job in jobs if job[1] == 16)
    assert module.source_coordinate(16, x, y) == (14, x >> 2, y >> 2)
    assert {job[1] for job in jobs} == {14, 15, 16}


def test_builds_valid_light_and_dark_raster_pmtiles(tmp_path, monkeypatch):
    module = load_generator(tmp_path, monkeypatch)
    bbox = [9.15, 45.46, 9.16, 45.47]
    source_path = tmp_path / "source.pbf"
    source_path.write_bytes(mapbox_vector_tile.encode({"name": "place", "features": []}))
    jobs = module.output_jobs(bbox, 14, 14)
    sources = {
        module.source_coordinate(z, x, y): source_path for _, z, x, y in jobs
    }
    outputs = {
        "light": tmp_path / "light.pmtiles",
        "dark": tmp_path / "dark.pmtiles",
    }
    tile_count, sizes = module.build_archives(
        bbox,
        14,
        14,
        outputs,
        sources,
    )
    assert tile_count == len(jobs)
    _, zoom, sample_x, sample_y = jobs[0]
    for mode, path in outputs.items():
        assert sizes[mode] == path.stat().st_size
        with path.open("r+b") as stream:
            reader = Reader(MmapSource(stream))
            header = reader.header()
            tile = reader.get(zoom, sample_x, sample_y)
            assert header["tile_type"].name == "JPEG"
            assert tile is not None
            assert Image.open(__import__("io").BytesIO(tile)).size == (256, 256)


def test_generation_steps_down_until_both_archives_fit(tmp_path, monkeypatch):
    module = load_generator(tmp_path, monkeypatch)
    attempts = []
    monkeypatch.setattr(
        module,
        "fetch_source_tiles",
        lambda *_args, **_kwargs: ("https://example/{z}/{x}/{y}.pbf", {}),
    )

    def fake_build(_bbox, _min_zoom, max_zoom, output_paths, _sources):
        attempts.append(max_zoom)
        for path in output_paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"archive")
        sizes = {"light": 101 if max_zoom == 16 else 80, "dark": 90}
        return 12, sizes

    monkeypatch.setattr(module, "build_archives", fake_build)
    report = module.generate(
        [9.15, 45.46, 9.16, 45.47],
        min_zoom=14,
        max_zoom=16,
        size_limit_bytes=100,
        cache_dir=tmp_path / "cache",
    )
    assert attempts == [16, 15]
    assert report["actual_max_zoom"] == 15
    assert report["outputs"]["light"]["bytes"] == 80


def test_valid_archives_are_reused_without_fetching(tmp_path, monkeypatch):
    module = load_generator(tmp_path, monkeypatch)
    bbox = [9.15, 45.46, 9.16, 45.47]
    source_path = tmp_path / "source.pbf"
    source_path.write_bytes(mapbox_vector_tile.encode({"name": "place", "features": []}))
    jobs = module.output_jobs(bbox, 14, 14)
    outputs = {
        "light": Path(module.basemap_light_path),
        "dark": Path(module.basemap_dark_path),
    }
    sources = {
        module.source_coordinate(z, x, y): source_path for _, z, x, y in jobs
    }
    tile_count, sizes = module.build_archives(bbox, 14, 14, outputs, sources)
    report = {
        "schema_version": 1,
        "renderer_version": module.RENDERER_VERSION,
        "bounds": bbox,
        "min_zoom": 14,
        "requested_max_zoom": 14,
        "actual_max_zoom": 14,
        "tile_count_per_archive": tile_count,
        "outputs": {
            mode: {"path": str(path), "bytes": sizes[mode]}
            for mode, path in outputs.items()
        },
    }
    Path(module.basemap_report_path).write_text(__import__("json").dumps(report))
    monkeypatch.setattr(
        module,
        "fetch_source_tiles",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fetched")),
    )
    assert module.generate(bbox, min_zoom=14, max_zoom=14) == report
