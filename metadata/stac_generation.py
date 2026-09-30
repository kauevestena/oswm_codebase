"""Publish current OSWM vector products as a static STAC 1.1.0 catalog.

Run from a node root after metadata_generation.py. The pilot is opt-in via
STAC_ENABLED and explicit STAC_LICENSES in the node config. No data is copied,
no historical releases are implied, and generation makes no network requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

CODEBASE_ROOT = Path(__file__).resolve().parents[1]
if str(CODEBASE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEBASE_ROOT))

from metadata.metadata_generation import (  # noqa: E402
    _atomic_json_dump,
    _load_node_config,
    metadata_relative_path_for_data,
)
from time_utils import isoformat_utc, parse_timestamp  # noqa: E402


GENERATOR = "oswm_codebase.metadata.stac_generation"
VERSION = "1.1.0"
PROCESSED_LAYERS = ("sidewalks", "crossings", "kerbs", "other_footways")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _link(rel: str, href: str, *, item: bool = False, **extra) -> dict:
    return {
        "rel": rel, "href": href,
        "type": "application/geo+json" if item else "application/json", **extra,
    }


def _base(kind: str, identifier: str, title: str, description: str) -> dict:
    return {
        "type": kind, "stac_version": VERSION, "stac_extensions": [],
        "id": identifier, "title": title, "description": description,
        "oswm:generator": GENERATOR,
    }


def _license(value) -> tuple[str, str]:
    if isinstance(value, str):
        value = {"id": value}
    if not isinstance(value, dict) or not isinstance(value.get("id"), str):
        raise ValueError("Each STAC_LICENSES entry needs a license ID")
    identifier = value["id"]
    if not re.fullmatch(r"[A-Za-z0-9.+-]+", identifier):
        raise ValueError("Use an SPDX license ID, or 'other' with a license URL")
    href = value.get("url")
    if not href and identifier != "other":
        href = f"https://spdx.org/licenses/{identifier}.html"
    if not isinstance(href, str) or urlsplit(href).scheme not in {"http", "https"}:
        raise ValueError("License 'other' requires an explicit HTTP(S) license URL")
    return identifier, href


def _asset(root: Path, relative: str, base_url: str, *, role: str = "data") -> dict:
    path = root / relative
    digest = _sha256(path)
    size = path.stat().st_size
    if relative.startswith("data/"):
        record = _read(root / metadata_relative_path_for_data(relative))
        distribution = record["distribution"]
        if (distribution.get("resource_path") != relative
                or distribution.get("checksum", {}).get("algorithm") != "SHA-256"
                or distribution.get("checksum", {}).get("value") != digest
                or distribution.get("byte_size") != size):
            raise ValueError(f"Stale metadata for {relative}; regenerate metadata first")
        media_type = distribution["media_type"]
    else:
        media_type = "application/json"
    return {
        "href": urljoin(base_url, relative), "type": media_type, "roles": [role],
        "oswm:sha256": digest, "oswm:byte_size": size,
    }


def _footprint(path: Path):
    # Read only the geometry column, including files using a non-default name.
    import geopandas as gpd
    import pyarrow.parquet as pq
    from shapely.geometry import MultiPoint, mapping
    from shapely.geometry.polygon import orient

    schema = pq.read_schema(path)
    geo = json.loads(schema.metadata[b"geo"])
    frame = gpd.read_parquet(path, columns=[geo["primary_column"]])
    if frame.crs is None:
        raise ValueError(f"Missing CRS in {path}")
    usable = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty]
    if usable.empty:
        return None
    bounds = [float(value) for value in usable.to_crs("EPSG:4326").total_bounds]
    west, south, east, north = bounds
    if not (all(math.isfinite(value) for value in bounds)
            and -180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError(f"Invalid WGS84 bounds for {path}: {bounds}")
    # Convex hull also handles a dataset containing only one point or a line.
    hull = MultiPoint([
        (west, south), (east, south), (east, north), (west, north),
    ]).convex_hull
    if hull.geom_type == "Polygon":
        hull = orient(hull, sign=1.0)
    geometry = json.loads(json.dumps(mapping(hull)))
    return bounds, geometry, len(frame)


def _product_time(root: Path, family: str, registry: dict, timezone: str) -> str:
    value = (registry.get("Data Pre-Processing") if family == "processed" else
             _read(root / "data/routing/metadata.json").get("generated_at"))
    parsed = parse_timestamp(value, timezone)
    if parsed is None:
        raise ValueError(f"Missing or invalid product-generation timestamp for {family}")
    return isoformat_utc(parsed)


def _timezone(config) -> str:
    explicit = getattr(config, "METADATA_TIMEZONE", None)
    if explicit:
        from zoneinfo import ZoneInfo
        ZoneInfo(explicit)  # Reject misspellings instead of silently changing dates.
        return explicit
    lat, lon = getattr(config, "MID_LAT", None), getattr(config, "MID_LGT", None)
    if lat is None or lon is None:
        bounds = getattr(config, "BOUNDING_BOX", None)
        if bounds and len(bounds) == 4:
            lat, lon = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
    if lat is not None and lon is not None:
        from timezonefinder import TimezoneFinder
        return TimezoneFinder().timezone_at(lat=float(lat), lng=float(lon)) or "UTC"
    return "UTC"


def _products(root: Path, families: dict):
    if "processed" in families:
        paths = [root / f"data/processed/{name}.parquet" for name in PROCESSED_LAYERS]
        paths.extend(sorted((root / "data/processed/other_footways").glob("*.parquet")))
        for path in paths:
            if path.is_file():
                yield "processed", path
    path = root / "data/routing/network.parquet"
    if "routing" in families and path.is_file():
        yield "routing", path


def _tiles(root: Path, family: str, name: str, digest: str):
    if family == "routing":
        relative = "data/routing/network.pmtiles"
        report_path = root / "data/routing/tile_generation_report.json"
    else:
        relative = f"data/tiles/{name}.pmtiles"
        report_path = root / "data/tiles/tile_generation_report.json"
    if not (root / relative).is_file():
        return None
    report = _read(report_path) if report_path.is_file() else {}
    if family == "processed":
        report = report.get(name, {})
    if report.get("status") == "ok" and report.get("source_sha256") == digest:
        return relative
    return None


def _local_target(root: Path, base_url: str, href: str) -> Path:
    if not href.startswith(base_url):
        raise ValueError(f"Asset URL is outside this node: {href}")
    parts = urlsplit(href[len(base_url):])
    if parts.query or parts.fragment or parts.netloc or parts.scheme:
        raise ValueError(f"Unexpected asset URL: {href}")
    target = (root / unquote(parts.path)).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Asset path escapes node: {href}")
    return target


def _validate(records: dict[str, dict], root: Path, base_url: str) -> list[str]:
    from metadata.stac_validation import validate_document

    errors = []
    for relative, document in records.items():
        errors.extend(f"{relative}: {error}" for error in validate_document(document))
        for link in document.get("links", []):
            if link["rel"] not in {"child", "item", "parent", "root", "collection"}:
                continue
            target = os.path.normpath(str(Path(relative).parent / link["href"]))
            if target not in records:
                errors.append(f"{relative}: missing STAC link target {target}")
            elif link["rel"] == "collection" and document.get("collection") != records[target]["id"]:
                errors.append(f"{relative}: collection ID/link mismatch")
        for key, asset in document.get("assets", {}).items():
            try:
                target = _local_target(root, base_url, asset["href"])
                if target.stat().st_size != asset["oswm:byte_size"] or _sha256(target) != asset["oswm:sha256"]:
                    errors.append(f"{relative}: stale asset {key}")
            except (OSError, ValueError, KeyError) as exc:
                errors.append(f"{relative}: invalid asset {key}: {exc}")
    if "catalog.json" not in records:
        errors.append("Missing stac/catalog.json")
    return errors


def _write_catalog(root: Path, records: dict[str, dict]) -> None:
    destination = root / "stac"
    # Preflight every collision before changing any existing catalog file.
    for relative in records:
        path = destination / relative
        if path.exists() and _read(path).get("oswm:generator") != GENERATOR:
            raise ValueError(f"Refusing to overwrite unmanaged STAC file: {path}")
    for relative in sorted(records, key=lambda path: path == "catalog.json"):
        _atomic_json_dump(records[relative], destination / relative)
    _prune(root, set(records))


def _prune(root: Path, keep: set[str]) -> None:
    destination = root / "stac"
    for path in destination.rglob("*.json"):
        if path.relative_to(destination).as_posix() not in keep:
            try:
                owned = _read(path).get("oswm:generator") == GENERATOR
            except (ValueError, AttributeError):
                owned = False
            if owned:
                path.unlink()


def generate_stac(node_root: str | Path = ".") -> dict:
    root = Path(node_root).resolve()
    config = _load_node_config(root)
    families = getattr(config, "STAC_LICENSES", {})
    if not isinstance(families, dict) or not families or set(families) - {"processed", "routing"}:
        raise ValueError("Set STAC_LICENSES for 'processed' and/or 'routing' in config.py")
    licenses = {family: _license(value) for family, value in families.items()}
    node_record = _read(root / "metadata/index.json")
    base_url = node_record["identifier"].removesuffix("metadata/index.json")
    if not base_url.endswith("/") or urlsplit(base_url).scheme not in {"http", "https"}:
        raise ValueError("metadata/index.json must identify its absolute public node URL")
    node_id = "oswm-" + re.sub(r"[^a-z0-9_.-]+", "-", f"{config.USERNAME}-{config.REPO_NAME}".lower())
    city = config.CITY_NAME
    registry = _read(root / "data/updates/registry.json")
    timezone = _timezone(config)
    catalog = _base("Catalog", node_id, f"{city} — OpenSidewalkMap",
                    "Current published OSWM products. Assets are mutable; historical releases are not retained by this catalog.")
    catalog["links"] = [_link("self", base_url + "stac/catalog.json"), _link("root", "catalog.json")]
    records = {"catalog.json": catalog}
    skipped = []
    for family, path in _products(root, families):
        spatial = _footprint(path)
        if spatial is None:
            skipped.append({"path": path.relative_to(root).as_posix(), "reason": "empty geometry"})
            continue
        bbox, geometry, count = spatial
        relative = path.relative_to(root).as_posix()
        product = path.relative_to(root / "data").with_suffix("").as_posix().replace("/", "--")
        identifier = f"{node_id}-{product}"
        metadata_path = metadata_relative_path_for_data(relative)
        record = _read(root / metadata_path)
        timestamp = _product_time(root, family, registry, timezone)
        data_asset = _asset(root, relative, base_url)
        assets = {
            "data": {**data_asset, "title": "Analytical GeoParquet"},
            "metadata": _asset(root, metadata_path, base_url, role="metadata"),
        }
        tiles = _tiles(root, family, path.stem, data_asset["oswm:sha256"])
        if tiles:
            assets["visual"] = {
                **_asset(root, tiles, base_url, role="visual"),
                "title": "Display PMTiles",
                "description": "Zoom-dependent display representation; geometry and attributes may differ from the analytical GeoParquet.",
            }
        else:
            skipped.append({"path": relative, "reason": "no PMTiles with matching source checksum"})
        if family == "routing":
            assets["routing_metadata"] = _asset(root, "data/routing/metadata.json", base_url, role="metadata")
            assets["profiles"] = _asset(root, "data/routing/profiles.json", base_url, role="metadata")
        license_id, license_url = licenses[family]
        title = record["title"]
        description = record["abstract"]
        collection = _base("Collection", identifier, title, description)
        collection.update({
            "license": license_id,
            "extent": {"spatial": {"bbox": [bbox]}, "temporal": {"interval": [[timestamp, timestamp]]}},
            "providers": [{"name": "OpenSidewalkMap", "roles": ["processor", "host"], "url": base_url}],
            "keywords": ["OpenSidewalkMap", family, path.stem, city],
            "links": [
                _link("self", base_url + f"stac/{product}/collection.json"),
                _link("root", "../catalog.json"), _link("parent", "../catalog.json"),
                _link("license", license_url, type="text/html"),
                _link("item", "current.json", item=True),
            ],
        })
        properties = {
            "datetime": timestamp, "title": title, "description": description,
            "oswm:state": "current", "oswm:product": product,
            "oswm:datetime_semantics": "product-generation",
            "oswm:footprint": "WGS84 envelope of published feature geometries",
            "oswm:feature_count": count,
            "oswm:attribution": "© OpenStreetMap contributors; additional sources are described in the linked metadata.",
        }
        fetched = parse_timestamp(registry.get("Data Fetching"), timezone)
        if fetched and fetched <= parse_timestamp(timestamp):
            properties["oswm:source_fetched_at"] = isoformat_utc(fetched)
        revision = record.get("metadata_generation", {}).get("code", {}).get("commit")
        if revision:
            properties["oswm:metadata_codebase_commit"] = revision
        item = {
            "type": "Feature", "stac_version": VERSION, "stac_extensions": [],
            "id": f"{identifier}-current", "collection": identifier,
            "geometry": geometry, "bbox": bbox, "properties": properties,
            "assets": assets, "oswm:generator": GENERATOR,
            "links": [
                _link("self", base_url + f"stac/{product}/current.json", item=True),
                _link("root", "../catalog.json"), _link("parent", "collection.json"),
                _link("collection", "collection.json"),
            ],
        }
        records[f"{product}/collection.json"] = collection
        records[f"{product}/current.json"] = item
        catalog["links"].append(_link("child", f"{product}/collection.json", title=title))
    if len(records) == 1:
        raise ValueError("No nonempty products available for the configured STAC_LICENSES")
    errors = _validate(records, root, base_url)
    if errors:
        raise ValueError("STAC validation failed:\n" + "\n".join(errors))
    _write_catalog(root, records)
    return {"catalog": "stac/catalog.json", "collections": (len(records) - 1) // 2,
            "records_written": len(records), "skipped": skipped}


def validate_stac(node_root: str | Path = ".") -> list[str]:
    root = Path(node_root).resolve()
    base_url = _read(root / "metadata/index.json")["identifier"].removesuffix("metadata/index.json")
    records = {}
    for path in (root / "stac").rglob("*.json"):
        record = _read(path)
        if record.get("oswm:generator") == GENERATOR:
            records[path.relative_to(root / "stac").as_posix()] = record
    return _validate(records, root, base_url)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-root", default=".")
    parser.add_argument("--if-enabled", action="store_true", help="Skip unless STAC_ENABLED is True in config.py")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.node_root).resolve()
    if args.if_enabled and getattr(_load_node_config(root), "STAC_ENABLED", False) is not True:
        _prune(root, set())
        print(json.dumps({"stac": "disabled"}))
        return 0
    try:
        if args.validate_only:
            errors = validate_stac(root)
            print(json.dumps({"errors": errors}, indent=2))
            return int(bool(errors))
        print(json.dumps(generate_stac(root), indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"STAC generation/validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
