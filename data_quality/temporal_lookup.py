"""Stable temporal-attribute lookups for OSM-derived feature tables."""

from __future__ import annotations

from typing import Any

import pandas as pd


TEMPORAL_COLUMNS = ("age", "last_update")


def build_temporal_lookup(frame: pd.DataFrame) -> dict[object, dict[str, Any]]:
    """Index temporal values without assuming that bare OSM IDs are unique.

    OSM nodes, ways, and relations have independent ID namespaces, and geometry
    normalization may also duplicate an element into multiple rows.  Prefer the
    composite ``(element, id)`` identity when available and collapse equivalent
    duplicate rows deterministically.
    """

    required = {"id", *TEMPORAL_COLUMNS}
    if frame.empty or not required.issubset(frame.columns):
        return {}

    key_columns = ["element", "id"] if "element" in frame.columns else ["id"]
    selected = frame.loc[:, [*key_columns, *TEMPORAL_COLUMNS]].dropna(
        subset=["id"]
    )
    selected = selected.drop_duplicates(subset=key_columns, keep="last")

    lookup: dict[object, dict[str, Any]] = {}
    for row in selected.itertuples(index=False):
        key = (row.element, row.id) if "element" in key_columns else row.id
        lookup[key] = {"age": row.age, "last_update": row.last_update}
    return lookup


def temporal_attributes(
    lookup: dict[object, dict[str, Any]], row: object
) -> dict[str, Any] | None:
    """Return temporal values for a raw feature row."""

    element = getattr(row, "element", None)
    feature_id = getattr(row, "id")
    if element is not None:
        match = lookup.get((element, feature_id))
        if match is not None:
            return match
    return lookup.get(feature_id)
