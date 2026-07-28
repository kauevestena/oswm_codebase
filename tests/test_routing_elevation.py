import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

from routing.elevation import (
    COGElevationProvider,
    CopernicusGLO30Provider,
    ElevationResolver,
    SlopeEstimate,
    copernicus_tile_name,
    copernicus_tile_url,
    load_slope_cache,
    robust_slope_percent,
    save_slope_cache,
)


class CopernicusNamingTests(unittest.TestCase):
    def test_southern_western_tile_name(self):
        self.assertEqual(
            copernicus_tile_name(-25.46, -49.26),
            "Copernicus_DSM_COG_10_S26_00_W050_00_DEM",
        )

    def test_northern_eastern_tile_name(self):
        self.assertEqual(
            copernicus_tile_name(50.5, 8.6),
            "Copernicus_DSM_COG_10_N50_00_E008_00_DEM",
        )

    def test_url_repeats_tile_identifier(self):
        tile = copernicus_tile_name(-25.46, -49.26)
        self.assertEqual(
            copernicus_tile_url(-25.46, -49.26),
            f"https://copernicus-dem-30m.s3.amazonaws.com/{tile}/{tile}.tif",
        )

    def test_failed_tile_is_not_downloaded_repeatedly(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = CopernicusGLO30Provider(
                {"cache_dir": directory},
                request_timeout_seconds=1,
            )
            with patch("requests.get", side_effect=OSError("offline")) as request:
                with self.assertRaises(OSError):
                    provider._local_tile(-25.46, -49.26)
                with self.assertRaises(RuntimeError):
                    provider._local_tile(-25.46, -49.26)
            request.assert_called_once()


class SlopeEstimationTests(unittest.TestCase):
    def test_robust_slope_ignores_one_large_outlier(self):
        distances = [0, 10, 20, 30, 40, 50, 60]
        elevations = [100, 101, 102, 150, 104, 105, 106]
        self.assertAlmostEqual(
            robust_slope_percent(distances, elevations), 10.0, places=5
        )

    def test_robust_slope_ignores_invalid_samples(self):
        distances = [0, 10, 20, 30]
        elevations = [100, None, float("nan"), 103]
        self.assertAlmostEqual(
            robust_slope_percent(distances, elevations), 10.0, places=5
        )

    def test_disabled_resolver_returns_missing(self):
        resolver = ElevationResolver({"enabled": False, "providers": []})
        estimate = resolver.estimate(None)
        self.assertEqual(estimate.source, "missing")
        self.assertIsNone(estimate.percent)

    def test_slope_cache_round_trip(self):
        payload = {
            "edge": SlopeEstimate(
                4.25, "local_lidar_dtm", 90, 1, 7
            ).to_dict()
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slope_cache.json"
            save_slope_cache(path, payload)
            self.assertEqual(load_slope_cache(path), payload)

    @unittest.skipUnless(
        find_spec("rasterio") and find_spec("numpy"),
        "rasterio and numpy are not installed",
    )
    def test_configured_raster_provider_samples_local_data(self):
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "elevation.tif"
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=2,
                width=2,
                count=1,
                dtype="float32",
                crs="EPSG:4326",
                transform=from_origin(0, 2, 1, 1),
            ) as dataset:
                dataset.write(
                    np.array([[10, 20], [30, 40]], dtype="float32"),
                    1,
                )

            provider = COGElevationProvider({"path": str(path)})
            self.assertEqual(
                provider.sample([(0.5, 1.5), (1.5, 0.5)]),
                [10.0, 40.0],
            )


if __name__ == "__main__":
    unittest.main()
