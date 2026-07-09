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

dot_lines = [
    "digraph Ontology {",
    "  dpi=150;",
    "  rankdir=BT;",
    "  nodesep=0.7;",
    "  ranksep=1.2;",
    "  node [shape=box, style=\"filled,rounded\", fontname=\"Arial\", margin=\"0.3,0.15\", fontsize=32];",
    "  edge [fontname=\"Arial\", fontsize=24];"
]

for cls in classes:
    color = colors.get(cls, "#FFFFFF")
    dot_lines.append(f'  "{cls}" [fillcolor="{color}"];')

for sub, sup in subclasses:
    dot_lines.append(f'  "{sub}" -> "{sup}" [label="is_a", color="#004C99", fontcolor="#004C99", penwidth=2];')

for dom, prop, rng in properties:
    dot_lines.append(f'  "{dom}" -> "{rng}" [label="{prop}", color="#004C99", fontcolor="#004C99", style="dashed", dir="forward", constraint=false, penwidth=2];')

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
