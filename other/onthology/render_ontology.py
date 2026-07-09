import xml.etree.ElementTree as ET
import re
import json

import os

script_dir = os.path.dirname(os.path.abspath(__file__))
owl_path = os.path.join(script_dir, 'pathways_oswm.owl')
with open(owl_path, 'r') as f:
    owl_content = f.read()

classes = set(re.findall(r'<Class IRI="([^"]+)"/>', owl_content))
if "Thing" in classes:
    classes.remove("Thing")

subclasses = []
for match in re.finditer(r'<SubClassOf>\s*<Class IRI="([^"]+)"/>\s*<Class IRI="([^"]+)"/>\s*</SubClassOf>', owl_content):
    sub, sup = match.groups()
    if sub != "Thing" and sup != "Thing":
        subclasses.append((sub, sup))

domains = {}
for match in re.finditer(r'<ObjectPropertyDomain>\s*<ObjectProperty IRI="([^"]+)"/>\s*<Class IRI="([^"]+)"/>\s*</ObjectPropertyDomain>', owl_content):
    prop, dom = match.groups()
    prop = prop.replace("&lt;br&gt;", "").replace("<br>", "").strip()
    domains.setdefault(prop, []).append(dom)

ranges = {}
for match in re.finditer(r'<ObjectPropertyRange>\s*<ObjectProperty IRI="([^"]+)"/>\s*<Class IRI="([^"]+)"/>\s*</ObjectPropertyRange>', owl_content):
    prop, rng = match.groups()
    prop = prop.replace("&lt;br&gt;", "").replace("<br>", "").strip()
    ranges.setdefault(prop, []).append(rng)

properties = []
for prop in domains:
    if prop in ranges:
        for dom in domains[prop]:
            for rng in ranges[prop]:
                properties.append((dom, prop, rng))

colors = {
    "Pathway": "#E0E0E0",
    "Footway": "#FFFFCC",
    "Road": "#E0E0E0",
    "Sidewalk": "#FFFFCC",
    "Crossing": "#FFFFCC",
    "Stairway": "#FFFFCC",
    "Informal_Footway": "#FFFFCC",
    "Potential_Footways": "#FFFFCC",
    "PedestrianAreas": "#CCFFE6",
    "TraversibleAreas": "#CCFFE6",
    "KerbAccessPoint": "#CCFFFF",
    "UtilityPoint": "#CCFFFF",
    "Other_Pathways": "#E3E3E3"
}

nodes = []
for cls in classes:
    nodes.append({
        "id": cls,
        "label": cls,
        "color": colors.get(cls, "#FFFFFF"),
        "shape": "box",
        "font": {"size": 32}
    })

edges = []
seen_edges = set()

for sub, sup in subclasses:
    edge_key = (sub, sup, "is_a")
    if edge_key not in seen_edges:
        seen_edges.add(edge_key)
        edges.append({
            "id": f"edge_{len(edges)}",
            "from": sub,
            "to": sup,
            "label": "is_a",
            "color": {"color": "#004C99"},
            "arrows": "to",
            "font": {"align": "middle", "size": 14, "background": "rgba(255, 255, 255, 0.75)", "strokeWidth": 0}
        })

for dom, prop, rng in properties:
    edge_key = (dom, rng, prop)
    if edge_key not in seen_edges:
        seen_edges.add(edge_key)
        edges.append({
            "id": f"edge_{len(edges)}",
            "from": dom,
            "to": rng,
            "label": prop,
            "color": {"color": "#004C99"},
            "arrows": "to",
            "dashes": True,
            "font": {"align": "middle", "size": 14, "background": "rgba(255, 255, 255, 0.75)", "strokeWidth": 0}
        })

nodes_json = json.dumps(nodes)
edges_json = json.dumps(edges)

html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>OSWM Ontology Viewer</title>
    <script src="https://unpkg.com/vis-network@9.1.2/standalone/umd/vis-network.min.js"></script>
    <style>
        body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; font-family: Arial, sans-serif; }}
        #mynetwork {{ width: 100%; height: 100%; }}
        #controls {{ position: absolute; top: 10px; left: 10px; background: rgba(255,255,255,0.9); padding: 10px; border-radius: 5px; box-shadow: 0 0 5px rgba(0,0,0,0.3); z-index: 10; }}
    </style>
</head>
<body>
    <div id="controls">
        <h3>OSWM Ontology</h3>
        <p>Rendered from <code>pathways_oswm.owl</code></p>
        <label for="fontSizeSlider">Class Size: <span id="fontSizeDisplay">32</span></label>
        <br>
        <input type="range" id="fontSizeSlider" min="10" max="60" value="32" oninput="updateFontSize(this.value)">
        <br><br>
        <label for="edgeSizeSlider">Arrow Label Size: <span id="edgeSizeDisplay">14</span></label>
        <br>
        <input type="range" id="edgeSizeSlider" min="8" max="40" value="14" oninput="updateEdgeFontSize(this.value)">
    </div>
    <div id="mynetwork"></div>
    <script>
        var nodes = new vis.DataSet({nodes_json});
        var edges = new vis.DataSet({edges_json});

        var container = document.getElementById('mynetwork');
        var data = {{
            nodes: nodes,
            edges: edges
        }};
        var options = {{
            layout: {{
                hierarchical: false
            }},
            physics: {{
                enabled: true,
                solver: 'barnesHut',
                barnesHut: {{
                    gravitationalConstant: -10000,
                    centralGravity: 0.1,
                    springLength: 350,
                    springConstant: 0.04,
                    damping: 0.09,
                    avoidOverlap: 1
                }}
            }},
            edges: {{
                smooth: {{
                    enabled: true,
                    type: 'cubicBezier',
                    roundness: 0.5
                }}
            }}
        }};
        var network = new vis.Network(container, data, options);
        // disable physics once stabilized to stop spinning and allow free dragging
        network.once("stabilized", function () {{
            network.setOptions({{ physics: false }});
        }});
        // Safety timeout: force-disable physics after 3 seconds in case stabilization hangs
        setTimeout(function() {{
            network.setOptions({{ physics: false }});
        }}, 3000);

        function updateFontSize(newSize) {{
            document.getElementById('fontSizeDisplay').innerText = newSize;
            var updates = [];
            nodes.forEach(function(node) {{
                updates.push({{id: node.id, font: {{size: Number(newSize)}}}});
            }});
            nodes.update(updates);
        }}

        function updateEdgeFontSize(newSize) {{
            document.getElementById('edgeSizeDisplay').innerText = newSize;
            var updates = [];
            edges.forEach(function(edge) {{
                updates.push({{id: edge.id, font: {{size: Number(newSize)}}}});
            }});
            edges.update(updates);
        }}
    </script>
</body>
</html>
"""

output_path = os.path.join(script_dir, 'ontology_viewer.html')
with open(output_path, 'w') as f:
    f.write(html_content)

print("Generated optimized ontology_viewer.html using vis.js successfully!")
