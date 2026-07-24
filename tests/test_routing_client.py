import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RoutingClientWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "routing" / "routing_demo.html").read_text(
            encoding="utf-8"
        )
        cls.generator = (
            ROOT / "generation" / "routing_demo_gen.py"
        ).read_text(encoding="utf-8")
        cls.daily_workflow = (
            ROOT / "workflows" / "data_daily_updating.yml"
        ).read_text(encoding="utf-8")
        cls.api_generator = (
            ROOT / "datahub" / "API" / "generate_api.py"
        ).read_text(encoding="utf-8")

    def test_client_uses_pathfinder_v2(self):
        self.assertIn("geojson-path-finder@2.1.0", self.html)
        self.assertIn("tolerance:", self.html)
        self.assertIn("weight:", self.html)
        self.assertNotIn("weightFn:", self.html)

    def test_profile_selector_and_directional_grades_are_wired(self):
        self.assertIn('id="profileSelect"', self.html)
        self.assertIn("_grade_${suffix}", self.html)
        self.assertIn("forward:", self.html)
        self.assertIn("backward:", self.html)

    def test_generator_emits_profile_metadata_and_slope_cache(self):
        self.assertIn("routing_profiles_path", self.generator)
        self.assertIn("routing_metadata_path", self.generator)
        self.assertIn("routing_slope_cache_path", self.generator)
        self.assertIn("profile_ruleset_hash", self.generator)

    def test_daily_workflow_caches_elevation_tiles(self):
        self.assertIn("actions/cache@v4", self.daily_workflow)
        self.assertIn(".cache/oswm/elevation", self.daily_workflow)

    def test_data_api_lists_generated_routing_artifacts(self):
        for filename in (
            "demo.geojson",
            "profiles.json",
            "metadata.json",
            "slope_cache.json",
        ):
            self.assertIn(filename, self.api_generator)


if __name__ == "__main__":
    unittest.main()
