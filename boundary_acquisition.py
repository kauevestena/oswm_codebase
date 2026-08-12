"""Deterministic and bounded Nominatim boundary acquisition."""

from __future__ import annotations

import copy
import time
from typing import Any, Callable

import requests


DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org"
POLYGON_TYPES = {"Polygon", "MultiPolygon"}


class BoundaryAcquisitionError(RuntimeError):
    """Raised when no valid administrative polygon can be acquired."""


def _request_json(
    url: str,
    *,
    params: dict[str, Any],
    user_agent: str,
    timeout_seconds: float,
    attempts: int,
    backoff_seconds: float,
    request_get: Callable[..., Any],
    sleep: Callable[[float], None],
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            response = request_get(
                url,
                params=params,
                headers={"User-Agent": user_agent},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("Nominatim returned a non-list payload")
            return payload
        except (requests.RequestException, ValueError, TypeError) as exc:
            last_error = exc
            if attempt + 1 < max(1, attempts):
                sleep(backoff_seconds * (2**attempt))
    raise BoundaryAcquisitionError(f"Nominatim request failed: {last_error}")


def _polygon_candidates(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    polygons = [
        item
        for item in results
        if item.get("geojson", {}).get("type") in POLYGON_TYPES
    ]
    return sorted(
        polygons,
        key=lambda item: (
            item.get("class") == "boundary"
            and item.get("type") == "administrative",
            float(item.get("importance") or 0),
        ),
        reverse=True,
    )


def resolve_boundary(
    place_name: str,
    *,
    relation_id: int | str | None = None,
    base_url: str = DEFAULT_NOMINATIM_URL,
    user_agent: str = "OpenSidewalkMap/1.0 (https://github.com/kauevestena/oswm_codebase)",
    timeout_seconds: float = 30,
    attempts: int = 3,
    backoff_seconds: float = 2,
    request_get: Callable[..., Any] = requests.get,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a polygon and metadata, preferring an exact OSM relation ID."""

    base = base_url.rstrip("/")
    if relation_id is not None:
        results = _request_json(
            f"{base}/lookup",
            params={
                "osm_ids": f"R{int(relation_id)}",
                "format": "jsonv2",
                "polygon_geojson": 1,
            },
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            attempts=attempts,
            backoff_seconds=backoff_seconds,
            request_get=request_get,
            sleep=sleep,
        )
        candidates = _polygon_candidates(results)
        if not candidates:
            raise BoundaryAcquisitionError(
                f"OSM relation {relation_id} did not resolve to a polygon"
            )
    else:
        results = _request_json(
            f"{base}/search",
            params={
                "q": place_name,
                "format": "jsonv2",
                "polygon_geojson": 1,
                "addressdetails": 1,
                "limit": 10,
            },
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            attempts=attempts,
            backoff_seconds=backoff_seconds,
            request_get=request_get,
            sleep=sleep,
        )
        candidates = _polygon_candidates(results)
        if not candidates:
            raise BoundaryAcquisitionError(
                f"No Polygon or MultiPolygon result found for {place_name!r}"
            )

    selected = copy.deepcopy(candidates[0])
    geometry = selected.pop("geojson")
    selected["selection"] = (
        "exact_relation" if relation_id is not None else "ranked_polygon_search"
    )
    selected["requested_place"] = place_name
    if relation_id is not None:
        selected["requested_relation_id"] = int(relation_id)
    return geometry, selected
