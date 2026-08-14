import math
import unittest
from pathlib import Path

from datahub.API.resource_examples import (
    attribute_filter_for_path,
    capabilities_for_resource,
    resource_format,
    square_bbox,
)


ROOT = Path(__file__).resolve().parents[1]


class ApiResourceExamplesTests(unittest.TestCase):
    def test_resource_formats_are_detected_without_treating_every_file_as_json(self):
        self.assertEqual(resource_format("index.json"), "JSON")
        self.assertEqual(resource_format("report.csv"), "CSV")
        self.assertEqual(resource_format("sidewalks.parquet"), "GeoParquet")
        self.assertEqual(resource_format("sidewalks.pmtiles"), "PMTiles")
        self.assertEqual(resource_format("notes.txt"), "File")

    def test_non_spatial_formats_do_not_offer_gdal(self):
        for format_name in ("JSON", "CSV", "PNG", "OSWM Binary Graph"):
            with self.subTest(format_name=format_name):
                capabilities = capabilities_for_resource(format_name)
                self.assertNotIn("gdal", capabilities["snippets"])

    def test_spatial_formats_offer_working_format_specific_actions(self):
        parquet = capabilities_for_resource(
            "GeoParquet", "data/processed/sidewalks.parquet"
        )
        pmtiles = capabilities_for_resource(
            "PMTiles", "data/tiles/sidewalks.pmtiles"
        )

        self.assertEqual(parquet["action"], "copy-spatial-extract")
        self.assertIn("gdal", parquet["snippets"])
        self.assertEqual(parquet["attribute_filter"], "surface = 'asphalt'")
        self.assertEqual(pmtiles["action"], "inspect-pmtiles")
        self.assertIn("javascript", pmtiles["snippets"])

    def test_attribute_examples_follow_common_layer_schemas(self):
        self.assertEqual(
            attribute_filter_for_path("crossings_lacking_kerbs.parquet"),
            "crossing IS NOT NULL",
        )
        self.assertEqual(attribute_filter_for_path("kerbs.parquet"), "kerb IS NOT NULL")
        self.assertEqual(attribute_filter_for_path("unknown.parquet"), "id IS NOT NULL")

    def test_default_bbox_is_a_one_kilometre_square_in_crs84_order(self):
        center_lat = -25.42973
        center_lon = -49.27196
        west, south, east, north = square_bbox(center_lat, center_lon)

        self.assertLess(west, center_lon)
        self.assertLess(south, center_lat)
        self.assertGreater(east, center_lon)
        self.assertGreater(north, center_lat)

        height_m = (north - south) * 111_320.0
        width_m = (
            (east - west)
            * 111_320.0
            * math.cos(math.radians(center_lat))
        )
        self.assertAlmostEqual(height_m, 1000, delta=0.2)
        self.assertAlmostEqual(width_m, 1000, delta=0.2)

    def test_bbox_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            square_bbox(-25.4, -49.2, 0)
        with self.assertRaises(ValueError):
            square_bbox(91, -49.2, 1000)
        with self.assertRaises(ValueError):
            square_bbox(90, 0, 1000)

    def test_generator_contains_regression_protections_for_reported_examples(self):
        source = (ROOT / "datahub" / "API" / "generate_api.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("ogrinfo -ro -al -so", source)
        self.assertIn("ogr2ogr -f GeoJSON", source)
        self.assertIn("-spat_srs OGC:CRS84", source)
        self.assertIn("-where", source)
        self.assertNotIn("/vsipmtiles/vsicurl/", source)
        self.assertNotIn('id="btn-try"', source)
        self.assertIn('id="btn-action"', source)


if __name__ == "__main__":
    unittest.main()
