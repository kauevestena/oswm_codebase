from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WebmapWiringTests(unittest.TestCase):
    def test_template_loads_snapshot_styles_and_control(self):
        template = (ROOT / "webmap/webmap_base.html").read_text(encoding="utf8")

        self.assertIn("webmap_snapshot.css", template)
        self.assertIn("import('./oswm_codebase/webmap/snapshot/snapshot_control.js')", template)
        self.assertIn("installSnapshotControl", template)

        composer = (ROOT / "webmap/snapshot/snapshot_composer.js").read_text(
            encoding="utf8"
        )
        self.assertIn("<h2>Theme</h2>", composer)
        self.assertIn("Optional author panel", composer)
        self.assertIn('name="author-content"', composer)

    def test_generator_emits_snapshot_contract(self):
        generator = (ROOT / "webmap/create_webmap_new.py").read_text(encoding="utf8")

        self.assertIn('params["snapshot"]', generator)
        self.assertIn("get_snapshot_themes()", generator)
        self.assertIn("snapshot_summary_path", generator)

    def test_daily_pipeline_generates_summary_before_webmap(self):
        runner = (ROOT / "runners/daily.sh").read_text(encoding="utf8")

        summary_position = runner.index("generate_snapshot_summary.py")
        webmap_position = runner.index("create_webmap_new.py")
        self.assertLess(summary_position, webmap_position)


if __name__ == "__main__":
    unittest.main()
