"""Instrumented Overture bbox/row-group reads; no node writes or publication.

This deliberately reads all columns of intersecting row groups. It reports
actual transferred ranges, not the much smaller exported file size, and is not
a claim of the minimum possible bandwidth of an optimized projected query.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import time
import traceback

import pyarrow.compute as pc
import pyarrow.parquet as pq
import requests
from shapely import from_wkb
from shapely.geometry import shape

AGENT = "OpenSidewalkMap-Sandbox/1.0 (https://github.com/kauevestena/oswm_codebase/pull/62)"
ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified"}
WALK_CLASSES = {"footway", "steps", "living_street", "pedestrian", "track", "path"}
KERBS = {"lowered", "raised", "flush", "rolled", "no", "yes"}


class Transport:
    def __init__(self, max_bytes=1024**3):
        self.events = []
        self.total = 0
        self.max_bytes = max_bytes
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": AGENT, "Accept-Encoding": "identity"})

    def get(self, url, start=None, end=None):
        headers = {"Range": f"bytes={start}-{end - 1}"} if start is not None else {}
        if len(self.events) > 2000:
            raise ValueError("HTTP request budget exhausted")
        if start is not None and (end - start > 128 * 1024**2 or self.total + end - start > self.max_bytes):
            raise ValueError("Range transfer budget exceeded")
        event = {"url": url, "range_start": start, "range_end_exclusive": end}
        self.events.append(event)
        began = time.monotonic()
        try:
            with self.session.get(url, headers=headers, stream=True, timeout=(15, 60)) as response:
                event["status"] = response.status_code
                response.raise_for_status()
                if start is not None and response.status_code != 206:
                    raise ValueError("Server ignored a bounded Range request")
                data = response.content
                event.update({"body_bytes": len(data), "seconds": round(time.monotonic() - began, 3),
                              "sha256": hashlib.sha256(data).hexdigest(),
                              "content_range": response.headers.get("Content-Range")})
                self.total += len(data)
                if self.total > self.max_bytes:
                    raise ValueError("Total transfer budget exceeded")
                if start is not None and len(data) != end - start:
                    raise ValueError("Truncated range response")
                if start is not None and not (response.headers.get("Content-Range") or "").startswith(f"bytes {start}-{end - 1}/"):
                    raise ValueError("Range response offsets do not match the request")
                return data
        except Exception as exc:
            event["error"] = str(exc)
            raise


class RangeFile(io.RawIOBase):
    def __init__(self, transport, url, size):
        self.transport, self.url, self.size = transport, url, size
        self.position = 0
        self.metadata_blocks = []
        self.data_block = None

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position

    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        if not 0 <= self.position <= self.size:
            raise ValueError("Seek outside object")
        return self.position

    def prefetch(self, start, end):
        data = self.transport.get(self.url, start, end)
        self.data_block = start, data

    def read(self, count=-1):
        if count < 0:
            count = self.size - self.position
        end = min(self.size, self.position + count)
        if end == self.position:
            return b""
        for start, data in ([self.data_block] if self.data_block else []) + self.metadata_blocks:
            if start <= self.position and end <= start + len(data):
                output = data[self.position - start:end - start]
                self.position = end
                return output
        start = self.position
        output = self.transport.get(self.url, start, end)
        if len(output) <= 2 * 1024**2:
            self.metadata_blocks.append((start, output))
        self.position = end
        return output

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)


def overlaps(bounds, box):
    return bounds[0] <= box[2] and bounds[2] >= box[0] and bounds[1] <= box[3] and bounds[3] >= box[1]


def group_overlaps(group, box):
    stats = {}
    for i in range(group.num_columns):
        col = group.column(i)
        if col.path_in_schema in {"bbox.xmin", "bbox.ymin", "bbox.xmax", "bbox.ymax"}:
            if col.statistics and col.statistics.has_min_max:
                stats[col.path_in_schema] = col.statistics
    if len(stats) != 4:
        return True  # cannot prune without a complete enclosing bbox
    bounds = [stats["bbox.xmin"].min, stats["bbox.ymin"].min,
              stats["bbox.xmax"].max, stats["bbox.ymax"].max]
    return overlaps(bounds, box)


def source_ids(row):
    result = set()
    for source in row.get("sources") or []:
        if source.get("dataset") != "OpenStreetMap":
            continue
        if source.get("property") not in (None, "", "/geometry", "geometry"):
            continue  # route/name attribute provenance is not feature identity
        identifier = source.get("record_id") or ""
        match = re.match(r"^([nwr])(\d+)(?:@\d+)?$", identifier)
        if match:
            result.add({"n": "node", "w": "way", "r": "relation"}[match[1]] + ":" + match[2])
    return result


def analyze(row, typ, boundary, summary, ids, config):
    geometry = from_wkb(row["geometry"])
    if geometry is None or geometry.is_empty:
        summary["invalid_or_empty_geometry"] += 1
        return
    inside = geometry.intersects(boundary)
    original = source_ids(row)
    ids["_all_bbox_provenance"].update(original)
    if inside:
        ids["_all_city_provenance"].update(original)
    for source in row.get("sources") or []:
        if source.get("dataset") == "OpenStreetMap" and source.get("property") in (None, "", "/geometry", "geometry"):
            summary["osm_source_versions"][str(source.get("version"))] += 1
    cls = row.get("class")
    summary["classes"][str(cls)] += 1
    tags = row.get("source_tags") or {}
    if isinstance(tags, list):
        tags = dict(tags)
    for name in ("kerb", "barrier", "wheelchair", "tactile_paving", "kerb:height", "surface", "smoothness", "width", "incline"):
        if tags.get(name) is not None:
            summary["source_tag_coverage"][name] += 1
            summary["source_tag_values"].setdefault(name, Counter())[str(tags[name])] += 1
    categories = set()
    if typ == "segment" and row.get("subtype") == "road":
        if cls in ROAD_CLASSES:
            categories.add("roads_for_completeness")
        if inside:
            subclasses = {rule.get("value") for rule in row.get("subclass_rules") or []}
            if row.get("subclass"):
                subclasses.add(row["subclass"])
            if cls == "footway" and "sidewalk" in subclasses:
                categories.add("sidewalks")
            if cls == "footway" and "crosswalk" in subclasses:
                categories.add("crossings")
            if cls in WALK_CLASSES and not {"sidewalks", "crossings"} & categories:
                categories.add("other_footways")
    elif typ == "infrastructure" and inside:
        if cls == "kerb":
            summary["class_kerb_count"] += 1
        excluded = any(tags.get(k) in v for k, v in config["OTHER_FOOTWAY_EXCLUSION_RULES"].items())
        if not excluded:
            if cls == "kerb" or tags.get("kerb") in KERBS or tags.get("barrier") == "kerb":
                categories.add("kerbs")
            elif tags.get("footway") == "sidewalk":
                categories.add("sidewalks")
            elif tags.get("footway") == "crossing":
                categories.add("crossings")
            elif any(tags.get(k) in v for k, v in config["OTHER_FOOTWAY_RULES"].items()):
                categories.add("other_footways")
        if cls in {"crossing", "pedestrian_crossing"}:
            summary["crossing_infrastructure_points_or_features"] += 1
    for category in categories:
        summary["candidate_category_features"][category] += 1
        ids[category].update(original)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", choices=["curitiba", "milan"], required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--release", default="2026-10-21.0")
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    if work.exists() and any(work.iterdir()):
        raise ValueError("Use a new empty sandbox")
    work.mkdir(parents=True, exist_ok=True)
    boundary_json = json.loads(args.boundary.read_text())
    config = {}
    exec(compile(args.config.read_text(), str(args.config), "exec"), config)
    from shapely.ops import unary_union
    if boundary_json["type"] == "FeatureCollection":
        boundary = unary_union([shape(f["geometry"]) for f in boundary_json["features"]])
    elif boundary_json["type"] == "Feature":
        boundary = shape(boundary_json["geometry"])
    else:
        boundary = shape(boundary_json)
    bbox = boundary.bounds
    transport = Transport()
    report = {"sandbox_only": True, "city": args.city, "release": args.release,
              "started_at": datetime.now(timezone.utc).isoformat(), "bbox": list(bbox),
              "reader": "instrumented HTTPS ranges; STAC file selection and row-group bbox pruning; all columns",
              "measurement": "encoded response bodies only; includes STAC and Parquet metadata/spillover; excludes HTTP/TLS headers",
              "caveat": "candidate schema coverage, not same-date or one-to-one OSWM feature parity",
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
              "types": {}}
    ids = defaultdict(set)
    def save():
        report["http"] = {"requests": len(transport.events), "body_bytes": transport.total, "events": transport.events}
        (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    try:
        catalog = json.loads(transport.get("https://stac.overturemaps.org/catalog.json"))
        report["latest_release_at_test"] = catalog.get("latest")
        data = transport.get(f"https://stac.overturemaps.org/{args.release}/collections.parquet")
        metadata = pq.ParquetFile(io.BytesIO(data)).read(use_threads=False).to_pylist()
        for typ in ("segment", "connector", "infrastructure"):
            began = time.monotonic()
            start_bytes, start_events = transport.total, len(transport.events)
            selected = [r for r in metadata if r["type"] == "Feature" and r["collection"] == typ
                        and overlaps([r["bbox"][k] for k in ("xmin", "ymin", "xmax", "ymax")], bbox)]
            summary = {"stac_files": len(selected), "files": [], "rows_in_downloaded_groups": 0,
                       "bbox_features": 0, "invalid_or_empty_geometry": 0, "classes": Counter(),
                       "osm_source_versions": Counter(),
                       "source_tag_coverage": Counter(), "source_tag_values": {}, "candidate_category_features": Counter(),
                       "class_kerb_count": 0, "crossing_infrastructure_points_or_features": 0}
            report["types"][typ] = summary
            writer = None
            try:
                for item in selected:
                    asset = item["assets"]["aws"]
                    raw = RangeFile(transport, asset["href"], asset["file:size"])
                    parquet = pq.ParquetFile(raw)
                    info = {"url": asset["href"], "object_bytes": asset["file:size"],
                            "row_groups_total": parquet.num_row_groups, "row_groups_selected": [],
                            "columns": parquet.schema_arrow.names}
                    summary["files"].append(info)
                    print(json.dumps({"city": args.city, "type": typ, "phase": "file metadata", "row_groups": parquet.num_row_groups}), flush=True)
                    for index in range(parquet.num_row_groups):
                        group = parquet.metadata.row_group(index)
                        if not group_overlaps(group, bbox):
                            continue
                        info["row_groups_selected"].append(index)
                        spans = []
                        for col in range(group.num_columns):
                            column = group.column(col)
                            starts = [n for n in (column.dictionary_page_offset, column.data_page_offset) if n is not None and n > 0]
                            start = min(starts)
                            spans.append((start, start + column.total_compressed_size))
                        raw.prefetch(min(s[0] for s in spans), max(s[1] for s in spans))
                        table = parquet.read_row_group(index, use_threads=False)
                        summary["rows_in_downloaded_groups"] += table.num_rows
                        coords = table.column("bbox")
                        conditions = [pc.less_equal(pc.struct_field(coords, "xmin"), bbox[2]),
                                      pc.greater_equal(pc.struct_field(coords, "xmax"), bbox[0]),
                                      pc.less_equal(pc.struct_field(coords, "ymin"), bbox[3]),
                                      pc.greater_equal(pc.struct_field(coords, "ymax"), bbox[1])]
                        mask = conditions[0]
                        for condition in conditions[1:]: mask = pc.and_kleene(mask, condition)
                        filtered = table.filter(mask)
                        summary["bbox_features"] += filtered.num_rows
                        if writer is None:
                            writer = pq.ParquetWriter(work / f"{typ}.parquet", filtered.schema, compression="zstd")
                        writer.write_table(filtered)
                        for row in filtered.to_pylist():
                            analyze(row, typ, boundary, summary, ids, config)
                        del table, filtered
                    parquet.close()
                    raw.close()
            finally:
                if writer is not None: writer.close()
            summary.update({"body_bytes": transport.total - start_bytes, "http_requests": len(transport.events) - start_events,
                            "seconds": round(time.monotonic() - began, 3),
                            "export_bytes": (work / f"{typ}.parquet").stat().st_size if writer else 0})
            save()
            print(json.dumps({"city": args.city, "type": typ, "phase": "complete",
                              **{k: summary[k] for k in ("body_bytes", "bbox_features", "candidate_category_features")}}), flush=True)
        report["candidate_unique_osm_ids"] = {k: len(v) for k, v in ids.items()}
        with gzip.open(work / "candidate-osm-ids.json.gz", "wt") as stream:
            json.dump({k: sorted(v) for k, v in ids.items()}, stream)
        report["success"] = True
    except Exception:
        report["fatal_error"] = traceback.format_exc()
        report["success"] = False
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
        print("OVERTURE_PROBE_REPORT=" + json.dumps(report), flush=True)


if __name__ == "__main__": main()
