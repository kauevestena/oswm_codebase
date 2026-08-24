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
        cls.tiles_generator = (
            ROOT / "generation" / "routing_tiles_gen.py"
        ).read_text(encoding="utf-8")
        cls.worker = (ROOT / "routing" / "routing_worker.js").read_text(
            encoding="utf-8"
        )
        cls.daily_workflow = (
            ROOT / "workflows" / "data_daily_updating.yml"
        ).read_text(encoding="utf-8")
        cls.daily_runner = (ROOT / "runners" / "daily.sh").read_text(
            encoding="utf-8"
        )
        cls.api_generator = (
            ROOT / "datahub" / "API" / "generate_api.py"
        ).read_text(encoding="utf-8")

    def test_client_uses_binary_graph_worker(self):
        self.assertIn("new Worker(", self.html)
        self.assertIn("routing_worker.js", self.html)
        self.assertIn("graph_profile_order", self.html)
        self.assertIn("workerRequest('snap'", self.html)
        self.assertIn("workerRequest('route'", self.html)
        self.assertNotIn("geojson-path-finder", self.html)
        self.assertNotIn("@turf", self.html)
        self.assertNotIn("demo.geojson", self.html)

    def test_worker_has_indexed_snapping_and_astar(self):
        self.assertIn("graph.cellOffsets", self.worker)
        self.assertIn("graph.cellSegments", self.worker)
        self.assertIn("class MinHeap", self.worker)
        self.assertIn("candidate + heuristic(target)", self.worker)
        self.assertIn("sanitizeSnap", self.worker)

    def test_profile_selector_and_directional_grades_are_wired(self):
        self.assertIn('id="profileSelect"', self.html)
        self.assertIn("graph_profile_order", self.generator)
        self.assertIn("build_binary_graph", self.generator)

    def test_distance_profile_and_optional_comparison_are_wired(self):
        self.assertIn('id="compareDistance"', self.html)
        self.assertIn("profilePayload.distance_profile_id", self.html)
        self.assertIn("profile.routing_mode === 'distance'", self.html)
        self.assertIn("comparisonProfileId", self.html)
        self.assertIn("distance-comparison-path-layer", self.html)
        self.assertIn('id="comparisonDelta"', self.html)
        self.assertNotIn('<option value="distance">', self.html)

    def test_generator_emits_profile_metadata_and_slope_cache(self):
        self.assertIn("routing_profiles_path", self.generator)
        self.assertIn("routing_metadata_path", self.generator)
        self.assertIn("routing_slope_cache_path", self.generator)
        self.assertIn("routing_graph_path", self.generator)
        self.assertIn("routing_parquet_path", self.generator)
        self.assertIn("_write_geoparquet", self.generator)
        self.assertNotIn("routing_demo_path", self.generator)
        self.assertNotIn("routing_collection", self.generator)
        self.assertIn("build_binary_graph(\n        output_rows", self.generator)
        self.assertIn("profile_ruleset_hash", self.generator)
        self.assertIn('"distance_profile_id": distance_profile_id', self.generator)
        self.assertIn('"graph_sha256": graph_metadata["sha256"]', self.generator)
        self.assertIn("versionedRoutingUrl", self.html)

    def test_network_rendering_uses_pmtiles(self):
        self.assertIn("PmtilesProtocol", self.html)
        self.assertIn("type: 'vector'", self.html)
        self.assertIn("'source-layer'", self.html)
        self.assertIn("routing_tiles_path", self.tiles_generator)
        self.assertIn("routing_parquet_path", self.tiles_generator)
        self.assertNotIn("routing_demo_path", self.tiles_generator)
        self.assertIn("DISPLAY_LAYER = \"routing\"", self.tiles_generator)

    def test_map_fits_authoritative_boundary_before_graph_is_ready(self):
        boundary = self.html.index("const boundaryPromise = initializeNodeBoundary()")
        display = self.html.index("addMapDisplayLayers();")
        graph = self.html.index("const graphInfo = await graphPromise;")
        self.assertLess(boundary, display)
        self.assertLess(display, graph)
        self.assertIn("map.fitBounds(bounds", self.html)
        self.assertIn("boundary.coordinates || boundary.geometry?.coordinates", self.html)
        self.assertNotIn("map.fitBounds([[minLon, minLat]", self.html)

    def test_daily_workflow_caches_elevation_tiles(self):
        self.assertIn("actions/cache@v4", self.daily_workflow)
        self.assertIn(".cache/oswm/elevation", self.daily_workflow)
        self.assertIn("routing_tiles_gen.py", self.daily_runner)

    def test_data_api_lists_generated_routing_artifacts(self):
        for filename in (
            "network.parquet",
            "network.oswmg",
            "network.pmtiles",
            "tile_generation_report.json",
            "profiles.json",
            "metadata.json",
            "slope_cache.json",
        ):
            self.assertIn(filename, self.api_generator)
        self.assertNotIn("demo.geojson", self.api_generator)


if __name__ == "__main__":
    unittest.main()
