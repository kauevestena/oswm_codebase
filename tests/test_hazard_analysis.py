import unittest
from pathlib import Path

from accessibility.normalization import prepare_feature
from hazard_analysis.assessment import assess_feature, compact_hazard_properties
from hazard_analysis.rules import HAZARD_RULES
from hazard_analysis.terrain import classify_terrain_slope
from hazard_analysis.validation import (
    public_rule_metadata,
    ruleset_hash,
    validate_rules,
)


ROOT = Path(__file__).resolve().parents[1]


class HazardRuleValidationTests(unittest.TestCase):
    def test_live_rules_are_valid_and_complete(self):
        validate_rules(HAZARD_RULES)
        self.assertEqual(len(HAZARD_RULES), 29)

    def test_duplicate_rule_id_is_rejected(self):
        duplicate = [HAZARD_RULES[0], HAZARD_RULES[0]]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_rules(duplicate)

    def test_ruleset_hash_is_deterministic(self):
        self.assertEqual(ruleset_hash(HAZARD_RULES), ruleset_hash(HAZARD_RULES))

    def test_public_metadata_does_not_expose_conditions(self):
        public = public_rule_metadata(HAZARD_RULES)
        self.assertTrue(public[0]["effects"])
        self.assertNotIn("condition", public[0])


class HazardAssessmentTests(unittest.TestCase):
    def test_raised_kerb_is_wheelchair_barrier(self):
        feature = prepare_feature(
            {"associated_kerbs": ["raised"]}, edge_kind="crossing"
        )
        result = assess_feature(feature, normalized=True)
        wheelchair = result["wheelchair"]["forward"]
        self.assertEqual(wheelchair["severity"], 4)
        self.assertEqual(wheelchair["traversability"], "impassable")

    def test_missing_tactile_data_is_unknown_not_dangerous(self):
        feature = prepare_feature({}, edge_kind="crossing")
        result = assess_feature(feature, normalized=True)["blind"]["forward"]
        self.assertEqual(result["severity"], 0)
        self.assertEqual(result["status"], "insufficient_data")

    def test_explicit_flush_without_tactile_is_critical(self):
        feature = prepare_feature(
            {
                "associated_transition_states": [
                    {"kerb": "flush", "tactile_paving": "no"}
                ]
            },
            edge_kind="crossing",
        )
        result = assess_feature(feature, normalized=True)["blind"]["forward"]
        self.assertEqual(result["severity"], 4)
        self.assertEqual(
            result["traversability"], "passable_with_extreme_risk"
        )

    def test_crossing_wide_values_do_not_create_false_pair(self):
        feature = prepare_feature(
            {
                "associated_transition_states": [
                    {"kerb": "flush", "tactile_paving": "yes"},
                    {"kerb": "raised", "tactile_paving": "no"},
                ],
                "associated_tactile_paving": ["yes", "no"],
            },
            edge_kind="crossing",
        )
        result = assess_feature(feature, normalized=True)["blind"]["forward"]
        self.assertEqual(result["severity"], 3)
        self.assertNotIn("flush_without_tactile", result["rule_ids"])

    def test_uniform_surface_requires_all_three_explicit_sources(self):
        complete = prepare_feature(
            {
                "surface": "asphalt",
                "associated_transition_states": [
                    {
                        "kerb_surface": "asphalt",
                        "sidewalk_surface": "asphalt",
                    }
                ],
            },
            edge_kind="crossing",
        )
        incomplete = prepare_feature(
            {
                "surface": "asphalt",
                "associated_transition_states": [
                    {"kerb_surface": "asphalt"}
                ],
            },
            edge_kind="crossing",
        )
        self.assertTrue(complete["uniform_transition_surface"])
        self.assertFalse(incomplete["uniform_transition_surface"])

    def test_cross_slope_requires_explicit_data(self):
        missing = prepare_feature({})
        explicit = prepare_feature({"incline:across": "6%"})
        self.assertEqual(
            assess_feature(missing, normalized=True)["wheelchair"]["forward"][
                "categories"
            ]["cross_slope"]["severity"],
            0,
        )
        self.assertEqual(
            assess_feature(explicit, normalized=True)["wheelchair"]["forward"][
                "categories"
            ]["cross_slope"]["severity"],
            4,
        )

    def test_longitudinal_slope_is_directional(self):
        feature = prepare_feature({"incline": "10%"})
        result = assess_feature(feature, normalized=True)["blind"]
        self.assertEqual(result["forward"]["severity"], 1)
        self.assertEqual(result["backward"]["severity"], 2)

    def test_compact_properties_include_categories_and_directions(self):
        feature = prepare_feature({"surface": "sand"})
        compact = compact_hazard_properties(
            assess_feature(feature, normalized=True), "wheelchair"
        )
        self.assertIn("forward", compact)
        self.assertIn("backward", compact)
        self.assertEqual(compact["category_surface"], 4)


class TerrainHazardTests(unittest.TestCase):
    def test_profile_thresholds_are_classified(self):
        values = classify_terrain_slope([0, 2.1, 5.1, 8.5, 13], [2, 5, 8.33, 12.5])
        self.assertEqual(values.tolist(), [0, 1, 2, 3, 4])


class HazardClientWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (
            ROOT / "hazard_analysis" / "hazard_analysis.html"
        ).read_text(encoding="utf-8")
        cls.generator = (
            ROOT / "generation" / "routing_demo_gen.py"
        ).read_text(encoding="utf-8")
        cls.modules = (ROOT / "modules_info.py").read_text(encoding="utf-8")
        cls.api = (
            ROOT / "datahub" / "API" / "generate_api.py"
        ).read_text(encoding="utf-8")

    def test_client_filters_profiles_categories_and_levels(self):
        for identifier in (
            'id="profileSelect"',
            'id="categorySelect"',
            'id="severitySelect"',
            'id="confidenceRange"',
        ):
            self.assertIn(identifier, self.html)
        self.assertIn("hazard.pmtiles", self.html)
        self.assertIn('data-oswm-branding="logos.page"', self.html)
        self.assertIn('id="node_link"', self.html)
        self.assertIn("ScaleControl", self.html)

    def test_client_explains_missing_data_and_critical_context(self):
        self.assertIn("not certified safe", self.html)
        self.assertIn("Apparent mobility barrier", self.html)
        self.assertIn("Extreme contextual safety risk", self.html)

    def test_client_supports_optional_terrain_raster(self):
        self.assertIn('id="terrainToggle"', self.html)
        self.assertIn("terrain-source", self.html)
        self.assertIn("source_attribution", self.html)

    def test_shared_generator_emits_both_modules(self):
        self.assertIn("compact_grade_properties", self.generator)
        self.assertIn("compact_hazard_properties", self.generator)
        self.assertIn("generate_terrain_overlays", self.generator)

    def test_homepage_and_api_list_hazard_module(self):
        self.assertIn("hazard_analysis.html", self.modules)
        self.assertIn("data/hazard_analysis/profiles.json", self.api)
        self.assertIn('fmt = "PNG"', self.api)


if __name__ == "__main__":
    unittest.main()
