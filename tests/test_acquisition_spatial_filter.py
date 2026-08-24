from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

from shapely.geometry import box


def _library(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "dh_lib",
        SimpleNamespace(boundaries_geojson_path="unused.geojson"),
    )
    sys.modules.pop("datahub.acquisition.acq_lib", None)
    return importlib.import_module("datahub.acquisition.acq_lib")


def test_pic4review_geom_is_normalized_and_filtered_from_other_node(monkeypatch):
    library = _library(monkeypatch)
    mission = {
        "id": 2820,
        "theme": "accessibility",
        "shortdesc": "Missing Surface Materials",
        "geom": {
            "type": "Polygon",
            "coordinates": [[
                [-49.2955, -25.4723],
                [-49.2693, -25.4723],
                [-49.2693, -25.4414],
                [-49.2955, -25.4414],
                [-49.2955, -25.4723],
            ]],
        },
    }

    projects = library.parse_pic4review_results([mission], "https://pic4review.test/#/")

    assert projects[0]["spatial_source"] == "geom"
    assert projects[0]["bbox"] == [-49.2955, -25.4723, -49.2693, -25.4414]
    lima = box(-77.1992, -12.5199, -76.6208, -11.5724)
    assert library.filter_by_polygon(projects, lima) == []


def test_pic4review_embedded_geojson_provides_bbox_without_payload_copy(monkeypatch):
    library = _library(monkeypatch)
    mission = {
        "id": 7,
        "dataoptions": {
            "geojson": {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-77.05, -12.1], [-77.0, -12.0]],
                    },
                }],
            }
        },
    }

    project = library.parse_pic4review_results([mission], "https://pic4review.test/#/")[0]

    assert project["bbox"] == [-77.05, -12.1, -77.0, -12.0]
    assert project["spatial_source"] == "dataoptions.geojson"
    assert "geometry" not in project


def test_pic4review_missing_geometry_is_explicitly_auditable(monkeypatch):
    library = _library(monkeypatch)
    project = library.parse_pic4review_results(
        [{"id": 8, "geom": {"type": "Polygon", "coordinates": []}}],
        "https://pic4review.test/#/",
    )[0]

    assert project["spatial_status"] == "unknown"
    assert project["spatial_source"] is None
