import copy
import unittest

from routing.grading import (
    compact_grade_properties,
    grade_feature,
    parse_incline_percent,
    parse_width_m,
)
from routing.profile_rules import ROUTING_PROFILES
from routing.profile_validation import (
    ProfileValidationError,
    profile_ruleset_hash,
    public_profile_metadata,
    validate_profiles,
)


class ProfileValidationTests(unittest.TestCase):
    def test_live_profiles_are_valid(self):
        validate_profiles(ROUTING_PROFILES)

    def test_ruleset_hash_is_deterministic(self):
        first = profile_ruleset_hash(ROUTING_PROFILES)
        second = profile_ruleset_hash(copy.deepcopy(ROUTING_PROFILES))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)

    def test_invalid_grade_is_rejected(self):
        profiles = copy.deepcopy(ROUTING_PROFILES)
        profiles["wheelchair"]["factors"]["surface"]["values"]["asphalt"] = 101
        with self.assertRaises(ProfileValidationError):
            validate_profiles(profiles)

    def test_non_monotonic_cost_is_rejected(self):
        profiles = copy.deepcopy(ROUTING_PROFILES)
        profiles["wheelchair"]["cost"]["grade_multipliers"][2][
            "multiplier"
        ] = 0.5
        with self.assertRaises(ProfileValidationError):
            validate_profiles(profiles)

    def test_boolean_speed_is_rejected(self):
        profiles = copy.deepcopy(ROUTING_PROFILES)
        profiles["wheelchair"]["speed_kmh"] = True
        with self.assertRaises(ProfileValidationError):
            validate_profiles(profiles)

    def test_public_metadata_contains_no_factor_tables(self):
        metadata = public_profile_metadata(ROUTING_PROFILES)
        self.assertIn("wheelchair", metadata)
        self.assertIn("cost", metadata["wheelchair"])
        self.assertNotIn("factors", metadata["wheelchair"])


class NormalizationTests(unittest.TestCase):
    def test_width_parsing(self):
        self.assertAlmostEqual(parse_width_m("1,25 m"), 1.25)
        self.assertAlmostEqual(parse_width_m("4'6\""), 1.3716, places=4)
        self.assertEqual(parse_width_m("1.5;0.9"), 0.9)
        self.assertIsNone(parse_width_m("?"))

    def test_incline_parsing(self):
        self.assertEqual(parse_incline_percent("8.5%"), (8.5, "numeric"))
        degrees, kind = parse_incline_percent("5°")
        self.assertEqual(kind, "numeric")
        self.assertAlmostEqual(degrees, 8.7489, places=3)
        self.assertEqual(parse_incline_percent("up"), (None, "qualitative"))

    def test_pandas_missing_scalar_is_unknown(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas is not installed")
        self.assertIsNone(parse_width_m(pd.NA))


class GradingTests(unittest.TestCase):
    def test_perfect_wheelchair_sidewalk_scores_100(self):
        feature = {
            "surface": "concrete",
            "smoothness": "excellent",
            "width": "1.8",
            "incline": "0%",
            "incline:across": "0%",
            "wheelchair": "yes",
            "highway": "footway",
            "access": "yes",
            "foot": "yes",
            "lit": "yes",
        }
        result = grade_feature(feature, edge_kind="sidewalk")
        wheelchair = result["profiles"]["wheelchair"]
        self.assertEqual(wheelchair["forward"]["grade"], 100)
        self.assertEqual(wheelchair["backward"]["grade"], 100)
        self.assertTrue(wheelchair["forward"]["allowed"])

    def test_stairs_are_wheelchair_barrier_but_not_blind_barrier(self):
        feature = {
            "surface": "concrete",
            "smoothness": "good",
            "width": "1.5",
            "highway": "steps",
        }
        result = grade_feature(
            feature,
            edge_kind="stairs",
            estimated_slope_percent=5,
            slope_source="local_lidar_dtm",
            slope_confidence=90,
        )
        self.assertFalse(
            result["profiles"]["wheelchair"]["forward"]["allowed"]
        )
        self.assertTrue(result["profiles"]["blind"]["forward"]["allowed"])
        self.assertLessEqual(
            result["profiles"]["blind"]["forward"]["grade"], 40
        )

    def test_uphill_and_downhill_grades_are_directional(self):
        feature = {
            "surface": "concrete",
            "smoothness": "good",
            "width": "1.5",
            "incline:across": "1%",
            "wheelchair": "yes",
            "highway": "footway",
        }
        result = grade_feature(
            feature,
            edge_kind="sidewalk",
            estimated_slope_percent=10,
            slope_source="local_lidar_dtm",
            slope_confidence=90,
        )
        wheelchair = result["profiles"]["wheelchair"]
        self.assertLess(
            wheelchair["forward"]["grade"], wheelchair["backward"]["grade"]
        )

    def test_missing_information_reduces_confidence(self):
        result = grade_feature({}, edge_kind="sidewalk")
        self.assertLess(
            result["profiles"]["wheelchair"]["forward"]["confidence"], 20
        )

    def test_raised_crossing_kerb_caps_wheelchair_grade(self):
        feature = {
            "surface": "concrete",
            "smoothness": "excellent",
            "width": "1.8",
            "incline": "0%",
            "incline:across": "0%",
            "wheelchair": "yes",
            "crossing": "traffic_signals",
            "associated_kerbs": ["flush", "raised"],
            "associated_tactile_paving": ["yes", "yes"],
        }
        result = grade_feature(feature, edge_kind="crossing")
        self.assertLessEqual(
            result["profiles"]["wheelchair"]["forward"]["grade"], 15
        )

    def test_compact_properties_include_both_directions(self):
        result = grade_feature({}, edge_kind="footway")
        properties = compact_grade_properties(result)
        self.assertIn("wheelchair_grade_fwd", properties)
        self.assertIn("wheelchair_grade_bwd", properties)
        self.assertIn("blind_confidence", properties)

    def test_compact_limit_comes_from_worse_direction(self):
        feature = {
            "surface": "concrete",
            "smoothness": "excellent",
            "width": "1.8",
            "incline": "-10%",
            "incline:across": "0%",
            "wheelchair": "yes",
        }
        result = grade_feature(feature, edge_kind="sidewalk")
        properties = compact_grade_properties(result)
        self.assertLess(
            properties["wheelchair_grade_bwd"],
            properties["wheelchair_grade_fwd"],
        )
        self.assertEqual(properties["wheelchair_limit"], "incline")


if __name__ == "__main__":
    unittest.main()
