"""Render dataset freshness from pipeline records, independently of page builds."""

import json
from pathlib import Path

from time_utils import isoformat_utc, parse_timestamp


def data_generation_html(registry_path="data/updates/registry.json", timezone_name="UTC"):
    """Use the last data processing time, falling back to acquisition time."""
    try:
        registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        registry = {}
    if isinstance(registry, dict):
        for key, label in (("Data Pre-Processing", "Data generated"),
                           ("Data Fetching", "Data acquired")):
            timestamp = parse_timestamp(registry.get(key), timezone_name)
            if timestamp is not None:
                iso = isoformat_utc(timestamp)
                display = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
                return f'{label}: <time datetime="{iso}">{display}</time>'
    return "Data generated: Not available"
