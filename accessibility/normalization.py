"""Normalize OSM accessibility evidence once for routing and hazard analysis."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


UNKNOWN_STRINGS = {"", "?", "unknown", "unset", "none", "null", "nan"}
_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)")


def is_unknown(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in UNKNOWN_STRINGS
    try:
        return bool(math.isnan(value))
    except (TypeError, ValueError):
        value_type = type(value)
        return (
            value_type.__name__ in {"NAType", "NaTType"}
            and value_type.__module__.startswith("pandas")
        )


def normalize_categorical(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def normalize_sequence(value: Any) -> list[Any]:
    if is_unknown(value):
        return []
    if isinstance(value, str):
        return [normalize_categorical(value)]
    if isinstance(value, Sequence):
        return [
            normalize_categorical(item)
            for item in value
            if not is_unknown(item)
        ]
    return [normalize_categorical(value)]


def parse_number(value: Any) -> float | None:
    """Parse the first finite number from a permissive OSM-style value."""

    if is_unknown(value) or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    match = _NUMBER_RE.search(str(value))
    if not match:
        return None
    try:
        number = float(match.group(0).replace(",", "."))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def parse_width_m(value: Any) -> float | None:
    """Parse common OSM width forms into metres."""

    if is_unknown(value):
        return None
    text = str(value).strip().lower()
    if ";" in text:
        parsed = [parse_width_m(part) for part in text.split(";")]
        valid = [item for item in parsed if item is not None]
        return min(valid) if valid else None

    feet_match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*'\s*(?:(\d+(?:\.\d+)?)\s*(?:\"|in)?)?\s*",
        text,
    )
    if feet_match:
        feet = float(feet_match.group(1))
        inches = float(feet_match.group(2) or 0)
        return feet * 0.3048 + inches * 0.0254

    number = parse_number(value)
    if number is None:
        return None
    if "ft" in text or "feet" in text:
        return number * 0.3048
    if "cm" in text:
        return number / 100
    if "mm" in text:
        return number / 1000
    return number


def parse_incline_percent(value: Any) -> tuple[float | None, str]:
    """Return ``(percent, kind)`` for an OSM incline-like value."""

    if is_unknown(value):
        return None, "missing"
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"up", "uphill", "down", "downhill"}:
            return None, "qualitative"
    else:
        text = str(value)

    number = parse_number(value)
    if number is None:
        return None, "invalid"
    if "°" in text or "deg" in text or "degree" in text:
        return math.tan(math.radians(number)) * 100, "numeric"
    return number, "numeric"


def _normalize_transition_states(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    normalized = []
    for state in value:
        if not isinstance(state, Mapping):
            continue
        normalized.append(
            {
                key: normalize_categorical(item)
                for key, item in state.items()
                if not is_unknown(item)
            }
        )
    return normalized


def prepare_feature(
    feature: Mapping[str, Any],
    *,
    edge_kind: str | None = None,
    estimated_slope_percent: float | None = None,
    slope_source: str = "missing",
    slope_confidence: int = 0,
) -> dict[str, Any]:
    """Normalize raw edge evidence for every accessibility consumer."""

    prepared = dict(feature)
    prepared["edge_kind"] = edge_kind or prepared.get("edge_kind") or "footway"
    prepared["width_m"] = parse_width_m(prepared.get("width"))

    direct_slope, incline_kind = parse_incline_percent(prepared.get("incline"))
    if direct_slope is not None:
        prepared["incline_percent"] = direct_slope
        prepared["incline_source"] = "direct_osm_numeric"
        prepared["incline_confidence"] = 100
    else:
        prepared["incline_percent"] = estimated_slope_percent
        prepared["incline_source"] = (
            slope_source if estimated_slope_percent is not None else incline_kind
        )
        prepared["incline_confidence"] = (
            int(slope_confidence) if estimated_slope_percent is not None else 0
        )

    cross_slope, cross_kind = parse_incline_percent(
        prepared.get("incline:across")
    )
    prepared["cross_slope_percent"] = cross_slope
    prepared["cross_slope_source"] = (
        "direct_osm_numeric" if cross_slope is not None else cross_kind
    )
    prepared["cross_slope_confidence"] = 100 if cross_slope is not None else 0

    for field in (
        "surface",
        "smoothness",
        "wheelchair",
        "crossing",
        "tactile_paving",
        "kerb",
        "lit",
        "highway",
        "access",
        "foot",
    ):
        prepared[field] = normalize_categorical(prepared.get(field))

    for field in (
        "associated_kerbs",
        "associated_tactile_paving",
        "associated_kerb_surfaces",
        "associated_sidewalk_surfaces",
    ):
        prepared[field] = normalize_sequence(prepared.get(field))

    transitions = _normalize_transition_states(
        prepared.get("associated_transition_states")
    )
    prepared["associated_transition_states"] = transitions

    crossing_surface = prepared.get("surface")
    prepared["uniform_transition_surface"] = bool(
        prepared["edge_kind"] == "crossing"
        and not is_unknown(crossing_surface)
        and any(
            not is_unknown(state.get("kerb_surface"))
            and not is_unknown(state.get("sidewalk_surface"))
            and crossing_surface == state.get("kerb_surface")
            == state.get("sidewalk_surface")
            for state in transitions
        )
    )
    return prepared
