"""Bounded provider failover for OSMnx/Overpass and regional PBF acquisitions."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any


DEFAULT_OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
)


class OverpassAcquisitionError(RuntimeError):
    """Raised after every configured provider and retry is exhausted."""


def features_from_polygon_with_failover(
    osmnx: Any,
    polygon: Any,
    tags: dict[str, Any],
    *,
    endpoints: Iterable[str] = DEFAULT_OVERPASS_ENDPOINTS,
    attempts_per_endpoint: int = 2,
    backoff_seconds: float = 5,
    sleep: Callable[[float], None] = time.sleep,
    pbf_options: dict[str, Any] | None = None,
) -> Any:
    """Try Overpass endpoints, then an optional independent Geofabrik snapshot."""

    configured = tuple(str(item).rstrip("/") for item in endpoints if str(item))
    if not configured:
        raise ValueError("At least one Overpass endpoint must be configured")

    previous_url = getattr(osmnx.settings, "overpass_url", None)
    failures: list[str] = []
    try:
        for endpoint in configured:
            osmnx.settings.overpass_url = endpoint
            for attempt in range(max(1, attempts_per_endpoint)):
                try:
                    return osmnx.features_from_polygon(polygon, tags)
                except Exception as exc:  # OSMnx exposes several provider errors
                    failures.append(
                        f"{endpoint} attempt {attempt + 1}: {type(exc).__name__}: {exc}"
                    )
                    if attempt + 1 < max(1, attempts_per_endpoint):
                        sleep(backoff_seconds * (2**attempt))
    finally:
        if previous_url is not None:
            osmnx.settings.overpass_url = previous_url
    if pbf_options is not None:
        from pbf_acquisition import features_from_polygon_pbf

        try:
            return features_from_polygon_pbf(osmnx, polygon, tags, **pbf_options)
        except Exception as exc:
            failures.append(f"Geofabrik PBF: {type(exc).__name__}: {exc}")
    raise OverpassAcquisitionError("; ".join(failures))
