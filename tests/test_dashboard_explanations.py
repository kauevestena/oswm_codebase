"""Check dashboard explanation output without loading geospatial datasets."""

import ast
from html.parser import HTMLParser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def explanation_namespace():
    # These templates are independent of the data-loading imports in this module.
    source = ast.parse((ROOT / "dashboard/statistics_funcs.py").read_text())
    assignments = [
        node for node in source.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name)
                and (target.id == "explanation_base" or target.id.endswith("_link"))
                for target in node.targets)
    ]
    namespace = {}
    exec(compile(ast.Module(body=assignments, type_ignores=[]), "templates", "exec"), namespace)
    return namespace


class ExplanationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.outer = None
        self.links = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.outer is None:
            self.outer = (tag, attrs)
        if tag == "a":
            self.links.append(attrs["href"])

    def handle_data(self, text):
        self.text.append(text)


class DashboardExplanationTests(unittest.TestCase):
    def test_explanation_uses_responsive_content_area(self):
        """The explanatory text must use the same sidebar clearance as page content."""
        parser = ExplanationParser()
        parser.feed(explanation_namespace()["explanation_base"].format("Example explanation"))
        tag, attrs = parser.outer
        self.assertEqual(tag, "div")
        self.assertIn("content", attrs.get("class", "").split())
        self.assertNotIn("style", attrs)  # Do not override responsive spacing inline.
        self.assertIn("Explanation:", parser.text)
        self.assertIn("Example explanation", parser.text)

    def test_kerb_explanation_documents_the_plotted_fields(self):
        namespace = explanation_namespace()
        namespace["oswm_footway_fieldname"] = "category"
        source = ast.parse((ROOT / "dashboard/statistics_specs.py").read_text())
        function = next(node for node in source.body
                        if isinstance(node, ast.FunctionDef) and node.name == "get_charts_specs")
        # Chart builders are not invoked when constructing the specification dictionary.
        for node in ast.walk(function):
            if isinstance(node, ast.Name) and node.id.startswith("create_"):
                namespace[node.id] = lambda **kwargs: None
        exec(compile(ast.Module(body=[function], type_ignores=[]), "specs", "exec"), namespace)
        chart = namespace["get_charts_specs"]({})["kerbs"]["kerbs_x_paving_x_wheelchair"]
        parser = ExplanationParser()
        parser.feed(namespace["explanation_base"].format(chart["explanation"]))
        documented_fields = {url.rsplit("Key:", 1)[-1] for url in parser.links}
        plotted_fields = {chart["params"][field] for field in ("xs", "ys", "hcolor")}
        self.assertEqual(documented_fields, plotted_fields)


if __name__ == "__main__":
    unittest.main()
