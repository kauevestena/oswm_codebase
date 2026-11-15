"""Current OSM snapshots from Geofabrik, independent of Overpass and ohsome.

Keep OSMnx's feature parsing semantics by supplying reference-complete local
OSM XML. Never turn an unavailable, stale or incomplete extract into empty data.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from time_utils import isoformat_utc, parse_timestamp


INDEX_URL = "https://download.geofabrik.de/index-v1.json"
LOGGER = logging.getLogger(__name__)
PROVENANCE_KEY = "oswm_acquisition"


class PbfAcquisitionError(RuntimeError):
    """The PBF provider could not supply a complete, sufficiently fresh snapshot."""


def pbf_options_from_config(config, *, minimum_timestamp=None):
    """Defaults also enable the fallback on existing nodes without config edits."""
    get = config.get if isinstance(config, Mapping) else lambda k, d: getattr(config, k, d)
    if not get("PBF_FALLBACK_ENABLED", True):
        return None
    return {
        "region": get("PBF_REGION", "auto"),
        "cache_dir": get("PBF_CACHE_DIR", ".cache/oswm/pbf"),
        "max_download_bytes": get("PBF_MAX_DOWNLOAD_MIB", 1024) * 1024 * 1024,
        "max_age_hours": get("PBF_MAX_AGE_HOURS", 72),
        "minimum_timestamp": minimum_timestamp,
    }


def _download(url, destination, *, max_bytes, deadline_seconds=900):
    """Stream to a caller-owned temporary file with size and time limits."""
    started = time.monotonic()
    digest = hashlib.sha256()
    total = 0
    headers = {"User-Agent": "OpenSidewalkMap/1.0 (https://github.com/kauevestena/oswm_codebase)"}
    with requests.get(url, stream=True, timeout=(15, 60), headers=headers) as response:
        response.raise_for_status()
        if int(response.headers.get("Content-Length", 0)) > max_bytes:
            raise PbfAcquisitionError(f"Download exceeds {max_bytes} bytes: {url}")
        with open(destination, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                total += len(chunk)
                if total > max_bytes or time.monotonic() - started > deadline_seconds:
                    raise PbfAcquisitionError(f"Download exceeded size/time budget: {url}")
                output.write(chunk)
                digest.update(chunk)
    if not total:
        raise PbfAcquisitionError(f"Empty download: {url}")
    return digest.hexdigest()


def _cached_json(url, cache_dir, *, max_bytes=8 * 1024 * 1024):
    """Cache small catalogue/boundary documents separately from PBF snapshots."""
    directory = cache_dir / "catalogue"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
    try:
        if 0 <= time.time() - path.stat().st_mtime < 24 * 3600:
            return json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    with tempfile.TemporaryDirectory(prefix="catalogue-", dir=directory) as temporary:
        candidate = Path(temporary) / "document.json"
        _download(url, candidate, max_bytes=max_bytes, deadline_seconds=90)
        document = json.loads(candidate.read_text())
        os.replace(candidate, path)
    return document


def select_region(index, polygon, region="auto", *, boundary_loader=None):
    """Choose the smallest extract covering the entire AOI, including islands."""
    from shapely.geometry import shape

    if polygon.is_empty or not polygon.is_valid or polygon.geom_type not in {"Polygon", "MultiPolygon"}:
        raise PbfAcquisitionError("PBF acquisition requires a valid WGS84 polygon")
    features = {}
    for feature in index["features"]:
        properties = feature["properties"]
        url = properties.get("urls", {}).get("pbf", "")
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.netloc != "download.geofabrik.de"
                or not url.endswith("-latest.osm.pbf")):
            continue
        features[properties["id"]] = feature

    resolved, visiting = {}, set()
    repairs = 0

    def covering_boundary(identifier):
        nonlocal repairs
        if identifier in resolved:
            return resolved[identifier]
        if identifier in visiting:
            raise PbfAcquisitionError("Cyclic Geofabrik region hierarchy")
        visiting.add(identifier)
        feature = features[identifier]
        properties = feature["properties"]
        boundary = shape(feature.get("geometry") or {"type": "MultiPolygon", "coordinates": []})
        if boundary.is_empty or not boundary.is_valid:
            # Some catalogue entries have empty geometry even while the region's
            # individual GeoJSON is valid. Follow covering ancestors so we only
            # fetch missing boundaries in the relevant part of the world.
            parent = properties.get("parent")
            parent_covers = parent not in features or covering_boundary(parent) is not None
            if boundary_loader is not None and parent_covers:
                repairs += 1
                if repairs > 32:
                    raise PbfAcquisitionError("Too many missing Geofabrik boundaries; pin PBF_REGION")
                url = properties["urls"]["pbf"].removesuffix("-latest.osm.pbf") + ".geojson"
                LOGGER.info("Loading missing Geofabrik boundary for %s", identifier)
                boundary = shape(boundary_loader(url))
        result = boundary if not boundary.is_empty and boundary.is_valid and boundary.covers(polygon) else None
        resolved[identifier] = result
        visiting.remove(identifier)
        return result

    candidates = []
    for identifier, feature in features.items():
        if region != "auto" and identifier != region:
            continue
        boundary = covering_boundary(identifier)
        if boundary is None:
            continue
        if boundary.covers(polygon):
            candidates.append((boundary.area, identifier, feature["properties"]["urls"]["pbf"]))
    if not candidates:
        raise PbfAcquisitionError(f"No Geofabrik region ({region}) covers the complete requested polygon")
    _, identifier, url = min(candidates)
    return identifier, url


def _snapshot_timestamp(path, *, now, max_age_hours, minimum_timestamp):
    import osmium

    with osmium.io.Reader(str(path)) as reader:
        header = reader.header()
        if header.has_multiple_object_versions:
            raise PbfAcquisitionError("History PBF files are not current snapshots")
        timestamp = parse_timestamp(header.get("osmosis_replication_timestamp"))
    if timestamp is None:
        raise PbfAcquisitionError("PBF has no valid replication timestamp")
    if timestamp > now + timedelta(minutes=5):
        raise PbfAcquisitionError("PBF snapshot timestamp is in the future")
    if now - timestamp > timedelta(hours=max_age_hours):
        raise PbfAcquisitionError(f"PBF snapshot is older than {max_age_hours} hours")
    if minimum_timestamp is not None and timestamp < minimum_timestamp:
        raise PbfAcquisitionError(
            "PBF snapshot predates the last successful data acquisition: "
            f"snapshot={isoformat_utc(timestamp)}, minimum={isoformat_utc(minimum_timestamp)}"
        )
    return timestamp


def _cached_snapshot(url, cache_dir, *, max_download_bytes, max_age_hours, minimum_timestamp):
    """Reuse a verified download for up to 24h; replace only after validation."""
    now = datetime.now(timezone.utc)
    stem = hashlib.sha256(url.encode()).hexdigest()[:24]
    pbf = cache_dir / f"{stem}.osm.pbf"
    metadata_path = cache_dir / f"{stem}.json"
    validation = dict(now=now, max_age_hours=max_age_hours, minimum_timestamp=minimum_timestamp)
    try:
        metadata = json.loads(metadata_path.read_text())
        downloaded_at = parse_timestamp(metadata["downloaded_at"])
        if (
            metadata["source_url"] == url
            and downloaded_at is not None
            and timedelta(0) <= now - downloaded_at < timedelta(hours=24)
            and pbf.stat().st_size <= max_download_bytes
        ):
            with pbf.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            if checksum == metadata["sha256"]:
                timestamp = _snapshot_timestamp(pbf, **validation)
                return pbf, timestamp, checksum, True
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        LOGGER.info("Refreshing PBF cache: %s", exc)

    # TemporaryDirectory also cleans up failed or interrupted downloads.
    with tempfile.TemporaryDirectory(prefix="download-", dir=cache_dir) as temporary:
        candidate = Path(temporary) / "snapshot.osm.pbf"
        checksum = _download(url, candidate, max_bytes=max_download_bytes)
        timestamp = _snapshot_timestamp(candidate, **validation)
        metadata = {
            "source_url": url,
            "sha256": checksum,
            "downloaded_at": isoformat_utc(now),
            "snapshot_timestamp": isoformat_utc(timestamp),
        }
        candidate_metadata = Path(temporary) / "snapshot.json"
        candidate_metadata.write_text(json.dumps(metadata, indent=2) + "\n")
        os.replace(candidate, pbf)
        os.replace(candidate_metadata, metadata_path)
    return pbf, timestamp, checksum, False


def _matches(tags, query):
    return any(
        key in tags and (value is True or tags[key] in ([value] if isinstance(value, str) else value))
        for key, value in query.items()
    )


def _write_spatial_subset(source, destination, polygon, tags):
    """Bound memory before OSMnx loads XML, retaining complete intersecting objects.

    Envelopes deliberately over-select: crossing ways and enclosing polygons
    must survive even when no vertex falls within the AOI. OSMnx performs the
    final exact intersection. The compact C++ node index avoids Python objects
    for the coordinates of every referenced node in the regional extract.
    """
    import osmium

    west, south, east, north = polygon.bounds

    def intersects(bounds):
        return bounds is not None and not (
            bounds[2] < west or bounds[0] > east or bounds[3] < south or bounds[1] > north
        )

    def envelope(bounds):
        items = [item for item in bounds if item is not None]
        if not items:
            return None
        return (min(item[0] for item in items), min(item[1] for item in items),
                max(item[2] for item in items), max(item[3] for item in items))

    ways, relations, relation_bounds = {}, {}, {}
    processor = osmium.FileProcessor(source).with_locations()
    with osmium.BackReferenceWriter(destination, ref_src=source, remove_tags=False, relation_depth=5) as writer:
        for item in processor:
            if item.is_node():
                if not item.location.valid():
                    raise PbfAcquisitionError(f"Invalid PBF node {item.id}")
                if _matches(item.tags, tags) and west <= item.lon <= east and south <= item.lat <= north:
                    writer.add(item)
            elif item.is_way():
                if not item.nodes or any(not node.location.valid() for node in item.nodes):
                    raise PbfAcquisitionError(f"Incomplete PBF way {item.id}")
                coordinates = [(node.lon, node.lat) for node in item.nodes]
                bounds = (min(x for x, y in coordinates), min(y for x, y in coordinates),
                          max(x for x, y in coordinates), max(y for x, y in coordinates))
                ways[item.id] = bounds
                if _matches(item.tags, tags) and intersects(bounds):
                    writer.add(item)
            elif item.is_relation():
                members = []
                for member in item.members:
                    if member.type == "n":
                        try:
                            valid = processor.node_location_storage.get(member.ref).valid()
                        except KeyError:
                            valid = False
                        if not valid:
                            raise PbfAcquisitionError(f"Incomplete PBF relation {item.id}")
                    elif member.type == "w" and member.ref not in ways:
                        raise PbfAcquisitionError(f"Incomplete PBF relation {item.id}")
                    else:
                        members.append((member.type, member.ref))
                relations[item.id] = members

        def relation_envelope(identifier, ancestors=frozenset()):
            if identifier in relation_bounds:
                return relation_bounds[identifier]
            if identifier not in relations:
                raise PbfAcquisitionError("Incomplete nested PBF relation")
            if identifier in ancestors or len(ancestors) > 5:
                raise PbfAcquisitionError("Cyclic or excessively nested PBF relation")
            bounds = envelope(
                ways[ref] if kind == "w" else relation_envelope(ref, ancestors | {identifier})
                for kind, ref in relations[identifier]
            )
            relation_bounds[identifier] = bounds
            return bounds

        for identifier in relations:
            relation_envelope(identifier)
        for item in osmium.FileProcessor(source, entities=osmium.osm.RELATION):
            if _matches(item.tags, tags) and intersects(relation_bounds[item.id]):
                writer.add(item)


def features_from_pbf(osmnx, path, polygon, tags, *, temporary_dir=None,
                      spatial_prefilter=False, max_matching_objects=1_000_000):
    """Filter tags, retain full ways/relations, then let OSMnx filter the AOI.

    Filtering by node coordinates first would lose crossing ways and polygons
    enclosing the AOI. OSMnx applies the final geometry intersection instead.
    """
    import osmium

    west, south, east, north = polygon.bounds
    with tempfile.TemporaryDirectory(prefix="features-", dir=temporary_dir) as temporary:
        selected = Path(temporary) / "selected.osm.pbf"
        xml = Path(temporary) / "features.osm"
        count = 0
        processor = osmium.FileProcessor(path)
        if spatial_prefilter:
            # C++ location handling sees all nodes before the tag filter. Only
            # nearby tagged ways/nodes and complete candidate area relations
            # enter BackReferenceWriter, avoiding a huge regional tag subset.
            processor.with_locations()
        processor.with_filter(osmium.filter.KeyFilter(*tags))
        with osmium.BackReferenceWriter(selected, ref_src=path, remove_tags=False, relation_depth=5) as writer:
            for item in processor:
                if not _matches(item.tags, tags):
                    continue
                if item.is_relation() and item.tags.get("type") not in {"multipolygon", "boundary"}:
                    continue
                if spatial_prefilter and item.is_node():
                    if not item.location.valid():
                        raise PbfAcquisitionError(f"Invalid PBF node {item.id}")
                    if not (west <= item.lon <= east and south <= item.lat <= north):
                        continue
                elif spatial_prefilter and item.is_way():
                    if not item.nodes or any(not n.location.valid() for n in item.nodes):
                        raise PbfAcquisitionError(f"Incomplete PBF way {item.id}")
                    coords = [(n.lon, n.lat) for n in item.nodes]
                    if (max(x for x, y in coords) < west or min(x for x, y in coords) > east
                            or max(y for x, y in coords) < south or min(y for x, y in coords) > north):
                        continue
                # Area relations remain candidates even when their rings have
                # no vertices inside the AOI. Reference completion followed by
                # the existing exact spatial pass handles these safely.
                count += 1
                if count > max_matching_objects:
                    raise PbfAcquisitionError("PBF exceeds one million matching objects; use a smaller region")
                writer.add(item)
        # BackReferenceWriter retains its ID tracker after close. Release the
        # regional tracker before constructing the smaller AOI reference set.
        del writer
        del processor
        if not count:
            raise PbfAcquisitionError("No matching features in PBF")
        _write_spatial_subset(selected, xml, polygon, tags)
        features = osmnx.features_from_xml(xml, polygon=polygon, tags=tags)
        if features.empty or features.geometry.isna().any() or features.geometry.is_empty.any():
            raise PbfAcquisitionError("PBF produced empty or incomplete feature geometry")
        return features


def features_from_polygon_pbf(
    osmnx, polygon, tags, *, region="auto", cache_dir=".cache/oswm/pbf",
    max_download_bytes=1024 * 1024 * 1024, max_age_hours=72, minimum_timestamp=None,
):
    """Acquire current features with an auditable source timestamp and checksum."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    identifier, url = select_region(
        _cached_json(INDEX_URL, cache_dir), polygon, region,
        boundary_loader=lambda url: _cached_json(url, cache_dir),
    )
    LOGGER.warning("Overpass unavailable; using Geofabrik PBF region %s", identifier)
    path, timestamp, checksum, cache_hit = _cached_snapshot(
        url, cache_dir, max_download_bytes=max_download_bytes,
        max_age_hours=max_age_hours, minimum_timestamp=minimum_timestamp,
    )
    features = features_from_pbf(osmnx, path, polygon, tags, temporary_dir=cache_dir)
    features.attrs[PROVENANCE_KEY] = {
        "provider": "geofabrik_pbf",
        "region": identifier,
        "source_url": url,
        "snapshot_timestamp": isoformat_utc(timestamp),
        "acquired_at": isoformat_utc(),
        "sha256": checksum,
        "cache_hit": cache_hit,
    }
    return features
