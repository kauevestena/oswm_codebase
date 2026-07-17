"""Generate whole-node statistics for printable Webmap scrutiny snapshots.

Pure aggregation helpers intentionally avoid importing the node configuration at
module import time.  This keeps them easy to unit-test outside a full OSWM node.
The CLI entry point imports the node-aware modules only when it is executed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping, Sequence


UNKNOWN_VALUE = "?"


def json_scalar(value: Any) -> Any:
    """Convert NumPy/Pandas-like scalars into JSON-safe native scalars."""

    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def normalize_unknown(value: Any, unknown_value: str = UNKNOWN_VALUE) -> Any:
    """Normalize missing values without treating numeric zero as missing."""

    value = json_scalar(value)
    if value is None:
        return unknown_value
    try:
        if value != value:  # NaN and pandas.NA-like values
            return unknown_value
    except (TypeError, ValueError):
        return unknown_value
    if isinstance(value, str):
        value = value.strip()
        if not value or value == unknown_value:
            return unknown_value
    return value


def _rounded(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _diversity(counts: Mapping[str, int]) -> tuple[float, float]:
    total = sum(counts.values())
    if total == 0:
        return 0.0, 0.0
    entropy = -sum(
        (count / total) * math.log(count / total)
        for count in counts.values()
        if count
    )
    return _rounded(entropy), _rounded(math.exp(entropy))


def categorical_summary(
    values: Iterable[Any],
    *,
    colors: Mapping[str, str] | None = None,
    other_color: str = "#777777",
    unknown_value: str = UNKNOWN_VALUE,
    weights_km: Iterable[float | None] | None = None,
) -> dict[str, Any]:
    """Summarize categories, separating incompleteness from heterogeneity."""

    normalized = [normalize_unknown(value, unknown_value) for value in values]
    total = len(normalized)
    unknown_count = sum(value == unknown_value for value in normalized)
    known_values = [value for value in normalized if value != unknown_value]
    raw_counts = Counter(str(value) for value in known_values)
    ordered_counts = sorted(raw_counts.items(), key=lambda item: (-item[1], item[0]))
    known_count = len(known_values)
    entropy, effective_diversity = _diversity(raw_counts)
    colors = colors or {}

    categories = [
        {
            "value": value,
            "count": int(count),
            "percent": _rounded(100 * count / known_count, 2) if known_count else 0.0,
            "color": colors.get(value, other_color),
        }
        for value, count in ordered_counts
    ]

    result: dict[str, Any] = {
        "kind": "categorical",
        "total": total,
        "known": known_count,
        "unknown": unknown_count,
        "unknownPercent": _rounded(100 * unknown_count / total, 2) if total else 0.0,
        "knownCategoryCount": len(categories),
        "categories": categories,
        "dominant": categories[0] if categories else None,
        "shannonEntropy": entropy,
        "effectiveDiversity": effective_diversity,
    }

    if weights_km is not None:
        lengths: defaultdict[str, float] = defaultdict(float)
        weighted_feature_count = 0
        for value, weight in zip(normalized, weights_km):
            if weight is None:
                continue
            weight = float(weight)
            if not math.isfinite(weight):
                continue
            lengths[str(value)] += weight
            weighted_feature_count += 1
        if weighted_feature_count:
            result["lengthFeatureCount"] = weighted_feature_count
            result["totalLengthKm"] = _rounded(sum(lengths.values()))
            result["unknownLengthKm"] = _rounded(lengths.get(unknown_value, 0.0))
            result["lengthKmByCategory"] = {
                value: _rounded(lengths.get(value, 0.0)) for value, _ in ordered_counts
            }

    return result


def _is_invalid(value: float, invalid: Mapping[str, Any] | None) -> bool:
    if not invalid:
        return False
    threshold = float(invalid.get("threshold", 0))
    operator = invalid.get("operator", "<")
    operations = {
        "<": value < threshold,
        "<=": value <= threshold,
        ">": value > threshold,
        ">=": value >= threshold,
    }
    return operations.get(operator, False)


def numeric_summary(
    values: Iterable[Any],
    *,
    breaks: Sequence[float],
    colors: Sequence[str],
    invalid: Mapping[str, Any] | None = None,
    unknown_value: str = UNKNOWN_VALUE,
) -> dict[str, Any]:
    """Summarize numeric values using the exact MapLibre class breaks."""

    normalized = [normalize_unknown(value, unknown_value) for value in values]
    valid: list[float] = []
    invalid_count = 0
    unknown_count = 0
    for value in normalized:
        if value == unknown_value:
            unknown_count += 1
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            unknown_count += 1
            continue
        if not math.isfinite(number):
            unknown_count += 1
        elif _is_invalid(number, invalid):
            invalid_count += 1
        else:
            valid.append(number)

    numeric_breaks = [float(value) for value in breaks]
    bin_counts = [0 for _ in numeric_breaks]
    for value in valid:
        index = 0
        for candidate_index, lower_bound in enumerate(numeric_breaks):
            if value >= lower_bound:
                index = candidate_index
            else:
                break
        bin_counts[index] += 1

    bins = []
    for index, lower_bound in enumerate(numeric_breaks):
        upper_bound = (
            numeric_breaks[index + 1] if index + 1 < len(numeric_breaks) else None
        )
        label = (
            f"{lower_bound:g}–<{upper_bound:g}"
            if upper_bound is not None
            else f"{lower_bound:g}+"
        )
        bins.append(
            {
                "label": label,
                "lower": lower_bound,
                "upper": upper_bound,
                "count": bin_counts[index],
                "color": colors[index] if index < len(colors) else "#777777",
            }
        )

    return {
        "kind": "numeric",
        "total": len(normalized),
        "known": len(valid),
        "unknown": unknown_count,
        "unknownPercent": _rounded(100 * unknown_count / len(normalized), 2)
        if normalized
        else 0.0,
        "invalid": invalid_count,
        "min": _rounded(min(valid)) if valid else None,
        "max": _rounded(max(valid)) if valid else None,
        "mean": _rounded(statistics.fmean(valid)) if valid else None,
        "median": _rounded(statistics.median(valid)) if valid else None,
        "bins": bins,
    }


def _line_lengths_km(frame: Any) -> list[float | None]:
    """Return projected lengths for linear rows and None for all other rows."""

    lengths: list[float | None] = [None] * len(frame)
    if not len(frame) or not hasattr(frame, "geometry"):
        return lengths
    line_mask = frame.geometry.geom_type.isin(["LineString", "MultiLineString"])
    if not line_mask.any():
        return lengths
    try:
        linear = frame.loc[line_mask]
        projected = linear.to_crs(linear.estimate_utm_crs())
        linear_positions = [
            position for position, is_line in enumerate(line_mask.tolist()) if is_line
        ]
        for position, length in zip(linear_positions, projected.geometry.length / 1000):
            lengths[position] = float(length)
    except Exception:
        # Lengths are an optional enrichment. Missing/invalid CRS metadata must
        # never prevent count-based scrutiny statistics from being generated.
        return [None] * len(frame)
    return lengths


def summarize_theme(
    frames: Mapping[str, Any],
    theme: Mapping[str, Any],
    layer_sources: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Aggregate one theme across its declared node layers."""

    values: list[Any] = []
    weights: list[float | None] = []
    missing_layers: list[str] = []
    included_layers: list[str] = []
    attribute_layers: list[str] = []
    attribute = theme.get("attribute")

    for layer in theme.get("layers", []):
        frame = frames.get(layer)
        if frame is None:
            missing_layers.append(layer)
            continue
        included_layers.append(layer)
        if attribute == "__layer__":
            values.extend([layer] * len(frame))
            attribute_layers.append(layer)
        elif attribute in frame.columns:
            values.extend(frame[attribute].tolist())
            attribute_layers.append(layer)
        else:
            values.extend([theme.get("unknown_value", UNKNOWN_VALUE)] * len(frame))
            missing_layers.append(layer)
        weights.extend(_line_lengths_km(frame))

    if theme.get("kind") == "numeric":
        result = numeric_summary(
            values,
            breaks=theme.get("breaks", []),
            colors=theme.get("colors", []),
            invalid=theme.get("invalid"),
            unknown_value=theme.get("unknown_value", UNKNOWN_VALUE),
        )
    else:
        result = categorical_summary(
            values,
            colors=theme.get("colors"),
            other_color=theme.get("other_color", "#777777"),
            unknown_value=theme.get("unknown_value", UNKNOWN_VALUE),
            weights_km=weights,
        )

    result.update(
        {
            "id": theme.get("id"),
            "label": theme.get("label", theme.get("id")),
            "status": "unavailable"
            if not included_layers or not attribute_layers
            else ("partial" if missing_layers else "ok"),
            "layers": included_layers,
            "missingLayers": sorted(set(missing_layers)),
            "sourceDatasets": [
                layer_sources[layer]
                for layer in included_layers
                if layer_sources and layer in layer_sources
            ],
        }
    )
    return result


