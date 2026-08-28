#!/usr/bin/env python3
"""Generate node-scoped light and dark raster PMTiles basemaps.

OpenFreeMap's OpenMapTiles vector service is used only as build input.  The
published node reads the resulting static PMTiles archives and therefore needs
no client-side basemap API key or third-party tile requests.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import math
import os
import shutil
import sys
import tempfile
import time
from functools import lru_cache
from pathlib import Path

import mapbox_vector_tile
import requests
from PIL import Image, ImageDraw, ImageFont
from pmtiles.reader import MmapSource, Reader
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

CODEBASE_ROOT = Path(__file__).resolve().parents[1]
if str(CODEBASE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEBASE_ROOT))

from constants import (  # noqa: E402
    CITY_NAME,
    MAX_TILE_FILESIZE_BYTES,
    basemap_dark_path,
    basemap_folderpath,
    basemap_light_path,
    basemap_report_path,
)
from functions import get_boundaries_bbox  # noqa: E402


OPENFREEMAP_TILEJSON = "https://tiles.openfreemap.org/planet"
SOURCE_MAX_ZOOM = 14
DEFAULT_MIN_ZOOM = 10
DEFAULT_MAX_ZOOM = 16
JPEG_QUALITY = 82
TILE_SIZE = 256
ATTRIBUTION = (
    "Basemap © OpenFreeMap, © OpenMapTiles; data © OpenStreetMap contributors"
)
RENDERER_VERSION = 1

PALETTES = {
    "light": {
        "background": "#edf0f2",
        "residential": "#e3e6e8",
        "commercial": "#e8e1dc",
        "industrial": "#dedfe3",
        "green": "#d7e4d2",
        "water": "#b7d7e8",
        "building": "#d2d0ce",
        "road_casing": "#c8c9ca",
        "road_major": "#f9f6ed",
        "road_minor": "#ffffff",
        "path": "#dfd5c6",
        "rail": "#a9aaad",
        "boundary": "#a795a8",
        "waterway": "#9bc5da",
        "label": "#52575b",
        "label_halo": "#f5f6f7",
    },
    "dark": {
        "background": "#171a1d",
        "residential": "#202428",
        "commercial": "#292426",
        "industrial": "#24252a",
        "green": "#1d2b24",
        "water": "#152b38",
        "building": "#292d31",
        "road_casing": "#202327",
        "road_major": "#55504a",
        "road_minor": "#3c4145",
        "path": "#4a443d",
        "rail": "#5b5d61",
        "boundary": "#756678",
        "waterway": "#28536a",
        "label": "#c8cbce",
        "label_halo": "#1a1d20",
    },
}

ROAD_WIDTHS = {
    "motorway": 5,
    "trunk": 5,
    "primary": 4,
    "secondary": 4,
    "tertiary": 3,
    "minor": 2,
    "service": 2,
    "track": 1,
    "path": 1,
    "rail": 1,
    "transit": 1,
}


def lonlat_to_fractional_tile(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    lat = max(-85.05112878, min(85.05112878, lat))
    scale = 2**zoom
    x = (lon + 180.0) / 360.0 * scale
    y = (
        1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi
    ) / 2.0 * scale
    return x, y


def tile_union_for_bbox(
    bbox: tuple[float, float, float, float] | list[float], zoom: int
) -> tuple[int, int, int, int]:
    west, south, east, north = bbox
    min_x, max_y_float = lonlat_to_fractional_tile(west, south, zoom)
    max_x_float, min_y = lonlat_to_fractional_tile(east, north, zoom)
    limit = 2**zoom - 1
    return (
        max(0, min(limit, math.floor(min_x))),
        max(0, min(limit, math.floor(min_y))),
        max(0, min(limit, math.floor(max_x_float))),
        max(0, min(limit, math.floor(max_y_float))),
    )


def output_jobs(
    bbox: tuple[float, float, float, float] | list[float],
    min_zoom: int,
    max_zoom: int,
) -> list[tuple[int, int, int, int]]:
    jobs = []
    for zoom in range(min_zoom, max_zoom + 1):
        min_x, min_y, max_x, max_y = tile_union_for_bbox(bbox, zoom)
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                jobs.append((zxy_to_tileid(zoom, x, y), zoom, x, y))
    return sorted(jobs)


def source_coordinate(zoom: int, x: int, y: int) -> tuple[int, int, int]:
    source_zoom = min(zoom, SOURCE_MAX_ZOOM)
    shift = zoom - source_zoom
    return source_zoom, x >> shift, y >> shift


def tile_bounds_lonlat(
    tile_union: tuple[int, int, int, int], zoom: int
) -> tuple[float, float, float, float]:
    min_x, min_y, max_x, max_y = tile_union
    scale = 2**zoom

    def longitude(x: float) -> float:
        return x / scale * 360.0 - 180.0

    def latitude(y: float) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / scale))))

    return (
        longitude(min_x),
        latitude(max_y + 1),
        longitude(max_x + 1),
        latitude(min_y),
    )


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for parent in ("/usr/share/fonts/truetype/dejavu", "/usr/local/share/fonts"):
        candidate = Path(parent) / filename
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def _scaled_point(point: list[float], extent: int, scale: int) -> tuple[float, float]:
    factor = TILE_SIZE * scale / extent
    return point[0] * factor, point[1] * factor


def _line_parts(geometry: dict) -> list[list[list[float]]]:
    if geometry["type"] == "LineString":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiLineString":
        return geometry["coordinates"]
    return []


def _polygon_parts(geometry: dict) -> list[list[list[list[float]]]]:
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    return []


def _point_parts(geometry: dict) -> list[list[float]]:
    if geometry["type"] == "Point":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPoint":
        return geometry["coordinates"]
    return []


def _features(decoded: dict, layer_name: str) -> tuple[list[dict], int]:
    layer = decoded.get(layer_name, {})
    return layer.get("features", []), int(layer.get("extent", 4096))


def _klass(feature: dict) -> str:
    properties = feature.get("properties", {})
    return str(properties.get("class") or properties.get("subclass") or "")


def _draw_polygons(draw, features, extent, scale, color) -> None:
    for feature in features:
        for polygon in _polygon_parts(feature["geometry"]):
            if polygon and len(polygon[0]) >= 3:
                draw.polygon(
                    [_scaled_point(point, extent, scale) for point in polygon[0]],
                    fill=color,
                )


def _draw_lines(draw, features, extent, scale, color, width) -> None:
    for feature in features:
        for line in _line_parts(feature["geometry"]):
            if len(line) >= 2:
                draw.line(
                    [_scaled_point(point, extent, scale) for point in line],
                    fill=color,
                    width=max(1, round(width)),
                    joint="curve",
                )


def _draw_landuse(draw, decoded, palette, scale) -> None:
    for layer_name in ("landcover", "landuse", "park"):
        features, extent = _features(decoded, layer_name)
        for feature in features:
            klass = _klass(feature)
            if layer_name == "park" or klass in {
                "wood", "grass", "farmland", "meadow", "park", "garden", "cemetery",
            }:
                color = palette["green"]
            elif klass in {"commercial", "retail"}:
                color = palette["commercial"]
            elif klass in {"industrial", "railway"}:
                color = palette["industrial"]
            else:
                color = palette["residential"]
            _draw_polygons(draw, [feature], extent, scale, color)


def _road_width(klass: str, target_zoom: int) -> float:
    zoom_factor = max(0.75, 1 + 0.45 * (target_zoom - SOURCE_MAX_ZOOM))
    return ROAD_WIDTHS.get(klass, 2) * zoom_factor


def _draw_transportation(draw, decoded, palette, scale, target_zoom) -> None:
    features, extent = _features(decoded, "transportation")
    ordered = sorted(features, key=lambda feature: _road_width(_klass(feature), target_zoom))
    for casing in (True, False):
        for feature in ordered:
            klass = _klass(feature)
            width = _road_width(klass, target_zoom)
            if casing:
                color = palette["road_casing"]
                width += max(1, scale)
            elif klass in {"motorway", "trunk", "primary", "secondary"}:
                color = palette["road_major"]
            elif klass in {"path", "track"}:
                color = palette["path"]
            elif klass in {"rail", "transit"}:
                color = palette["rail"]
            else:
                color = palette["road_minor"]
            _draw_lines(draw, [feature], extent, scale, color, width)


def _line_midpoint(line, extent, scale):
    if len(line) < 2:
        return None
    first, second = max(
        zip(line, line[1:]),
        key=lambda pair: (pair[1][0] - pair[0][0]) ** 2
        + (pair[1][1] - pair[0][1]) ** 2,
    )
    return _scaled_point(
        [(first[0] + second[0]) / 2, (first[1] + second[1]) / 2],
        extent,
        scale,
    )


def _draw_labels(draw, decoded, palette, scale, target_zoom) -> None:
    size_offset = max(-2, target_zoom - SOURCE_MAX_ZOOM)
    road_font = _font(max(8, 11 + 5 * size_offset))
    place_font = _font(max(9, 14 + 6 * size_offset), bold=True)
    city_font = _font(max(10, 18 + 7 * size_offset), bold=True)
    occupied: list[tuple[int, int, int, int]] = []
    canvas_size = TILE_SIZE * scale

    def place_label(point, text, font, stroke_width) -> bool:
        bbox = draw.textbbox(
            point,
            text,
            font=font,
            stroke_width=stroke_width,
            anchor="mm",
        )
        padding = 3
        padded = (
            bbox[0] - padding,
            bbox[1] - padding,
            bbox[2] + padding,
            bbox[3] + padding,
        )
        if padded[0] < 0 or padded[1] < 0 or padded[2] > canvas_size or padded[3] > canvas_size:
            return False
        if any(
            padded[0] < other[2]
            and padded[2] > other[0]
            and padded[1] < other[3]
            and padded[3] > other[1]
            for other in occupied
        ):
            return False
        draw.text(
            point,
            text,
            font=font,
            fill=palette["label"],
            stroke_width=stroke_width,
            stroke_fill=palette["label_halo"],
            anchor="mm",
        )
        occupied.append(padded)
        return True

    # Places establish the visual hierarchy and reserve space before roads.
    place_features, place_extent = _features(decoded, "place")
    place_priority = {"city": 0, "town": 1, "village": 2, "suburb": 3, "neighbourhood": 4}
    place_features = sorted(
        place_features, key=lambda feature: place_priority.get(_klass(feature), 99)
    )
    seen_places = set()
    for feature in place_features:
        properties = feature.get("properties", {})
        name = properties.get("name")
        points = _point_parts(feature["geometry"])
        klass = _klass(feature)
        if not name or not points or klass not in {
            "city", "town", "village", "suburb", "neighbourhood",
        }:
            continue
        if name in seen_places:
            continue
        if place_label(
            _scaled_point(points[0], place_extent, scale),
            str(name),
            city_font if klass in {"city", "town"} else place_font,
            3,
        ):
            seen_places.add(name)

    road_features, road_extent = _features(decoded, "transportation_name")
    road_features = sorted(
        road_features,
        key=lambda feature: -_road_width(_klass(feature), target_zoom),
    )
    seen_roads = set()
    for feature in road_features:
        name = feature.get("properties", {}).get("name")
        parts = _line_parts(feature["geometry"])
        if not name or name in seen_roads or not parts:
            continue
        point = _line_midpoint(max(parts, key=len), road_extent, scale)
        if point and place_label(point, str(name), road_font, 2):
            seen_roads.add(name)


def render_parent(decoded: dict, mode: str, target_zoom: int, source_zoom: int) -> Image.Image:
    scale = 2 ** (target_zoom - source_zoom)
    palette = PALETTES[mode]
    image = Image.new("RGB", (TILE_SIZE * scale, TILE_SIZE * scale), palette["background"])
    draw = ImageDraw.Draw(image)
    _draw_landuse(draw, decoded, palette, scale)
    water, extent = _features(decoded, "water")
    _draw_polygons(draw, water, extent, scale, palette["water"])
    waterways, extent = _features(decoded, "waterway")
    _draw_lines(draw, waterways, extent, scale, palette["waterway"], max(1, scale))
    buildings, extent = _features(decoded, "building")
    _draw_polygons(draw, buildings, extent, scale, palette["building"])
    _draw_transportation(draw, decoded, palette, scale, target_zoom)
    boundaries, extent = _features(decoded, "boundary")
    _draw_lines(draw, boundaries, extent, scale, palette["boundary"], max(1, scale))
    _draw_labels(draw, decoded, palette, scale, target_zoom)
    return image


def jpeg_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=False,
        subsampling="4:2:0",
    )
    return buffer.getvalue()


def fetch_source_tiles(
    cache_dir: Path,
    jobs: list[tuple[int, int, int, int]],
    workers: int = 8,
) -> tuple[str, dict[tuple[int, int, int], Path]]:
    tilejson_response = requests.get(
        OPENFREEMAP_TILEJSON,
        timeout=60,
        headers={"User-Agent": "OpenSidewalkMap-basemap-builder/1.0"},
    )
    tilejson_response.raise_for_status()
    template = tilejson_response.json()["tiles"][0]
    coordinates = sorted({source_coordinate(z, x, y) for _, z, x, y in jobs})
    paths = {
        coordinate: cache_dir / str(coordinate[0]) / str(coordinate[1]) / f"{coordinate[2]}.pbf"
        for coordinate in coordinates
    }

    def fetch(coordinate: tuple[int, int, int]) -> None:
        path = paths[coordinate]
        if path.is_file() and path.stat().st_size:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        z, x, y = coordinate
        url = template.format(z=z, x=x, y=y)
        last_error = None
        for attempt in range(3):
            try:
                response = requests.get(
                    url,
                    timeout=90,
                    headers={"User-Agent": "OpenSidewalkMap-basemap-builder/1.0"},
                )
                response.raise_for_status()
                path.write_bytes(response.content)
                return
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2**attempt)
        raise RuntimeError(f"Could not download {url}") from last_error

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch, coordinate) for coordinate in coordinates]
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            future.result()
            if completed % 25 == 0 or completed == len(futures):
                print(f"Basemap source tiles: {completed}/{len(futures)}", flush=True)
    return template, paths


def build_archives(
    bbox: tuple[float, float, float, float] | list[float],
    min_zoom: int,
    max_zoom: int,
    output_paths: dict[str, Path],
    source_paths: dict[tuple[int, int, int], Path],
) -> tuple[int, dict[str, int]]:
    jobs = output_jobs(bbox, min_zoom, max_zoom)

    @lru_cache(maxsize=2)
    def decoded_source(source_zoom: int, source_x: int, source_y: int) -> dict:
        return mapbox_vector_tile.decode(
            source_paths[(source_zoom, source_x, source_y)].read_bytes(),
            default_options={"y_coord_down": True},
        )

    @lru_cache(maxsize=4)
    def rendered_parent(
        mode: str, target_zoom: int, source_zoom: int, source_x: int, source_y: int
    ) -> Image.Image:
        return render_parent(
            decoded_source(source_zoom, source_x, source_y),
            mode,
            target_zoom,
            source_zoom,
        )

    temporary_paths = {
        mode: path.with_name(f".{path.name}.tmp") for mode, path in output_paths.items()
    }
    streams = {}
    writers = {}
    try:
        for mode, temporary in temporary_paths.items():
            temporary.parent.mkdir(parents=True, exist_ok=True)
            streams[mode] = temporary.open("wb")
            writers[mode] = Writer(streams[mode])

        for completed, (tile_id, zoom, x, y) in enumerate(jobs, 1):
            source_zoom, source_x, source_y = source_coordinate(zoom, x, y)
            scale = 2 ** (zoom - source_zoom)
            child_x = x - source_x * scale
            child_y = y - source_y * scale
            crop = (
                child_x * TILE_SIZE,
                child_y * TILE_SIZE,
                (child_x + 1) * TILE_SIZE,
                (child_y + 1) * TILE_SIZE,
            )
            for mode in output_paths:
                parent = rendered_parent(
                    mode, zoom, source_zoom, source_x, source_y
                )
                tile = parent if scale == 1 else parent.crop(crop)
                writers[mode].write_tile(tile_id, jpeg_bytes(tile))
            if completed % 250 == 0 or completed == len(jobs):
                print(f"Raster basemap tiles: {completed}/{len(jobs)}", flush=True)

        west, south, east, north = tile_bounds_lonlat(
            tile_union_for_bbox(bbox, max_zoom), max_zoom
        )
        header = {
            "tile_type": TileType.JPEG,
            "tile_compression": Compression.NONE,
            "min_lon_e7": round(west * 1e7),
            "min_lat_e7": round(south * 1e7),
            "max_lon_e7": round(east * 1e7),
            "max_lat_e7": round(north * 1e7),
            "center_lon_e7": round(((west + east) / 2) * 1e7),
            "center_lat_e7": round(((south + north) / 2) * 1e7),
            "center_zoom": min(max_zoom, 14),
        }
        for mode, writer in writers.items():
            metadata = {
                "name": f"OSWM {CITY_NAME} {mode} raster basemap",
                "format": "jpeg",
                "bounds": ",".join(str(value) for value in (west, south, east, north)),
                "minzoom": min_zoom,
                "maxzoom": max_zoom,
                "attribution": ATTRIBUTION,
                "description": (
                    f"Node-scoped {mode} context basemap rendered from OpenFreeMap vector tiles."
                ),
            }
            writer.finalize(header, metadata)
            streams[mode].close()
        for mode, path in output_paths.items():
            os.replace(temporary_paths[mode], path)
        return len(jobs), {mode: path.stat().st_size for mode, path in output_paths.items()}
    finally:
        for stream in streams.values():
            if not stream.closed:
                stream.close()
        for temporary in temporary_paths.values():
            temporary.unlink(missing_ok=True)


def reusable_report(
    bbox: tuple[float, float, float, float] | list[float],
    min_zoom: int,
    max_zoom: int,
    size_limit_bytes: int,
) -> dict | None:
    report_path = Path(basemap_report_path)
    output_paths = {
        "light": Path(basemap_light_path),
        "dark": Path(basemap_dark_path),
    }
    try:
        report = json.loads(report_path.read_text())
        if report.get("renderer_version") != RENDERER_VERSION:
            return None
        if report.get("bounds") != list(bbox):
            return None
        if report.get("min_zoom") != min_zoom:
            return None
        if report.get("requested_max_zoom") != max_zoom:
            return None
        actual_max_zoom = int(report["actual_max_zoom"])
        if not min_zoom <= actual_max_zoom <= max_zoom:
            return None
        for mode, path in output_paths.items():
            expected = report["outputs"][mode]
            size = path.stat().st_size
            if expected.get("path") != str(path):
                return None
            if expected.get("bytes") != size or not 0 < size <= size_limit_bytes:
                return None
            with path.open("r+b") as stream:
                header = Reader(MmapSource(stream)).header()
                if header["tile_type"] != TileType.JPEG:
                    return None
                if (
                    header["min_zoom"] != min_zoom
                    or header["max_zoom"] != actual_max_zoom
                ):
                    return None
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return report


def generate(
    bbox: tuple[float, float, float, float] | list[float],
    min_zoom: int = DEFAULT_MIN_ZOOM,
    max_zoom: int = DEFAULT_MAX_ZOOM,
    size_limit_bytes: int = MAX_TILE_FILESIZE_BYTES,
    cache_dir: Path | None = None,
    force: bool = False,
) -> dict:
    if min_zoom < 0 or max_zoom < min_zoom:
        raise ValueError("Invalid basemap zoom range")
    if not force:
        existing = reusable_report(bbox, min_zoom, max_zoom, size_limit_bytes)
        if existing is not None:
            print(
                "Raster basemaps already satisfy the current boundary, rendering, "
                "and size contract; reusing them.",
                flush=True,
            )
            return existing
    started = time.perf_counter()
    output_dir = Path(basemap_folderpath)
    output_paths = {
        "light": Path(basemap_light_path),
        "dark": Path(basemap_dark_path),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    managed_cache = cache_dir is None
    if managed_cache:
        cache_dir = Path(tempfile.mkdtemp(prefix="oswm-basemap-source-"))

    try:
        initial_jobs = output_jobs(bbox, min_zoom, max_zoom)
        template, source_paths = fetch_source_tiles(cache_dir, initial_jobs)
        chosen_zoom = max_zoom
        while True:
            jobs, sizes = build_archives(
                bbox, min_zoom, chosen_zoom, output_paths, source_paths
            )
            oversized = {
                mode: size for mode, size in sizes.items() if size > size_limit_bytes
            }
            if not oversized:
                break
            if chosen_zoom == min_zoom:
                raise RuntimeError(
                    "Raster basemap exceeds the size limit even at the minimum zoom: "
                    + json.dumps(oversized)
                )
            print(
                f"Basemap exceeds {size_limit_bytes:,} bytes; retrying with max zoom "
                f"{chosen_zoom - 1}",
                flush=True,
            )
            chosen_zoom -= 1

        report = {
            "schema_version": 1,
            "renderer_version": RENDERER_VERSION,
            "node": CITY_NAME,
            "bounds": list(bbox),
            "source": {
                "tilejson": OPENFREEMAP_TILEJSON,
                "versioned_template": template,
                "attribution": ATTRIBUTION,
            },
            "min_zoom": min_zoom,
            "requested_max_zoom": max_zoom,
            "actual_max_zoom": chosen_zoom,
            "tile_count_per_archive": jobs,
            "jpeg_quality": JPEG_QUALITY,
            "size_limit_bytes": size_limit_bytes,
            "outputs": {
                mode: {"path": str(path), "bytes": sizes[mode]}
                for mode, path in output_paths.items()
            },
            "elapsed_seconds": time.perf_counter() - started,
        }
        Path(basemap_report_path).write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        if managed_cache:
            shutil.rmtree(cache_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-zoom", type=int, default=DEFAULT_MIN_ZOOM)
    parser.add_argument("--max-zoom", type=int, default=DEFAULT_MAX_ZOOM)
    parser.add_argument(
        "--size-limit-mib",
        type=float,
        default=MAX_TILE_FILESIZE_BYTES / (1024 * 1024),
    )
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh basemaps even when the existing archives remain valid.",
    )
    args = parser.parse_args()
    report = generate(
        get_boundaries_bbox(),
        min_zoom=args.min_zoom,
        max_zoom=args.max_zoom,
        size_limit_bytes=round(args.size_limit_mib * 1024 * 1024),
        cache_dir=args.cache_dir,
        force=args.force
        or os.environ.get("OSWM_FORCE_BASEMAP_REGEN", "").lower()
        in {"1", "true", "yes", "on"},
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
