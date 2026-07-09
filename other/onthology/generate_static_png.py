import xml.etree.ElementTree as ET
import re
import os
import subprocess

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

# Font sizing configurations for class nodes and arrow labels
CLASS_FONT_SIZE = 30
ARROW_LABEL_FONT_SIZE = 22

# Row and column index lookup to enforce top-down hierarchy in Graphviz
node_rows = {
    "UtilityPoint": 0,
    "Pathway": 0,
    "TraversibleAreas": 0,
    
    "Road": 1,
    "Footway": 1,
    "Other_Pathways": 1,
    
    "KerbAccessPoint": 2,
    "Informal_Footway": 2,
    "Sidewalk": 2,
    "Crossing": 2,
    "Stairway": 2,
    "Potential_Footways": 2,
    "PedestrianAreas": 2
}

dot_lines = [
    "digraph Ontology {",
    "  dpi=150;",
    "  rankdir=LR;",
    "  splines=true;",
    "  nodesep=0.5;",
    "  ranksep=2.5;",
    f"  node [shape=box, style=\"filled,rounded\", fontname=\"Arial\", margin=\"0.2,0.1\", fontsize={CLASS_FONT_SIZE}];",
    f"  edge [fontname=\"Arial\", fontsize={ARROW_LABEL_FONT_SIZE}];",
    "",
    "  // Invisible dummy nodes to maintain layout grid",
    "  dummy1 [style=invis, label=\"\", width=0.1, height=0.1];",
    "  dummy2 [style=invis, label=\"\", width=0.1, height=0.1];",
    "",
    "  // Rank definitions (Rows)",
    "  { rank=same; UtilityPoint; Pathway; TraversibleAreas; }",
    "  { rank=same; dummy1; Road; Footway; Other_Pathways; dummy2; }",
    "  { rank=same; KerbAccessPoint; Informal_Footway; Sidewalk; Crossing; Stairway; Potential_Footways; PedestrianAreas; }",
    "",
    "  // Horizontal alignment constraints (left-to-right column order)",
    "  UtilityPoint -> Pathway -> TraversibleAreas [style=invis];",
    "  dummy1 -> Road -> Footway -> Other_Pathways -> dummy2 [style=invis];",
    "  KerbAccessPoint -> Informal_Footway -> Sidewalk -> Crossing -> Stairway -> Potential_Footways -> PedestrianAreas [style=invis];",
    "",
    "  // Vertical column constraints",
    "  UtilityPoint -> dummy1 -> KerbAccessPoint [style=invis];",
    "  TraversibleAreas -> dummy2 -> PedestrianAreas [style=invis];",
    "",
    "  // Pathway column vertical alignments",
    "  Pathway -> Footway [style=invis];",
    "  Road -> Informal_Footway [style=invis];",
    "  Footway -> Crossing [style=invis];",
    "  Other_Pathways -> Potential_Footways [style=invis];",
    ""
]

def make_html_label(text):
    return f'<<table border="0" cellborder="0" bgcolor="#ffffffcc"><tr><td><font point-size="{ARROW_LABEL_FONT_SIZE}">{text}</font></td></tr></table>>'

def get_edge_label_attr(dom, prop, rng):
    label_val = make_html_label(prop)
    # Distribute labels to tail or head with distance/angle to prevent center-channel and node-box collisions
    if prop == "is_juxtaposed":
        return f'headlabel={label_val}, labeldistance=3.5, labelangle=-20'
    elif prop == "is_used_as":
        return f'headlabel={label_val}, labeldistance=4.0, labelangle=20'
    elif prop == "Is_above":
        return f'taillabel={label_val}, labeldistance=4.0, labelangle=15'
    elif prop == "probably_is_a":
        return f'headlabel={label_val}, labeldistance=3.0, labelangle=15'
    elif prop == "may_also_be" and rng == "Road":
        return f'taillabel={label_val}, labeldistance=4.5, labelangle=-20'
    elif prop == "may_also_be" and rng == "Other_Pathways":
        return f'taillabel={label_val}, labeldistance=3.5, labelangle=-25'
    elif prop == "contains" and dom == "PedestrianAreas" and rng == "Pathway":
        return f'headlabel={label_val}, labeldistance=4.0, labelangle=20'
    elif prop == "contains" and dom == "PedestrianAreas" and rng == "Footway":
        return f'headlabel={label_val}, labeldistance=3.0, labelangle=-25'
    elif prop == "contains" and dom == "TraversibleAreas" and rng == "Pathway":
        return f'headlabel={label_val}, labeldistance=3.0, labelangle=-20'
    elif prop == "contains" and dom == "TraversibleAreas" and rng == "Footway":
        return f'taillabel={label_val}, labeldistance=3.5, labelangle=25'
    
    return f'label={label_val}'

for cls in classes:
    color = colors.get(cls, "#FFFFFF")
    dot_lines.append(f'  "{cls}" [fillcolor="{color}"];')

# Subclasses (is_a edges)
for sub, sup in subclasses:
    label = make_html_label("is_a")
    # Determine top-down flow direction to prevent Graphviz inversion
    if node_rows.get(sub, 2) > node_rows.get(sup, 0):
        # Draw from parent to child but point arrowhead backward
        dot_lines.append(f'  "{sup}" -> "{sub}" [label={label}, color="#004C99", fontcolor="#004C99", penwidth=2, dir=back, arrowhead=normal];')
    else:
        dot_lines.append(f'  "{sub}" -> "{sup}" [label={label}, color="#004C99", fontcolor="#004C99", penwidth=2];')

# Object properties
for dom, prop, rng in properties:
    label_attr = get_edge_label_attr(dom, prop, rng)
    # Determine top-down flow direction
    if node_rows.get(dom, 2) > node_rows.get(rng, 2):
        dot_lines.append(f'  "{rng}" -> "{dom}" [{label_attr}, color="#004C99", fontcolor="#004C99", style="dashed", penwidth=2, dir=back, arrowhead=normal, constraint=false];')
    else:
        dot_lines.append(f'  "{dom}" -> "{rng}" [{label_attr}, color="#004C99", fontcolor="#004C99", style="dashed", penwidth=2, dir=forward, constraint=false];')

dot_lines.append("}")
dot_string = "\n".join(dot_lines)

dot_path = os.path.join(script_dir, 'graph.dot')
with open(dot_path, 'w') as f:
    f.write(dot_string)

print("Generated graph.dot")

png_output_path = os.path.join(script_dir, 'ontology_static.png')
paper_fig_path = '/home/kaue/OSWM_paper/figures/onthology.png'

# Execute curl request to Kroki API
try:
    print("Calling Kroki API to render PNG...")
    cmd = [
        "curl", "-s", "-X", "POST",
        "-H", "Content-Type: text/plain",
        "--data-binary", f"@{dot_path}",
        "https://kroki.io/graphviz/png",
        "-o", png_output_path
    ]
    subprocess.run(cmd, check=True)
    print(f"Successfully generated {png_output_path}")

    # Copy to paper figures if directory exists
    if os.path.exists(os.path.dirname(paper_fig_path)):
        import shutil
        shutil.copyfile(png_output_path, paper_fig_path)
        print(f"Successfully copied PNG to {paper_fig_path}")
    else:
        print(f"Paper figures directory not found at {os.path.dirname(paper_fig_path)}. Skipping copy.")

finally:
    # Cleanup graph.dot
    if os.path.exists(dot_path):
        os.remove(dot_path)
        print("Cleaned up graph.dot")