def build_node_summary(
    frames: Mapping[str, Any],
    themes: Mapping[str, Mapping[str, Any]],
    *,
    node_name: str,
    layer_sources: Mapping[str, str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the complete JSON-safe summary consumed by the browser composer."""

    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    theme_summaries: dict[str, Any] = {}
    for theme_id, theme in themes.items():
        if theme.get("kind") == "multi":
            theme_summaries[theme_id] = {
                "id": theme_id,
                "kind": "multi",
                "label": theme.get("label", theme_id),
                "panels": [
                    summarize_theme(frames, panel, layer_sources)
                    for panel in theme.get("panels", [])
                ],
            }
        else:
            theme_summaries[theme_id] = summarize_theme(
                frames, theme, layer_sources
            )

    return {
        "schema_version": 1,
        "node_name": node_name,
        "generated_at": generated_at,
        "themes": theme_summaries,
    }


def main() -> None:
    codebase_root = Path(__file__).resolve().parents[2]
    if str(codebase_root) not in sys.path:
        sys.path.insert(0, str(codebase_root))

    from constants import CITY_NAME, paths_dict, snapshot_summary_path
    from functions import dump_json, get_gdfs_dict_v2
    from webmap.webmap_lib import get_snapshot_themes

    frames = get_gdfs_dict_v2()
    summary = build_node_summary(
        frames,
        get_snapshot_themes(),
        node_name=CITY_NAME,
        layer_sources=paths_dict["map_layers"],
    )
    dump_json(summary, snapshot_summary_path)
    print(f"Snapshot summary written to {os.path.abspath(snapshot_summary_path)}")


if __name__ == "__main__":
    main()
