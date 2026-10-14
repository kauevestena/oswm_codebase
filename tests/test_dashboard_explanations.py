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


if __name__ == "__main__":
    unittest.main()
