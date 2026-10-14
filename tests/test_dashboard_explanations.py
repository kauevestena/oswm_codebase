"""Regression for explanatory text hidden behind dashboard category navigation."""
import ast
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExplanationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.text_containers = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs.get("href"))
        self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_data(self, text):
        if text.strip():
            self.text_containers.append(
                (text.strip(), [attrs for tag, attrs in self.stack if tag == "div"])
            )


class DashboardExplanationTests(unittest.TestCase):
    def test_heading_and_linked_explanation_share_sidebar_aware_content(self):
        # Load the generator's actual template without acquisition/geospatial globals.
        tree = ast.parse((ROOT / "dashboard/statistics_funcs.py").read_text())
        template = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "explanation_base" for t in node.targets)
        )
        parser = ExplanationParser()
        parser.feed(template.format(
            'Inspect the <a href="https://wiki.openstreetmap.org/wiki/Key:surface">surface</a> values.'
        ))
        self.assertIn("https://wiki.openstreetmap.org/wiki/Key:surface", parser.links)
        self.assertTrue(any(text == "Explanation:" for text, _ in parser.text_containers))
        self.assertTrue(any(text == "surface" for text, _ in parser.text_containers))
        for text, containers in parser.text_containers:
            with self.subTest(text=text):
                # Existing div.content rules reserve the sidebar width on desktop
                # and remove that offset below 700px. All explanatory text needs
                # that layout, including nested links.
                self.assertTrue(any(
                    "content" in attrs.get("class", "").split() for attrs in containers
                ))
                self.assertFalse(any(
                    "margin-left" in attrs.get("style", "") for attrs in containers
                ), "Inline margin must not override the mobile layout")


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


class KerbExplanationTests(unittest.TestCase):
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
