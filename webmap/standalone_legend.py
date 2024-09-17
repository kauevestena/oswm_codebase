import numpy as np
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from functions import *


# thx ChatGPT, employed to transform a scratch code into the class
class StandaloneLegend:
    def __init__(self):
        # Initialize the figure for the legend
        self.legend_elements = []
        self.legend_labels = []
        self.legendFig = plt.figure("Legend plot")

    def add_line(self, label="Line", **kwargs):
        """
        Add a line to the legend with customizable parameters.

        Parameters:
        label (str): The label for the line element.
        **kwargs: Additional keyword arguments for Line2D.
        """

        rename_dict_key(kwargs, "width", "linewidth")

        line = Line2D([0], [0], label=label, **kwargs)
        self.legend_elements.append(line)
        self.legend_labels.append(label)

    def add_marker(self, marker="o", label="Marker", **kwargs):
        """
        Add a marker to the legend with customizable parameters.

        Parameters:
        marker (str): The marker style.
        label (str): The label for the marker element.
        **kwargs: Additional keyword arguments for Line2D.
        """

        # to standardize the key names
        rename_dict_key(kwargs, "color", "markerfacecolor")
        rename_dict_key(kwargs, "width", "markersize")

        # Add default transparent color to kwargs if not provided
        kwargs.setdefault("color", (0.0, 0.0, 0.0, 0.0))
        kwargs.setdefault("markeredgecolor", (0.0, 0.0, 0.0, 0.0))
        marker = Line2D([0], [0], marker=marker, label=label, **kwargs)
        self.legend_elements.append(marker)
        self.legend_labels.append(label)

    def add_patch(self, facecolor="orange", edgecolor="w", label="Patch", **kwargs):
        """
        Add a patch to the legend with customizable parameters.

        Parameters:
        facecolor (str): The face color of the patch.
        edgecolor (str): The edge color of the patch.
        label (str): The label for the patch element.
        **kwargs: Additional keyword arguments for Patch.
        """

        # rename_dict_key(kwargs, "facecolor", "markerfacecolor")

        if "width" in kwargs:
            kwargs.pop("width")

        patch = Patch(facecolor=facecolor, edgecolor=edgecolor, label=label, **kwargs)
        self.legend_elements.append(patch)
        self.legend_labels.append(label)

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

    def add_elements(self, elements):
        """
        Add multiple custom elements to the legend.

        Parameters:
        elements (list): A list of tuples containing the element type and its parameters.
        """
        for element_type, kwargs in elements:
            self.add_element(element_type, **kwargs)

    def __hash__(self) -> int:
        # enable hashing of the object, example: legend = StandaloneLegend(); hash(legend)
        return hash((self.legend_elements, self.legend_labels))

    def export(self, filename="legend.png"):
        # Export the legend to an image file
        self.legendFig.legend(
            handles=self.legend_elements, labels=self.legend_labels, loc="center"
        )
        self.legendFig.savefig(filename, bbox_inches="tight", transparent=True)
        plt.close(self.legendFig)  # Close the figure to free memory


# # Example usage:
# legend = StandaloneLegend()
# legend.add_line(color='b', linewidth=4, label='Line')
# legend.add_marker(marker='o', markerfacecolor='g', markersize=15, label='Marker')
# legend.add_patch(facecolor='orange', edgecolor='r', label='Patch')
# # Using add_element iteratively
# elements = [
#     ('line', {'color': 'red', 'linewidth': 2, 'label': 'Red Line'}),
#     ('marker', {'marker': 's', 'markerfacecolor': 'blue', 'markersize': 10, 'label': 'Square Marker'}),
#     ('patch', {'facecolor': 'yellow', 'edgecolor': 'black', 'label': 'Yellow Patch'})
# ]

# for elem_type, kwargs in elements:
#     legend.add_element(elem_type, **kwargs)

# legend.export('tests/legend.png')
