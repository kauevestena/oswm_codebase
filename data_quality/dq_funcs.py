import sys

sys.path.append("oswm_codebase")

from functions import *
import csv

used_z_level = 12

boundaries_infos = get_boundaries_infos()

qc_mainpage_path = "quality_check/oswm_qc_main.html"
qc_externalpage_path = "quality_check/oswm_qc_external.html"

occurrence_per_feature = {k: {} for k in geom_type_dict.keys()}

js_functions_dq = f"""
    <script src="../oswm_codebase/assets/js_functions/topbar.js"></script>
"""


styles_dq = f"""
    <link rel="stylesheet" href="../oswm_codebase/assets/styles/topnav_styles.css">
    <link rel="stylesheet" href="../oswm_codebase/assets/styles/accordion.css">
"""


def add_to_occurrences(category, id):
    if id in occurrence_per_feature[category]:
        occurrence_per_feature[category][id] += 1
    else:
        occurrence_per_feature[category][id] = 1


def gen_content_OSMI():
    base_url = "https://tools.geofabrik.de/osmi/"

    params = {
        "view": "geometry",  # let the default
        "zoom": used_z_level,
        "baselayer": "Geofabrik Topo",
        "lat": boundaries_infos["center"][1],
        "lon": boundaries_infos["center"][0],
        "opacity": "0.5",
    }

    # the wrongly encoded base layer name:
    wrongly_enc_bs_name = "Geofabrik+Topo"

    url = encode_url_requests(base_url, params).replace(
        wrongly_enc_bs_name, "Geofabrik Topo"
    )

    themes_content = f"""
    <button><a href="{url}">Geometry Theme</a></button>
    """

    inner_content = f"""
        <p>
            Geofabrik offers
            <a href="https://wiki.openstreetmap.org/wiki/OSM_Inspector">
                OSM Inspector.
            </a>

            We curated some themes that can be correlated to Pedestrian data, but some may include highways, bridges, etc.
        </p>

        {themes_content}
    """

    content = details_item("OSM Inspector (Geofabrik)", inner_content)

    return content


def gen_content_osmose():
    inner_content = f"""
    TBD
    """

    content = details_item("Osmose (OSM France)", inner_content)

    return content


def details_item(title, content):
    return f"""
    <details>
        <summary>{title}</summary>
        <div class="content">
            {content}
        </div>
    </details>
    """


def write_dq_topbar(active_index=1):

    active_handler = 'class="active"'

    entries_list = [
        f'<a href="{node_homepage_url}">Go to Node Home</a>',
        f'<a href="{node_homepage_url}{qc_mainpage_path}">OSWM DQ Main</a>',
        f'<a href="{node_homepage_url}{qc_externalpage_path}">External Providers</a>',
    ]

    entries = ""

    for index, entry in enumerate(entries_list):
        if index == active_index:
            entries += entry.replace("<a", f"<a {active_handler}") + "\n"
        else:
            entries += entry + "\n"

    topbar = f"""
    
    <div class="topnav" id="myTopnav">
        {entries}
        <a href="javascript:void(0);" class="icon" onclick="topnav()">
            <i class="fa fa-bars"></i>
         </a>
        
    </div>
    """

    return topbar
