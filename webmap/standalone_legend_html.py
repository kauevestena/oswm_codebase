# -*- coding: utf-8 -*-

import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from functions import *


class StandaloneLegendHTML:
    default_line_height = 8
    default_marker_size = 18
    min_marker_display = 12

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

    def _generate_css(self, num_items=None):
        if num_items is None:
            num_items = len(self.elements)

        return f"""
        :root {{
            --text-size: 1em;
            --symbol-size: 18px;
            --symbol-width: 30px;
            --line-height: 1.5;
            --symbol-container-height: 20px;
        }}
        body {{
            font-family: sans-serif;
            background-color: rgba(255, 255, 255, 0.8);
            padding: 10px;
            margin: 0;
            width: 100%;
            min-width: 150px;
            /* Let parent iframe control height and scrolling to avoid feedback loops */
            overflow-y: visible;
            overflow-x: hidden;
            box-sizing: border-box;
            height: auto;
        }}
        .legend-title {{
            font-size: calc(var(--text-size) * 1.2);
            font-weight: bold;
            margin-bottom: 10px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin-bottom: 8px;
            font-size: var(--text-size);
            line-height: var(--line-height);
        }}
        .legend-symbol-container {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: var(--symbol-width);
            height: var(--symbol-container-height);
            margin-right: 10px;
            flex-shrink: 0;
        }}
        .legend-symbol {{
            display: block;
        }}
        .line {{
            height: {self.default_line_height}px; /* a little thicker */
            width: var(--symbol-width);
            border: 1px solid rgba(0, 0, 0, 0.85); /* keep a dark margin */
            box-sizing: border-box;
        }}
        .marker {{
            height: var(--symbol-size);
            width: var(--symbol-size);
        }}
        .patch {{
            height: var(--symbol-size);
            width: var(--symbol-width);
            border: 2px solid;
        }}
        .circle {{
            border-radius: 50%;
        }}
        .legend-text {{
            line-height: var(--symbol-container-height);
            flex: 1;
            min-width: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
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
                # default visible height (keeps parity with .line CSS)
                height = self.default_line_height
                # Override height if linewidth is specified, but keep it reasonable
                # if props.get("linewidth") is not None:
                #     height = max(
                #         2, min(10, props.get("linewidth"))
                #     )  # Clamp between 2-10px
                style += f" height: {height}px;"
                if props.get("dashes"):
                    # For dashed lines, use border instead of background
                    color = props.get("color", "black")
                    # keep a thick dark margin and dashed interior
                    style = (
                        f"background-color: transparent; border-style: dashed; border-width: {max(2, height-1)}px 0; "
                        f"border-color: {color}; box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.85);"
                    )
                symbol_html = (
                    f'<span class="legend-symbol line" style="{style}"></span>'
                )

            elif element["type"] == "marker":
                # marker face color: prefer explicit markerfacecolor, fall back to generic color
                face = props.get("markerfacecolor", props.get("color", "black"))
                style += f"background-color: {face};"
                # border for markers if edgecolor provided
                if props.get("edgecolor"):
                    style += f" border: 1px solid {props.get('edgecolor')};"
                # Determine marker size: prefer explicit markersize, then legend width; enforce minimum display size
                marker_size_raw = props.get("markersize", props.get("width", None))
                if marker_size_raw is None:
                    size = self.default_marker_size
                else:
                    try:
                        size = int(marker_size_raw)
                    except Exception:
                        size = self.default_marker_size
                # enforce sensible bounds
                size = max(self.min_marker_display, min(28, size))
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
        # timestamp in UTC (timezone-aware)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        generated_comment = f"<!-- GENERATED FILE - auto-generated by StandaloneLegendHTML on {ts} - DO NOT EDIT -->\n"

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
        # write with a clear generated-file comment at the top
        with open(filename, "w") as f:
            f.write(generated_comment)
            f.write(html)

    def export_elements(self):
        # return embeddable html prefixed with an HTML comment (no visible banner)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        generated_comment = f"<!-- GENERATED FRAGMENT - auto-generated by StandaloneLegendHTML on {ts} - DO NOT EDIT -->\n"
        return self._generate_css(), generated_comment + self._generate_html_body()

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
