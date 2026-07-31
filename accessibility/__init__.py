"""Shared accessibility evidence normalization for OSWM modules."""

from .normalization import (
    is_unknown,
    normalize_categorical,
    normalize_sequence,
    parse_incline_percent,
    parse_number,
    parse_width_m,
    prepare_feature,
)

__all__ = [
    "is_unknown",
    "normalize_categorical",
    "normalize_sequence",
    "parse_incline_percent",
    "parse_number",
    "parse_width_m",
    "prepare_feature",
]
