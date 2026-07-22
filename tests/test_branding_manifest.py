import json
from pathlib import Path, PurePosixPath
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "assets" / "branding" / "manifest.json"


class BrandingManifestTests(unittest.TestCase):
    @staticmethod
    def _reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate manifest key: {key}")
            result[key] = value
        return result

    def setUp(self):
        self.manifest = json.loads(
            MANIFEST_PATH.read_text(encoding="utf-8"),
            object_pairs_hook=self._reject_duplicate_keys,
        )

    def _asset_entries(self):
        yield "favicon", self.manifest["favicon"]
        for group_name in ("logos", "banners"):
            for key, path in self.manifest[group_name].items():
                yield f"{group_name}.{key}", path

    def test_manifest_contract_and_required_keys(self):
        self.assertEqual(1, self.manifest["schema_version"])
        self.assertEqual(
            {
                "page",
                "page_clean",
                "page_dark_clean",
                "project",
                "project_100px",
            },
            set(self.manifest["logos"]),
        )
        self.assertIsInstance(self.manifest["banners"], dict)

    def test_registered_assets_are_unique_safe_and_present(self):
        seen_paths = set()
        for semantic_key, relative_path in self._asset_entries():
            with self.subTest(semantic_key=semantic_key):
                self.assertIsInstance(relative_path, str)
                path = PurePosixPath(relative_path)
                self.assertFalse(path.is_absolute())
                self.assertNotIn("..", path.parts)
                self.assertEqual(("assets", "branding"), path.parts[:2])
                self.assertNotIn(relative_path, seen_paths)
                self.assertTrue((ROOT / relative_path).is_file())
                seen_paths.add(relative_path)

    def test_requested_legacy_locations_are_empty(self):
        old_paths = (
            "assets/favicon_homepage.png",
            "assets/page_logo.png",
            "assets/page_logo_clean.png",
            "assets/page_logo_dark_clean.png",
            "assets/homepage/project_logo.png",
            "assets/homepage/project_logo_100px.png",
        )
        for relative_path in old_paths:
            with self.subTest(relative_path=relative_path):
                self.assertFalse((ROOT / relative_path).exists())


if __name__ == "__main__":
    unittest.main()
