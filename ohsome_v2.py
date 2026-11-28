"""Optional, bounded historical OSM snapshots from the authenticated HeiGIT API."""

from io import BytesIO
import os
import time

import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq
import requests

from time_utils import parse_timestamp

BASE_URL = "https://api.heigit.org/ohsome-api/v2"
FILTERS = (
    "geometry:line and highway in (motorway,trunk,primary,secondary,tertiary,residential,unclassified,"
    "motorway_link,trunk_link,primary_link,secondary_link,tertiary_link)",
    "geometry:line and highway=footway",
    "geometry:line and footway=sidewalk",
)
MAX_LAYER_BYTES = 48 * 1024 * 1024
COLUMNS = ["osm_type", "osm_id", "edit_timestamp", "valid_to_timestamp", "geom"]


class HistoryUnavailable(RuntimeError):
    """A complete, validated history snapshot could not be acquired."""


def _validate_response(response):
    if response.status_code != 200:
        raise HistoryUnavailable(f"OHSOME v2 returned HTTP {response.status_code}; history was not updated.")


def _read_ways(content, requested):
    table = pq.read_table(content, columns=COLUMNS)
    frame = table.to_pandas()
    ways = frame.loc[frame["osm_type"].eq("way")].copy()
    start = pd.to_datetime(ways["edit_timestamp"], utc=True)
    end = pd.to_datetime(ways["valid_to_timestamp"], utc=True)
    if not ((start <= requested) & (requested < end)).all() or ways["osm_id"].isna().any() or ways["osm_id"].duplicated().any():
        raise ValueError("extract does not contain one valid version per way at the requested date")
    geo = gpd.GeoSeries.from_wkb(ways["geom"], crs="EPSG:4326")
    if (geo.isna() | geo.is_empty | ~geo.geom_type.isin(["LineString", "MultiLineString"])).any():
        raise ValueError("extract contains incomplete/nonlinear way geometry")
    return gpd.GeoDataFrame(geometry=geo, crs="EPSG:4326")


def historical_layers(bounds, date, *, session=None, sleep=time.sleep, monotonic=time.monotonic):
    """Fetch three dated city extracts, with no partial output if any fails."""
    key = os.environ.get("OHSOME_API_KEY", "").strip()
    if not key:
        raise HistoryUnavailable("Historical backfill requires OHSOME_API_KEY from HeiGIT.")
    timestamp = f"{date}T00:00:00Z"
    requested = parse_timestamp(timestamp)
    if requested is None:
        raise HistoryUnavailable("Historical date must be a valid UTC date.")
    headers = {"Authorization": key}
    session = session or requests
    deadline = monotonic() + 180
    try:
        with session.get(f"{BASE_URL}/metadata", headers=headers, timeout=(5, 20), allow_redirects=False) as response:
            _validate_response(response)
            extent = response.json()["temporalExtent"]
            earliest, latest = parse_timestamp(extent["start"]), parse_timestamp(extent["end"])
            if not earliest or not latest or not earliest <= requested <= latest:
                raise HistoryUnavailable(f"OHSOME v2 does not cover {date}; history was not updated.")

        layers = []
        for filter_ in FILTERS:
            sleep(4.2)  # Limit calls to fewer than 15/minute; abort if account quota is already used.
            time_left = deadline - monotonic()
            if time_left <= 0:
                raise HistoryUnavailable("Historical backfill exceeded its time budget; history was not updated.")
            content = BytesIO()
            with session.post(f"{BASE_URL}/extraction/features.parquet", headers=headers, json={
                "aoi": list(bounds), "filter": filter_, "time": timestamp, "clip": True,
            }, timeout=(5, min(30, time_left)), stream=True, allow_redirects=False) as response:
                _validate_response(response)
                for chunk in response.iter_content(chunk_size=65536):
                    if monotonic() > deadline or content.tell() + len(chunk) > MAX_LAYER_BYTES:
                        raise HistoryUnavailable("OHSOME v2 extract exceeded its size/time budget; history was not updated.")
                    content.write(chunk)
            content.seek(0)
            layers.append(_read_ways(content, requested))
        return layers
    except (requests.RequestException, ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        raise HistoryUnavailable(f"Invalid or incomplete OHSOME v2 response for {date}; history was not updated.") from None
