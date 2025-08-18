# -*- coding: utf-8 -*-

import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from functions import *


class StandaloneLegendHTML:
    def __init__(self, title="Legend"):
        self.elements = []
        self.title = title

    def add_element(self, element_type, label, **kwargs):
        """
        Add a custom element to the legend based on the element type.

        Parameters:
        element_type (str): The type of element ('line', 'marker', 'patch').
        label (str): The label for the element.
        **kwargs: Additional keyword arguments for the element.
        """
        if element_type == "line":
            self.add_line(label=label, **kwargs)
        elif element_type == "marker" or element_type == "circle":
            self.add_marker(label=label, **kwargs)
        elif element_type == "patch" or element_type == "fill":
            self.add_patch(label=label, **kwargs)
        else:
            raise ValueError(
                f"Unknown element type: {element_type}. Supported types are 'line', 'marker'/'circle', and 'patch'/'fill'."
            )

    def add_line(self, label="Line", **kwargs):
        self.elements.append({"type": "line", "label": label, "properties": kwargs})

    def add_marker(self, marker="o", label="Marker", **kwargs):
        kwargs["marker"] = marker
        self.elements.append({"type": "marker", "label": label, "properties": kwargs})

    def add_patch(self, facecolor="orange", edgecolor="w", label="Patch", **kwargs):
        kwargs["facecolor"] = facecolor
        kwargs["edgecolor"] = edgecolor
        self.elements.append({"type": "patch", "label": label, "properties": kwargs})

    def _generate_css(self):
        return """
        :root {
            --text-size: 1em;
            --symbol-size: 18px;
            --symbol-width: 30px;
            --line-height: 1.5;
            --symbol-container-height: 20px;
        }
        body {
            font-family: sans-serif;
        }
        .legend-title {
            font-size: calc(var(--text-size) * 1.2);
            font-weight: bold;
            margin-bottom: 10px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            margin-bottom: 8px;
            font-size: var(--text-size);
            line-height: var(--line-height);
        }
        .legend-symbol-container {
            display: flex;
            align-items: center;
            justify-content: center;
            width: var(--symbol-width);
            height: var(--symbol-container-height);
            margin-right: 10px;
            flex-shrink: 0;
        }
        .legend-symbol {
            display: block;
        }
        .line {
            height: 3px;
            width: var(--symbol-width);
        }
        .marker {
            height: var(--symbol-size);
            width: var(--symbol-size);
        }
        .patch {
            height: var(--symbol-size);
            width: var(--symbol-width);
            border: 2px solid;
        }
        .circle {
            border-radius: 50%;
        }
        .legend-text {
            line-height: var(--symbol-container-height);
        }
        """

    def _generate_html_body(self):
        body = f'<div class="legend-title">{self.title}</div>'
        for element in self.elements:
            label = element["label"]
            props = element["properties"]
            symbol_html = ""
            style = ""

            if element["type"] == "line":
                style += f"background-color: {props.get('color', 'black')};"
                # Override height if linewidth is specified, but keep it reasonable
                if props.get("linewidth"):
                    height = max(
                        1, min(6, props.get("linewidth"))
                    )  # Clamp between 1-6px
                    style += f" height: {height}px;"
                if props.get("dashes"):
                    style += (
                        " border-style: dashed; border-width: 2px 0; background-color: transparent; border-color: "
                        + props.get("color", "black")
                        + ";"
                    )
                    style = style.replace(
                        "background-color: " + props.get("color", "black") + ";", ""
                    )
                symbol_html = (
                    f'<span class="legend-symbol line" style="{style}"></span>'
                )

            elif element["type"] == "marker":
                style += f"background-color: {props.get('markerfacecolor', 'black')};"
                # Use consistent size for all markers, but allow some customization
                marker_size = props.get("markersize", 18)
                if marker_size:
                    # Scale down large marker sizes to fit within our standard
                    size = min(18, max(8, marker_size))
                    style += f" height: {size}px; width: {size}px;"
                marker_type = "marker"
                if props.get("marker") == "o":
                    marker_type += " circle"
                symbol_html = (
                    f'<span class="legend-symbol {marker_type}" style="{style}"></span>'
                )

            elif element["type"] == "patch":
                style += f"background-color: {props.get('facecolor', 'orange')}; border-color: {props.get('edgecolor', 'black')};"
                symbol_html = (
                    f'<span class="legend-symbol patch" style="{style}"></span>'
                )

            body += f'<div class="legend-item"><div class="legend-symbol-container">{symbol_html}</div><span class="legend-text">{label}</span></div>'
        return body

    def export_full_page(self, filename="legend.html", **kwargs):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{self.title}</title>
            <style>{self._generate_css()}</style>
        </head>
        <body>
            {self._generate_html_body()}
        </body>
        </html>
        """
        with open(filename, "w") as f:
            f.write(html)

    def export_elements(self):
        return self._generate_css(), self._generate_html_body()

    def export(self, filename="legend.html", **kwargs):
        """
        Export method for compatibility with the original StandaloneLegend.
        Exports to HTML instead of PNG.
        """
        # Check if filename has .png extension and change it to .html
        if filename.endswith(".png"):
            filename = filename.replace(".png", ".html")

        self.export_full_page(filename, **kwargs)


if __name__ == "__main__":
    # Example usage:
    legend = StandaloneLegendHTML(title="My Dynamic Legend")
    legend.add_line(label="Road", color="black", linewidth=4)
    legend.add_line(label="Path", color="brown", dashes=[2, 2])
    legend.add_marker(
        label="Point of Interest", marker="o", markerfacecolor="blue", markersize=10
    )
    legend.add_patch(label="Park Area", facecolor="green", edgecolor="darkgreen")

    # Using add_element iteratively
    elements = [
        ("line", {"color": "red", "linewidth": 2, "label": "Red Line"}),
        (
            "marker",
            {
                "marker": "s",
                "markerfacecolor": "purple",
                "markersize": 10,
                "label": "Square Marker",
            },
        ),
        (
            "patch",
            {"facecolor": "yellow", "edgecolor": "black", "label": "Yellow Patch"},
        ),
    ]

    for elem_type, kwargs in elements:
        legend.add_element(elem_type, label=kwargs.pop("label"), **kwargs)

    # create a test folder if it does not exist
    if not os.path.exists("tests"):
        os.makedirs("tests")

    # Demonstrate export_full_page
    legend.export_full_page("tests/legend_full_page.html")
    print("Generated full HTML legend in tests/legend_full_page.html")

    # Demonstrate export_elements
    css, html_div = legend.export_elements()

    example_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Embedded Legend Example</title>
        <style>
            {css}
            body {{
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }}
            .legend-container {{
                border: 1px solid #ccc;
                padding: 20px;
                border-radius: 5px;
            }}
        </style>
    </head>
    <body>
        <div class="legend-container">
            {html_div}
        </div>
    </body>
    </html>
    """

    with open("tests/example.html", "w") as f:
        f.write(example_html)
    print("Generated example HTML with embedded legend in tests/example.html")
