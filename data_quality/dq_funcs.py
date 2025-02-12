import sys

sys.path.append("oswm_codebase")

from functions import *
import csv


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
        "zoom": 12,
        "baselayer": "Geofabrik Topo",
        "lat": boundaries_infos["center"][1],
        "lon": boundaries_infos["center"][0],
        "opacity": "0.5",
    }

    themes_dict = {
        "Highways Theme": {
            "params": {"view": "highways", "overlays": ["unknown_way", "unknown_node"]},
            "description": "Detections related to highways, we kept only the ones with unknown tags, like nodes improperly tagged as footways",
        },
        "Geometry Theme": {
            "params": {
                "view": "geometry",
                "overlays": [],
            },
            "description": "Detections related to geometry, many detections pertains roads",
        },
        "Routing Theme": {
            "params": {
                "view": "routing",
                "overlays": [
                    "duplicated_edges",
                    "duplicated_edges",
                    "duplicated_edges_areas",
                    "islands_all",
                ],
            },
            "description": "Detections related to routing, we kept only duplicated edges (in general) and non car/bike islands. Keep in mind that some 'islands' are meant to be as such.",
        },
        "Tagging Theme": {
            "params": {"view": "tagging", "overlays": []},
            "description": "Detections related to tagging, can regard any kind of feature",
        },
        "Area Theme": {
            "params": {"view": "areas", "overlays": []},
            "description": "Can hold detections about Pedestrian Areas, but most aren't about them",
        },
    }

    # the wrongly encoded base layer name:
    wrongly_enc_bs_name = "Geofabrik+Topo"

    themes_content = ""

    for theme_name in themes_dict:
        # fixing the behavior of list encoding:
        theme_params = themes_dict[theme_name]["params"]
        theme_params["overlays"] = ",".join(theme_params["overlays"])

        # update the params
        params.update(theme_params)
        url = encode_url_requests(base_url, params).replace(
            wrongly_enc_bs_name, "Geofabrik Topo"
        )

        # update the content
        themes_content += f"""
            <tr>
                <td><a href="{url}">{theme_name}</a></td>
                <td>{themes_dict[theme_name]["description"]}</td>
            </tr>
        """

    inner_content = f"""
        <p>
            Geofabrik offers
            <a href="https://wiki.openstreetmap.org/wiki/OSM_Inspector">
                OSM Inspector.
            </a>
            A visualization tool containing detections for potential errors in OSM features.
            We curated some themes that can be correlated to Pedestrian data, but some may include highways, bridges, etc. You can navigate through the following themes:
        </p>
        
        <table>
            <tr>
                <th>Theme (link)</th>
                <th>Description</th>
            </tr>

            {themes_content}
            
        </table>
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
