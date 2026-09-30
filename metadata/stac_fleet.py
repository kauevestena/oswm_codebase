"""Build a global STAC entry point for explicitly selected, published nodes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

CODEBASE_ROOT = Path(__file__).resolve().parents[1]
if str(CODEBASE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEBASE_ROOT))

from fleet.registry import load_registry  # noqa: E402
from metadata.metadata_generation import _atomic_json_dump  # noqa: E402
from metadata.stac_generation import GENERATOR, _base, _link  # noqa: E402
from metadata.stac_validation import validate_document  # noqa: E402


def _fetch_catalog(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "OpenSidewalkMap-STAC/1.0"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def generate_fleet_catalog(registry_path, node_ids, output, public_url, *, fetch_catalog=_fetch_catalog):
    """Check published node catalogs before replacing the global entry point."""
    if urlsplit(public_url).scheme != "https" or not urlsplit(public_url).netloc:
        raise ValueError("The global catalog needs an absolute HTTPS public URL")
    registry = load_registry(registry_path)
    requested = set(node_ids)
    eligible = {node.id: node for node in registry.nodes if node.enabled}
    if not requested or requested - eligible.keys():
        raise ValueError("Select at least one enabled fleet node using --node")
    catalog = _base("Catalog", "opensidewalkmap", "OpenSidewalkMap",
                    "Current OSWM datasets from participating city nodes.")
    catalog["links"] = [_link("self", public_url), _link("root", public_url)]
    for identifier in sorted(requested):
        node = eligible[identifier]
        href = node.pages_url.rstrip("/") + "/stac/catalog.json"
        remote = fetch_catalog(href)
        if remote.get("type") != "Catalog" or validate_document(remote):
            raise ValueError(f"{identifier} has no valid published STAC 1.1.0 catalog: {href}")
        catalog["links"].append(_link("child", href, title=remote.get("title", identifier)))
    errors = validate_document(catalog)
    if errors:
        raise ValueError("Invalid fleet catalog: " + "; ".join(errors))
    destination = Path(output)
    if destination.exists() and json.loads(destination.read_text()).get("oswm:generator") != GENERATOR:
        raise ValueError(f"Refusing to overwrite unmanaged catalog: {destination}")
    _atomic_json_dump(catalog, destination)
    return catalog


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(CODEBASE_ROOT / "fleet/registry.toml"))
    parser.add_argument("--node", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--public-url", required=True)
    args = parser.parse_args(argv)
    catalog = generate_fleet_catalog(args.registry, args.node, args.output, args.public_url)
    print(json.dumps({"catalog": args.output, "nodes": len(catalog["links"]) - 2}))


if __name__ == "__main__":
    main()
