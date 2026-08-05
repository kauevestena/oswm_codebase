"""Metadata generation and validation for OpenSidewalkMap nodes."""

from .metadata_generation import (
    PROFILE_VERSION,
    generate_metadata,
    metadata_relative_path_for_data,
    validate_metadata_tree,
)

__all__ = [
    "PROFILE_VERSION",
    "generate_metadata",
    "metadata_relative_path_for_data",
    "validate_metadata_tree",
]
