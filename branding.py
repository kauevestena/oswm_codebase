"""Resolve shared OSWM identity assets from the canonical JSON manifest."""

from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Iterator


CODEBASE_ROOT = Path(__file__).resolve().parent
BRANDING_MANIFEST_PATH = CODEBASE_ROOT / "assets" / "branding" / "manifest.json"


@lru_cache(maxsize=1)
def load_branding_manifest() -> dict[str, Any]:
    """Load the canonical branding registry once per Python process."""

    with BRANDING_MANIFEST_PATH.open(encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


def branding_asset_path(semantic_key: str) -> str:
    """Return a codebase-root-relative asset path for a dotted semantic key."""

    value: Any = load_branding_manifest()
    for part in semantic_key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(f"Unknown OSWM branding key: {semantic_key}")
        value = value[part]
    if not isinstance(value, str):
        raise KeyError(f"OSWM branding key is not an asset: {semantic_key}")
    return value


def branding_asset_url(
    semantic_key: str,
    codebase_prefix: str = "oswm_codebase",
) -> str:
    """Join an asset from the manifest to a node-relative or absolute prefix."""

    asset_path = branding_asset_path(semantic_key).lstrip("/")
    prefix = codebase_prefix.rstrip("/")
    return f"{prefix}/{asset_path}" if prefix else asset_path


def iter_branding_assets() -> Iterator[tuple[str, str]]:
    """Yield every semantic asset key and path in the manifest."""

    manifest = load_branding_manifest()

    def walk(value: Any, prefix: str) -> Iterator[tuple[str, str]]:
        if isinstance(value, str):
            yield prefix, value
        elif isinstance(value, dict):
            for key, child in value.items():
                child_prefix = f"{prefix}.{key}" if prefix else key
                yield from walk(child, child_prefix)

    yield from walk(manifest.get("favicon"), "favicon")
    yield from walk(manifest.get("logos", {}), "logos")
    yield from walk(manifest.get("banners", {}), "banners")
