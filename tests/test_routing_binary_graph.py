import math
import struct
import tempfile
import unittest
from pathlib import Path

from routing.binary_graph import (
    MAGIC,
    SCHEMA_VERSION,
    build_binary_graph,
    read_graph_header,
)


def profile_payload():
    return {
        "distance_profile_id": "distance",
        "profiles": {
            "distance": {"routing_mode": "distance"},
            "wheelchair": {
                "routing_mode": "accessibility_grade",
                "cost": {
                    "grade_multipliers": [
                        {"min_grade": 90, "multiplier": 1.0},
                        {"min_grade": 20, "multiplier": 5.0},
                    ],
                    "event_penalties_m": {
                        "sidewalk": 0,
                        "footway": 0,
                        "crossing": 15,
                        "stairs": None,
                    },
                },
            },
        },
    }


def feature(coordinates, **properties):
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "edge_kind": "sidewalk",
            "length_m": 111.2,
            "wheelchair_allow_fwd": True,
            "wheelchair_allow_bwd": True,
            "wheelchair_grade_fwd": 90,
            "wheelchair_grade_bwd": 20,
            **properties,
        },
    }


class BinaryRoutingGraphTests(unittest.TestCase):
    def test_serializes_topology_profiles_and_spatial_index(self):
        collection = {
            "type": "FeatureCollection",
            "features": [
                feature([[0, 0], [0.001, 0]]),
                feature(
                    [[0.001000001, 0], [0.002, 0]],
                    wheelchair_allow_bwd=False,
                ),
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.oswmg"
            metadata = build_binary_graph(collection, profile_payload(), path)
            header = read_graph_header(path)
            payload = path.read_bytes()

        self.assertEqual(payload[:8], MAGIC)
        self.assertEqual(header["schema_version"], SCHEMA_VERSION)
        self.assertEqual(header["node_count"], 3)
        self.assertEqual(header["directed_edge_count"], 4)
        self.assertEqual(header["profile_count"], 2)
        self.assertEqual(header["segment_count"], 2)
        self.assertGreaterEqual(header["cell_membership_count"], 2)
        self.assertEqual(metadata["profile_order"], ["distance", "wheelchair"])
        self.assertEqual(len(metadata["sha256"]), 64)

        edge_count = header["directed_edge_count"]
        weights_offset = header["weights_offset"]
        weights = struct.unpack_from(f"<{edge_count * 2}f", payload, weights_offset)
        distance_weights = weights[:edge_count]
        accessibility_weights = weights[edge_count:]
        self.assertTrue(all(110 < value < 112 for value in distance_weights))
        self.assertTrue(any(math.isinf(value) for value in accessibility_weights))
        self.assertTrue(any(550 < value < 560 for value in accessibility_weights))

    def test_duplicate_edges_and_rounded_vertices_use_last_write(self):
        collection = {
            "type": "FeatureCollection",
            "features": [
                feature([[0, 0], [0.001, 0]], wheelchair_grade_fwd=20),
                feature(
                    [[0.000000001, 0], [0.001000001, 0]],
                    wheelchair_grade_fwd=90,
                    wheelchair_grade_bwd=90,
                ),
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.oswmg"
            build_binary_graph(collection, profile_payload(), path)
            header = read_graph_header(path)
            payload = path.read_bytes()

        self.assertEqual(header["node_count"], 2)
        self.assertEqual(header["directed_edge_count"], 2)
        weights = struct.unpack_from(
            "<4f", payload, header["weights_offset"]
        )
        # Profile-major storage: the final two entries are wheelchair costs.
        self.assertTrue(any(110 < value < 112 for value in weights[2:]))
        self.assertFalse(any(550 < value < 560 for value in weights[2:]))

    def test_rejects_empty_network(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "must contain features"):
                build_binary_graph(
                    {"type": "FeatureCollection", "features": []},
                    profile_payload(),
                    Path(directory) / "network.oswmg",
                )


if __name__ == "__main__":
    unittest.main()
