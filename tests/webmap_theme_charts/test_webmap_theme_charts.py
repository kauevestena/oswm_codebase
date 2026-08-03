from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WebmapThemeChartWiringTests(unittest.TestCase):
    def test_template_loads_chart_assets_without_blocking_the_map(self):
        template = (ROOT / "webmap/webmap_base.html").read_text(encoding="utf8")

        self.assertIn("webmap_theme_charts.css", template)
        self.assertIn("echarts@6.1.0/+esm", template)
        self.assertIn("theme_chart_control.js", template)
        self.assertIn("loadECharts: () => import", template)
        self.assertIn("installThemeChartControl(map, params", template)
        self.assertIn("position: 'bottom-left'", template)
        self.assertIn("themeChartControl?.setActiveStyle(style)", template)

    def test_generator_exposes_webmap_only_theme_chart_contract(self):
        generator = (ROOT / "webmap/create_webmap_new.py").read_text(encoding="utf8")
        library = (ROOT / "webmap/webmap_lib.py").read_text(encoding="utf8")

        self.assertIn('params["theme_charts"]', generator)
        self.assertIn('"default_scope": "node"', generator)
        self.assertIn("get_webmap_theme_definitions()", generator)
        self.assertIn('"chart": "bar"', library)
        self.assertIn('"chart": "histogram"', library)
        self.assertIn('return "length" if geometry_types == {"line"} else "count"', library)

    def test_chart_implementation_has_no_dashboard_or_hazard_dependency(self):
        chart_root = ROOT / "webmap/theme_charts"
        implementation = "\n".join(
            path.read_text(encoding="utf8")
            for path in chart_root.glob("*.js")
        ).lower()

        self.assertNotIn("dashboard", implementation)
        self.assertNotIn("hazard", implementation)
        self.assertIn("visible vector tiles", implementation)
        self.assertIn("summary_url", implementation)

    def test_chart_control_includes_scope_and_accessible_table(self):
        control = (
            ROOT / "webmap/theme_charts/theme_chart_control.js"
        ).read_text(encoding="utf8")

        self.assertIn('"Visible area"', control)
        self.assertIn('"live estimate"', control)
        self.assertIn("Entire dataset · exact", control)
        self.assertIn('"Data table"', control)
        self.assertIn('renderer: "svg"', control)


if __name__ == "__main__":
    unittest.main()
