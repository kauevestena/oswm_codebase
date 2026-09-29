"""Offline validation against the unmodified STAC 1.1.0 core schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft7Validator, FormatChecker
from referencing import Registry, Resource


SCHEMA_ROOT = Path(__file__).parent / "schemas" / "stac-1.1.0"
SCHEMA_URL = "https://schemas.stacspec.org/v1.1.0"


@lru_cache(maxsize=1)
def _schemas():
    schemas = {}
    for path in SCHEMA_ROOT.rglob("*.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        identifier = schema.get("$id") or schema.get("id")
        if path.parent.name == "geojson":
            identifier = f"https://geojson.org/schema/{path.name}"
        else:
            # Register retrieval URLs too: upstream common.json has an $id
            # ending in 'commonjson'. Keep the vendored schema unmodified.
            schemas[f"{SCHEMA_URL}/{path.relative_to(SCHEMA_ROOT).as_posix()}"] = schema
        schemas[identifier] = schema
    registry = Registry().with_resources(
        (uri, Resource.from_contents(schema)) for uri, schema in schemas.items()
    )
    return schemas, registry


def validate_document(document: dict) -> list[str]:
    """Return schema errors without fetching any network resources."""
    kind = {"Catalog": "catalog", "Collection": "collection", "Feature": "item"}.get(
        document.get("type")
    )
    if kind is None:
        return ["Unknown STAC document type"]
    schemas, registry = _schemas()
    schema = schemas[f"{SCHEMA_URL}/{kind}-spec/json-schema/{kind}.json"]
    validator = Draft7Validator(schema, registry=registry, format_checker=FormatChecker())
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '/'}: {error.message}"
        for error in validator.iter_errors(document)
    ]
