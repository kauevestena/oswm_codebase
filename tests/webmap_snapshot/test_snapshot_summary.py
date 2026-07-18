import json
from pathlib import Path
import sys
import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point


CODEBASE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CODEBASE_ROOT))

from webmap.snapshot.generate_snapshot_summary import (  # noqa: E402
    build_node_summary,
    categorical_summary,
    numeric_summary,
    summarize_theme,
)


class CategoricalSummaryTests(unittest.TestCase):
    def test_unknown_values_do_not_contribute_to_diversity(self):
        summary = categorical_summary(["asphalt", "concrete", "?", None, ""])

        self.assertEqual(summary["total"], 5)
        self.assertEqual(summary["known"], 2)
        self.assertEqual(summary["unknown"], 3)
        self.assertAlmostEqual(summary["effectiveDiversity"], 2.0, places=5)

    def test_category_order_is_count_then_label(self):
        summary = categorical_summary(["z", "a", "z", "a", "b"])

        self.assertEqual(
            [category["value"] for category in summary["categories"]],
            ["a", "z", "b"],
        )

    def test_single_category_has_zero_entropy(self):
        summary = categorical_summary(["asphalt", "asphalt"])

        self.assertEqual(summary["shannonEntropy"], 0)
        self.assertEqual(summary["effectiveDiversity"], 1)


class NumericSummaryTests(unittest.TestCase):
    def test_map_class_breaks_and_invalid_values_are_preserved(self):
        summary = numeric_summary(
            [None, -1, 0, 1.9, 2, 12],
            breaks=[0, 2, 4, 10],
            colors=["a", "b", "c", "d"],
            invalid={"operator": "<", "threshold": 0},
        )

        self.assertEqual(summary["unknown"], 1)
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual([item["count"] for item in summary["bins"]], [2, 1, 0, 1])
        self.assertEqual(summary["median"], 1.95)


class NodeSummaryTests(unittest.TestCase):
    def setUp(self):
        self.sidewalks = gpd.GeoDataFrame(
            {"surface": ["asphalt", "concrete", "?"]},
            geometry=[
                LineString([(0, 0), (0.01, 0)]),
                LineString([(0, 0), (0.01, 0)]),
                LineString([(0, 0), (0.01, 0)]),
            ],
            crs="EPSG:4326",
        )
        self.kerbs = gpd.GeoDataFrame(
            {"kerb": ["lowered", "?"]},
            geometry=[Point(0, 0), Point(0.01, 0)],
            crs="EPSG:4326",
        )

    def test_line_lengths_are_projected_and_points_have_no_length_claim(self):
        surface = summarize_theme(
            {"sidewalks": self.sidewalks},
            {
                "id": "surface",
                "kind": "categorical",
                "label": "Surface",
                "attribute": "surface",
                "layers": ["sidewalks"],
                "colors": {},
            },
        )
        kerbs = summarize_theme(
            {"kerbs": self.kerbs},
            {
                "id": "kerbs",
                "kind": "categorical",
                "label": "Kerbs",
                "attribute": "kerb",
                "layers": ["kerbs"],
                "colors": {},
            },
        )

        self.assertGreater(surface["totalLengthKm"], 3)
        self.assertLess(surface["totalLengthKm"], 4)
        self.assertNotIn("totalLengthKm", kerbs)

    def test_missing_optional_attribute_is_documented_not_raised(self):
        summary = summarize_theme(
            {"kerbs": self.kerbs.drop(columns="kerb")},
            {
                "id": "tactile_paving",
                "kind": "categorical",
                "label": "Tactile paving",
                "attribute": "tactile_paving",
                "layers": ["kerbs"],
                "colors": {},
            },
        )

        self.assertEqual(summary["status"], "unavailable")
        self.assertEqual(summary["unknown"], 2)
        self.assertEqual(summary["missingLayers"], ["kerbs"])

    def test_complete_output_is_json_safe_and_repeatable(self):
        themes = {
            "surface": {
                "id": "surface",
                "kind": "categorical",
                "label": "Surface",
                "attribute": "surface",
                "layers": ["sidewalks"],
                "colors": {"asphalt": "#000"},
            }
        }
        first = build_node_summary(
            {"sidewalks": self.sidewalks},
            themes,
            node_name="Test node",
            generated_at="2026-01-01T00:00:00+00:00",
        )
        second = build_node_summary(
            {"sidewalks": self.sidewalks},
            themes,
            node_name="Test node",
            generated_at="2026-01-01T00:00:00+00:00",
        )

        self.assertEqual(first, second)
        json.dumps(first, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
