import json
from pathlib import Path

import pytest

from metadata.stac_fleet import generate_fleet_catalog


REGISTRY = Path(__file__).resolve().parents[1] / "fleet/registry.toml"


def test_fleet_publishes_only_selected_validated_node_catalogs(tmp_path):
    requested = []

    def fetch(url):
        requested.append(url)
        return {"type": "Catalog", "stac_version": "1.1.0", "id": "milan",
                "description": "Milan", "title": "Milan", "links": []}

    path = tmp_path / "catalog.json"
    catalog = generate_fleet_catalog(REGISTRY, ["milan"], path,
        "https://example.org/stac/catalog.json", fetch_catalog=fetch)
    assert requested == ["https://opensidewalkmap.github.io/milan/stac/catalog.json"]
    assert [link["href"] for link in catalog["links"] if link["rel"] == "child"] == requested
    assert json.loads(path.read_text()) == catalog
    first = path.read_bytes()
    generate_fleet_catalog(REGISTRY, ["milan"], path,
        "https://example.org/stac/catalog.json", fetch_catalog=fetch)
    assert path.read_bytes() == first


def test_unpublished_node_does_not_replace_existing_global_catalog(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text('{"existing": true}')

    def missing(url):
        raise OSError("404")

    with pytest.raises(OSError, match="404"):
        generate_fleet_catalog(REGISTRY, ["milan"], path,
            "https://example.org/stac/catalog.json", fetch_catalog=missing)
    assert json.loads(path.read_text()) == {"existing": True}


@pytest.mark.parametrize("nodes", [[], ["unregistered"]])
def test_fleet_rejects_empty_or_unknown_selection(tmp_path, nodes):
    with pytest.raises(ValueError, match="enabled fleet node"):
        generate_fleet_catalog(REGISTRY, nodes, tmp_path / "catalog.json",
            "https://example.org/stac/catalog.json", fetch_catalog=lambda url: pytest.fail(url))
