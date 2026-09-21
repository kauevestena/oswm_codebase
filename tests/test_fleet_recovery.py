"""Regression cases from the September 20 node failures (no live services)."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from node_outputs import stage_profile
from overpass_acquisition import features_from_polygon_with_failover, OverpassAcquisitionError

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True, text=True,
                          capture_output=True).stdout.strip()


def init(root):
    git(root, 'init', '-b', 'main')
    git(root, 'config', 'user.name', 'Test')
    git(root, 'config', 'user.email', 'test@example.invalid')


class WeeklyPublicationTests(unittest.TestCase):
    def test_api_indices_are_committed_without_unrelated_products(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init(root)
            names = ['data/index.json', 'data/raw/index.json',
                     'data/tiles/index.json', 'data/raw/source.parquet', 'config.py']
            for name in names:
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('old')
            git(root, 'add', '.')
            git(root, 'commit', '-m', 'baseline')
            for name in names:
                (root / name).write_text('new')
            (root / 'data/tiles/index.json').unlink()
            (root / 'data/raw/nested').mkdir()
            (root / 'data/raw/nested/index.json').write_text('{}')
            stage_profile(root, 'weekly')
            staged = set(git(root, 'diff', '--cached', '--name-only').splitlines())
            self.assertEqual(staged, {'data/index.json', 'data/raw/index.json',
                                     'data/tiles/index.json', 'data/raw/nested/index.json'})

    def test_weekly_commit_leaves_clean_tree_for_rebase(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            init(root)
            (root / 'data').mkdir()
            (root / 'data/index.json').write_text('old')
            git(root, 'add', '.')
            git(root, 'commit', '-m', 'baseline')
            baseline = git(root, 'rev-parse', 'HEAD')
            (root / 'data/index.json').write_text('new')
            stage_profile(root, 'weekly')
            git(root, 'commit', '-m', 'weekly')
            git(root, 'rebase', baseline)
            self.assertEqual(git(root, 'status', '--porcelain'), '')

    def test_queued_writer_refreshes_branch_before_generating(self):
        for name in ['weekly.yml', 'data_daily_updating.yml']:
            workflow = (ROOT / 'workflows' / name).read_text()
            checkout = workflow.split('uses: actions/checkout@v4', 1)[1].split('      - ', 1)[0]
            self.assertIn('ref: ${{ github.ref_name }}', checkout)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin, daily, weekly = (root / p for p in ['origin.git', 'daily', 'weekly'])
            git(root, 'init', '--bare', str(origin))
            daily.mkdir()
            init(daily)
            (daily / 'product').write_text('initial')
            git(daily, 'add', '.')
            git(daily, 'commit', '-m', 'initial')
            git(daily, 'remote', 'add', 'origin', str(origin))
            git(daily, 'push', 'origin', 'main')
            queued_sha = git(daily, 'rev-parse', 'HEAD')
            git(root, 'clone', '--branch', 'main', str(origin), str(weekly))
            (daily / 'product').write_text('daily')
            git(daily, 'commit', '-am', 'daily')
            git(daily, 'push', 'origin', 'main')
            git(weekly, 'checkout', '--detach', queued_sha)
            self.assertEqual((weekly / 'product').read_text(), 'initial')
            # Explicit branch checkout resolves the ref when the queued job starts.
            git(weekly, 'fetch', 'origin', 'main')
            git(weekly, 'checkout', '-B', 'main', 'origin/main')
            self.assertEqual((weekly / 'product').read_text(), 'daily')
            self.assertEqual(git(weekly, 'rev-parse', 'HEAD'), git(daily, 'rev-parse', 'HEAD'))


class CompletenessDownloadTests(unittest.TestCase):
    def loader(self, root, provider):
        # Isolate the real download function from unrelated node-config imports.
        source = ROOT / 'data_quality/completeness/completeness_lib.py'
        tree = ast.parse(source.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'fetch_or_load_roads')
        cache = root / 'roads.parquet'
        settings = SimpleNamespace(OVERPASS_ENDPOINTS=('primary', 'backup'),
                                   OVERPASS_ATTEMPTS_PER_ENDPOINT=2,
                                   OVERPASS_BACKOFF_SECONDS=0)
        namespace = dict(os=os, ROADS_CACHE_PATH=str(cache), ROAD_HIGHWAY_TYPES=['residential'],
                         node_config=settings, DEFAULT_OVERPASS_ENDPOINTS=('unused',),
                         box=lambda *bounds: bounds,
                         features_from_polygon_with_failover=features_from_polygon_with_failover,
                         create_folder_if_not_exists=lambda p: Path(p).mkdir(exist_ok=True),
                         gpd=SimpleNamespace(read_parquet=lambda p: 'cached'))
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        return namespace['fetch_or_load_roads'], cache

    def test_timeout_uses_backup_and_preserves_bounds_and_settings(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class Roads:
                geometry = SimpleNamespace(geom_type=SimpleNamespace(isin=lambda values: [True]))
                def __getitem__(self, key): return self
                def copy(self): return self
                def reset_index(self, **kwargs): return self
                def to_parquet(self, path): Path(path).write_text('roads')
                def __len__(self): return 1
            ox = SimpleNamespace(settings=SimpleNamespace(overpass_url='original'))
            def fetch(polygon, tags):
                calls.append((ox.settings.overpass_url, polygon, tags))
                if ox.settings.overpass_url == 'primary':
                    raise TimeoutError('September 20 connection timeout')
                return Roads()
            ox.features_from_polygon = fetch
            loader, cache = self.loader(root, ox)
            bounds = (-77.2, -12.52, -76.62, -11.57)
            with patch.dict(sys.modules, osmnx=ox):
                loader(bounds, silent=True)
                self.assertEqual(loader(bounds, silent=True), 'cached')
            self.assertEqual([c[0] for c in calls], ['primary', 'primary', 'backup'])
            self.assertTrue(all(c[1] == bounds for c in calls))
            self.assertTrue(all(c[2] == {'highway': ['residential']} for c in calls))
            self.assertTrue(cache.exists())
            self.assertEqual(ox.settings.overpass_url, 'original')

    def test_exhausted_providers_fail_without_writing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            ox = SimpleNamespace(settings=SimpleNamespace(overpass_url='original'))
            def fetch(*args):
                calls.append(ox.settings.overpass_url)
                raise TimeoutError('offline')
            ox.features_from_polygon = fetch
            loader, cache = self.loader(Path(directory), ox)
            with patch.dict(sys.modules, osmnx=ox), self.assertRaises(OverpassAcquisitionError):
                loader((-77.2, -12.52, -76.62, -11.57), silent=True)
            self.assertEqual(calls, ['primary', 'primary', 'backup', 'backup'])
            self.assertFalse(cache.exists())
            self.assertEqual(ox.settings.overpass_url, 'original')


if __name__ == '__main__':
    unittest.main()
