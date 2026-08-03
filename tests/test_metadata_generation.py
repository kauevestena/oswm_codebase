import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from metadata.metadata_generation import (
    GENERATOR_ID,
    generate_metadata,
    metadata_relative_path_for_data,
    validate_metadata_tree,
)


ROOT = Path(__file__).resolve().parents[1]


class MetadataGenerationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.node_root = Path(self.tempdir.name)
        (self.node_root / "config.py").write_text(
            "\n".join(
                [
                    'CITY_NAME = "Milan"',
                    'CITY_SHORTNAME = "milan"',
                    'USERNAME = "oswm-test"',
                    'REPO_NAME = "milan-node"',
                    'METADATA_LANGUAGE = "en"',
                    'METADATA_TIMEZONE = "Europe/Rome"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._write_json(
            "data/boundaries/infos.json",
            {
                "name": "Milan",
                "bbox": [9.04, 45.36, 9.28, 45.54],
                "center": [9.16, 45.45],
            },
        )
        self._write_json(
            "data/updates/registry.json",
            {
                "Data Fetching": "03/08/2026 09:15:00",
                "Data Pre-Processing": "03/08/2026 09:20:00",
            },
        )
        self._write_json("data/index.json", {"folders": {}})
        self._write_json("data/raw/index.json", {"folder": "data/raw"})
        self._write_json(
            "data/raw/crossings.geojson",
            {"type": "FeatureCollection", "features": []},
        )
        parquet = self.node_root / "data" / "processed" / "sidewalks.parquet"
        parquet.parent.mkdir(parents=True, exist_ok=True)
        parquet.write_bytes(b"deterministic-geoparquet-fixture")
        status_page = self.node_root / "data" / "updates" / "index.html"
        status_page.parent.mkdir(parents=True, exist_ok=True)
        status_page.write_text("<!doctype html><title>Status</title>", encoding="utf-8")

    def tearDown(self):
        self.tempdir.cleanup()

    def _write_json(self, relative_path, payload):
        path = self.node_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _metadata_snapshot(self):
        return {
            path.relative_to(self.node_root).as_posix(): path.read_bytes()
            for path in sorted((self.node_root / "metadata").rglob("*.json"))
        }

    def test_path_mapping_preserves_tree_and_avoids_extension_collisions(self):
        self.assertEqual(
            metadata_relative_path_for_data("data/processed/index.json"),
            "metadata/processed/index.json",
        )
        self.assertEqual(
            metadata_relative_path_for_data("data/processed/sidewalks.parquet"),
            "metadata/processed/sidewalks.parquet.metadata.json",
        )
        self.assertEqual(
            metadata_relative_path_for_data("data/updates/index.html"),
            "metadata/updates/index.html.metadata.json",
        )
        with self.assertRaises(ValueError):
            metadata_relative_path_for_data("quality_check/index.json")

    def test_global_generation_creates_iso_aligned_catalogue_and_sidecars(self):
        summary = generate_metadata(self.node_root)

        self.assertGreaterEqual(summary["records_written"], 7)
        root_catalogue = self._read("metadata/index.json")
        raw_collection = self._read("metadata/raw/index.json")
        sidewalk_record = self._read(
            "metadata/processed/sidewalks.parquet.metadata.json"
        )
        status_record = self._read("metadata/updates/index.html.metadata.json")

        self.assertEqual(root_catalogue["resource_type"], "catalog")
        self.assertNotIn("data/data", root_catalogue["abstract"])
        self.assertEqual(
            root_catalogue["metadata_profile"]["name"],
            "OSWM Metadata Profile",
        )
        self.assertEqual(root_catalogue["spatial"]["bbox"], [9.04, 45.36, 9.28, 45.54])
        self.assertNotIn("geometry", root_catalogue["spatial"])
        self.assertIn("ISO 19115-1:2014", {
            item["name"] for item in root_catalogue["metadata_profile"]["aligned_with"]
        })
        self.assertEqual(raw_collection["resource_type"], "collection")
        self.assertEqual(
            sidewalk_record["distribution"]["resource_path"],
            "data/processed/sidewalks.parquet",
        )
        self.assertEqual(
            sidewalk_record["distribution"]["checksum"]["value"],
            hashlib.sha256(b"deterministic-geoparquet-fixture").hexdigest(),
        )
        self.assertEqual(sidewalk_record["metadata_profile"]["domain"], "geographic")
        self.assertIn(
            "ISO 19110:2016",
            {
                item["name"]
                for item in sidewalk_record["metadata_profile"]["aligned_with"]
            },
        )
        self.assertEqual(status_record["metadata_profile"]["domain"], "non-geographic")
        self.assertEqual(
            {item["name"] for item in status_record["metadata_profile"]["aligned_with"]},
            {"ISO 15836-1:2017"},
        )
        self.assertIsNone(status_record["spatial"])
        self.assertEqual(
            status_record["quality"]["standard"], "OSWM Metadata Profile 1.0"
        )
        self.assertEqual(
            sidewalk_record["metadata_generation"]["generator"], GENERATOR_ID
        )
        self.assertEqual(
            root_catalogue["integrity"]["generated_records"],
            summary["records_written"],
        )
        self.assertEqual(validate_metadata_tree(self.node_root, verify_checksums=True), [])

    def test_generation_is_deterministic_and_prunes_only_owned_stale_records(self):
        generate_metadata(self.node_root)
        first = self._metadata_snapshot()

        stale = self.node_root / "metadata" / "raw" / "removed.parquet.metadata.json"
        stale.write_bytes(
            (self.node_root / "metadata" / "raw" / "crossings.geojson.metadata.json").read_bytes()
        )
        manual = self.node_root / "metadata" / "manual-note.json"
        manual.write_text('{"title": "preserve me"}\n', encoding="utf-8")

        summary = generate_metadata(self.node_root)
        second = self._metadata_snapshot()

        self.assertIn("metadata/raw/removed.parquet.metadata.json", summary["stale_records_removed"])
        self.assertFalse(stale.exists())
        self.assertTrue(manual.exists())
        second_without_manual = {
            key: value for key, value in second.items() if key != "metadata/manual-note.json"
        }
        self.assertEqual(first, second_without_manual)

    def _read(self, relative_path):
        return json.loads((self.node_root / relative_path).read_text(encoding="utf-8"))


class MetadataApiWiringTests(unittest.TestCase):
    def test_api_exposes_metadata_as_first_class_deliverable(self):
        source = (ROOT / "datahub" / "API" / "generate_api.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('onclick="switchDeliverable(\'metadata\')"', source)
        self.assertIn('id="btn-metadata"', source)
        self.assertIn('"deliverable": "metadata"', source)
        self.assertIn("metadata_relative_path_for_data", source)

    def test_daily_runner_generates_metadata_before_api(self):
        source = (ROOT / "runners" / "daily.sh").read_text(encoding="utf-8")
        metadata_position = source.rfind("metadata_generation.py")
        api_position = source.rfind("datahub/API/generate_api.py")
        self.assertGreater(metadata_position, -1)
        self.assertGreater(api_position, metadata_position)


if __name__ == "__main__":
    unittest.main()
