"""Bounded, sequence-driven Geofabrik updates of a complete regional PBF.

The cache checkpoint describes source acquisition, not successful publication.
Consumers must compare the resulting city layers with their published inputs on
every invocation, including when a previous build failed after acquisition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlparse

import osmium
import requests

from pbf_acquisition import PbfAcquisitionError, _download
from time_utils import isoformat_utc, parse_timestamp


class ReplicationError(PbfAcquisitionError):
    """No verified, sufficiently fresh replication result is available."""


@dataclass(frozen=True)
class State:
    sequence: int
    timestamp: datetime

    @classmethod
    def parse(cls, text):
        values = dict(line.split("=", 1) for line in text.splitlines()
                      if "=" in line and not line.lstrip().startswith("#"))
        try:
            sequence = int(values["sequenceNumber"])
            stamp = parse_timestamp(values["timestamp"].replace("\\:", ":"))
            if sequence < 0 or stamp is None:
                raise ValueError("invalid state")
        except (KeyError, ValueError) as exc:
            raise ReplicationError("Invalid replication state") from exc
        return cls(sequence, stamp)


def checksum(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_header(path, replication_url):
    with osmium.io.Reader(str(path)) as reader:
        header = reader.header()
        if header.has_multiple_object_versions:
            raise ReplicationError("History files are not replication snapshots")
        try:
            seq = int(header.get("osmosis_replication_sequence_number"))
            stamp = parse_timestamp(header.get("osmosis_replication_timestamp"))
            base = header.get("osmosis_replication_base_url").rstrip("/")
            if stamp is None or seq < 0 or base != replication_url.rstrip("/"):
                raise ValueError("mismatching source")
        except (TypeError, ValueError, AttributeError) as exc:
            raise ReplicationError("PBF replication headers do not match the region") from exc
    return State(seq, stamp)


def sequence_path(sequence):
    if not 0 <= sequence <= 999999999:
        raise ReplicationError("Replication sequence out of range")
    digits = f"{sequence:09d}"
    return "/".join((digits[:3], digits[3:6], digits[6:]))


def source_identity(snapshot_url):
    url = urlparse(snapshot_url)
    if (url.scheme != "https" or url.netloc != "download.geofabrik.de"
            or not url.path.endswith("-latest.osm.pbf") or url.query or url.fragment):
        raise ReplicationError("Expected a public Geofabrik latest snapshot URL")
    return snapshot_url.removesuffix("-latest.osm.pbf") + "-updates"


def semantic_digest(path):
    """Fingerprint ordered OSM objects, not compressed bytes or PBF headers."""
    digest = hashlib.sha256()
    counts = {"n": 0, "w": 0, "r": 0}
    previous = None
    for obj in osmium.FileProcessor(str(path)):
        kind = "n" if obj.is_node() else "w" if obj.is_way() else "r"
        key = ({"n": 0, "w": 1, "r": 2}[kind], obj.id)
        if previous is not None and key <= previous:
            raise ReplicationError("Snapshot objects must be unique and ordered")
        previous = key
        if obj.deleted:
            raise ReplicationError("Current snapshot contains a deleted object")
        if kind == "n":
            geometry = [round(obj.lon * 1e7), round(obj.lat * 1e7)]
        elif kind == "w":
            geometry = [node.ref for node in obj.nodes]
        else:
            geometry = [(member.type, member.ref, member.role) for member in obj.members]
        data = [kind, obj.id, obj.version, str(obj.timestamp),
                sorted((tag.k, tag.v) for tag in obj.tags), geometry]
        digest.update(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode())
        digest.update(b"\n")
        counts[kind] += 1
    if not sum(counts.values()):
        raise ReplicationError("Empty regional snapshot")
    return {"sha256": digest.hexdigest(), "counts": counts}


def sync_source(snapshot_url, cache_dir, *, bootstrap_url=None, target_sequence=None,
                now=None, minimum_timestamp=None, max_age_hours=72,
                max_download_bytes=1024 * 1024 * 1024, max_diffs=100,
                max_diff_bytes=128 * 1024 * 1024, max_elapsed_seconds=1800, fetch=None):
    """Return (PBF path, report), atomically checkpointing a validated source.

    A dated bootstrap URL and target sequence allow reproducible historical
    replay. They never disable freshness or the published-data regression guard.
    Missing diffs/caches recover by a new validated snapshot. Other errors retain
    the previous pointer and propagate. The single-writer lock covers promotion.
    """
    fetch = fetch or _download
    now = now or datetime.now(timezone.utc)
    base = source_identity(snapshot_url)
    if bootstrap_url is not None:
        stem = snapshot_url.removesuffix("-latest.osm.pbf")
        suffix = bootstrap_url.removeprefix(stem + "-").removesuffix(".osm.pbf")
        if bootstrap_url != snapshot_url and (len(suffix) != 6 or not suffix.isdigit()
                                               or bootstrap_url != f"{stem}-{suffix}.osm.pbf"):
            raise ReplicationError("Bootstrap URL must belong to the same Geofabrik region")
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    downloaded = []

    def download(url, destination, max_bytes):
        for attempt in range(2):
            if time.monotonic() - started > max_elapsed_seconds:
                raise ReplicationError("Replication elapsed-time budget exceeded")
            try:
                digest = fetch(url, destination, max_bytes=max_bytes)
                downloaded.append({"url": url, "bytes": destination.stat().st_size, "sha256": digest})
                return digest
            except requests.RequestException as exc:
                if (isinstance(exc, requests.HTTPError) and exc.response is not None
                        and exc.response.status_code == 404) or attempt:
                    raise
        raise AssertionError("unreachable")

    with (cache / ".lock").open("w") as lock, tempfile.TemporaryDirectory(dir=cache, prefix="candidate-") as temp:
        fcntl.flock(lock, fcntl.LOCK_EX)
        work = Path(temp)

        def state(sequence=None):
            url = f"{base}/" + ("state.txt" if sequence is None else sequence_path(sequence) + ".state.txt")
            destination = work / "state.txt"
            download(url, destination, 65536)
            result = State.parse(destination.read_text())
            if sequence is not None and result.sequence != sequence:
                raise ReplicationError("State sequence does not match its requested file")
            if result.timestamp > now + timedelta(minutes=5):
                raise ReplicationError("Replication state is in the future")
            return result

        latest = state()
        target = latest if target_sequence is None else state(target_sequence)
        if target.sequence > latest.sequence:
            raise ReplicationError("Target sequence has not been published")
        original = None
        recovery = None
        try:
            manifest = json.loads((cache / "current.json").read_text())
            name = manifest["file"]
            if Path(name).name != name or manifest["replication_url"] != base:
                raise ValueError("cache source mismatch")
            original = cache / name
            source_state = read_header(original, base)
            if (source_state.sequence != manifest["sequence"]
                    or isoformat_utc(source_state.timestamp) != manifest["snapshot_timestamp"]
                    or checksum(original) != manifest["sha256"]):
                raise ValueError("cache checkpoint mismatch")
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            recovery = f"bootstrap: {type(exc).__name__}"
            original = None

        start_state = source_state if original else None
        candidate = work / "updated.osm.pbf"

        def bootstrap():
            path = work / "bootstrap.osm.pbf"
            if path.exists():
                path.unlink()
            download(bootstrap_url or snapshot_url, path, max_download_bytes)
            initial = read_header(path, base)
            if initial.timestamp > now + timedelta(minutes=5):
                raise ReplicationError("Snapshot timestamp is in the future")
            return path, initial

        source, source_state = (original, source_state) if original else bootstrap()
        if source_state.sequence > target.sequence:
            raise ReplicationError("Snapshot/cache is newer than the pinned target; retry with a current target")
        if target.sequence - source_state.sequence > max_diffs:
            recovery = "bootstrap: catch-up range exceeded"
            source, source_state = bootstrap()
        changes = []
        previous = source_state
        total_diff_bytes = 0
        expanded = 0
        try:
            for seq in range(source_state.sequence + 1, target.sequence + 1):
                if seq - source_state.sequence > max_diffs:
                    raise ReplicationError("Catch-up range exceeded after bootstrap")
                next_state = state(seq)
                if next_state.timestamp < previous.timestamp:
                    raise ReplicationError("Replication timestamp regressed")
                diff = work / f"{seq}.osc.gz"
                download(f"{base}/{sequence_path(seq)}.osc.gz", diff, max_diff_bytes - total_diff_bytes)
                total_diff_bytes += diff.stat().st_size
                # Bound decompression before allowing the C++ merge to load it.
                with gzip.open(diff, "rb") as stream:
                    while block := stream.read(1024 * 1024):
                        expanded += len(block)
                        if expanded > 512 * 1024 * 1024:
                            raise ReplicationError("Expanded change file exceeds memory budget")
                changes.append(diff)
                previous = next_state
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
            recovery = "bootstrap: required diff unavailable"
            source, source_state = bootstrap()
            changes = []
            if source_state != target:
                raise ReplicationError("Recovery snapshot does not match the pinned target") from exc

        if source_state.sequence > target.sequence:
            raise ReplicationError("Recovery snapshot exceeds target")
        if changes:
            reader = osmium.MergeInputReader()
            for diff in changes:
                reader.add_file(str(diff))
            header = osmium.io.Header()
            header.set("osmosis_replication_base_url", base)
            header.set("osmosis_replication_sequence_number", str(target.sequence))
            header.set("osmosis_replication_timestamp", isoformat_utc(target.timestamp))
            with osmium.io.Reader(str(source)) as baseline:
                writer = osmium.io.Writer(str(candidate), header)
                try:
                    reader.apply_to_reader(baseline, writer)
                finally:
                    writer.close()
            result = candidate
        else:
            result = source
        actual = read_header(result, base)
        if result.stat().st_size > max_download_bytes:
            raise ReplicationError("Updated snapshot exceeds regional size budget")
        if actual != target:
            raise ReplicationError("Result does not match target sequence and timestamp")
        if now - actual.timestamp > timedelta(hours=max_age_hours):
            raise ReplicationError(f"Result is older than {max_age_hours} hours")
        lower_bound = max(t for t in [minimum_timestamp, start_state.timestamp if start_state else None]
                          if t is not None) if minimum_timestamp or start_state else None
        if lower_bound is not None and actual.timestamp < lower_bound:
            raise ReplicationError("Result predates the last successful acquisition")
        # Let the C++ decoder validate the file without Python serialization of
        # every regional object. Semantic parity is a separate preview check.
        if result != original:
            with osmium.io.Reader(str(result)) as validation_reader:
                osmium.apply(validation_reader, osmium.filter.EntityFilter(osmium.osm.OBJECT))
        sha = checksum(result)
        filename = f"source-{actual.sequence}-{sha[:16]}.osm.pbf"
        destination = cache / filename
        if result != destination:
            os.replace(result, destination)
        manifest = {"schema_version": 1, "file": filename, "source_url": snapshot_url,
                    "replication_url": base, "sequence": actual.sequence,
                    "snapshot_timestamp": isoformat_utc(actual.timestamp), "sha256": sha}
        pointer = work / "current.json"
        pointer.write_text(json.dumps(manifest, indent=2) + "\n")
        os.replace(pointer, cache / "current.json")
        for old in cache.glob("source-*.osm.pbf"):
            if old != destination:
                old.unlink()
        return destination, {
            **manifest, "provider": "geofabrik_replication", "checked_at": isoformat_utc(now),
            "from_sequence": start_state.sequence if start_state else None,
            "diffs_applied": len(changes), "recovery": recovery,
            "freshness_warning": now - actual.timestamp > timedelta(hours=48),
            "downloads": downloaded, "download_bytes": sum(x["bytes"] for x in downloaded),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
