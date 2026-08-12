import sys
import os
from urllib.parse import urlencode

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from functions import *
from branding import branding_asset_url
import csv
import pandas as pd
import requests

# # # constants and setup:
boundaries_infos = get_boundaries_infos()
reversed_centerpoint = list(reversed(boundaries_infos["center"]))  # it expects lat,lon
dq_maps_z_default = 13

bbox_str = join_list_for_req(boundaries_infos["bbox"])

qc_mainpage_path = "quality_check/oswm_qc_main.html"
qc_externalpage_path = "quality_check/oswm_qc_external.html"

# dictionary that holds the occurrences per feature:
occurrence_per_feature = {k: {} for k in geom_type_dict.keys()}

# data_dict for the map view:
map_view_data = {}

js_functions_dq = f"""
    <script src="../oswm_codebase/assets/js_functions/topbar.js"></script>
"""


styles_dq = f"""
    <link rel="stylesheet" href="../oswm_codebase/assets/styles/topnav_styles.css">
    <link rel="stylesheet" href="../oswm_codebase/assets/styles/accordion.css">
"""

# # # subfolders:
dq_rootfolder = os.path.join("quality_check")

qc_categories_index_path = os.path.join(dq_rootfolder, "categories.json")
qc_main_webmap_path = os.path.join(dq_rootfolder, "map.html")

subfoldernames = ["pages", "tables", "maps", "json"]  # TODO: "data"

subfolderpaths = {name: os.path.join(dq_rootfolder, name) for name in subfoldernames}

for name in subfoldernames:
    for data_category in data_categories:
        type_data_category_folderpath = os.path.join(
            subfolderpaths[name], data_category
        )
        create_folder_if_not_exists(type_data_category_folderpath)


# # # functions:
def add_to_map_data(row_tuple, quality_category, category, issue_key=None, issue_val=None, issue_comment=None):
    id = row_tuple.id
    
    def sanitize(v):
        import math
        if isinstance(v, float) and math.isnan(v):
            return "N/A"
        if v is None:
            return ""
        return str(v)

    issue_details = None
    if issue_key is not None or issue_val is not None or issue_comment is not None:
        issue_details = {
            "category": sanitize(quality_category),
            "key": sanitize(issue_key),
            "value": sanitize(issue_val),
            "comment": sanitize(issue_comment)
        }

    if id not in map_view_data:
        rep_point = row_tuple.geometry.representative_point()
        map_view_data[id] = {
            "id": id,
            # Leaflet uses lat, lon instead of lon, lat
            "point": (rep_point.y, rep_point.x),
            # as a set:
            "quality_category": {quality_category},
            "category": {category},
            "feat_type": row_tuple.element,
            "issues": [issue_details] if issue_details else []
        }
    else:
        # Always update both sets so per-category filtering works correctly
        map_view_data[id]["quality_category"].add(quality_category)
        map_view_data[id]["category"].add(category)
        if issue_details:
            if "issues" not in map_view_data[id]:
                map_view_data[id]["issues"] = []
            if issue_details not in map_view_data[id]["issues"]:
                map_view_data[id]["issues"].append(issue_details)


def add_to_occurrences(curr, category, val_list, feature_id, feature_type):
    # "curr" is the current category and "category" is the data layer (sidewalks, kerbs, etc.)
    curr["occurrences"][category][feature_id] = val_list

    curr["occ_count"][category] += 1

    curr["feature_types"][feature_id] = feature_type


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
        theme_params["overlays"] = join_list_for_req(theme_params["overlays"])

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


def osmose_issue_mapurl(params):
    """
    Generate an Osmose issue map URL with the given parameters.

    :param params: Dictionary containing item, zoom, lat, lon, and issue_uuid.
    :return: Generated URL as a string.

    # Example usage:
    params = {
        "item": 2130,
        "zoom": 16,
        "lat": -25.5157399,
        "lon": -49.2146691,
        "issue_uuid": "e6db259e-b438-85f8-8ca9-23129d292329"
    }

    generated_url = osmose_issue_mapurl(params)

    """

    base_url = "https://osmose.openstreetmap.fr/en/map/"

    # Encode the parameters as a fragment (after '#')
    fragment = urlencode(params)

    # Construct and return the full URL
    return f"{base_url}#{fragment}"


def compose_osmose_issues_url(item, class_id, bbox, source="", username=""):
    """
    Generate an Osmose issues URL with the given parameters.

    :param item: The item number (e.g., 9001).
    :param class_id: The class identifier (e.g., 9001001).
    :param bbox: A tuple representing the bounding box (min_lon, min_lat, max_lon, max_lat).
    :param source: (Optional) The source parameter.
    :param username: (Optional) The OSM username.
    :return: Generated URL as a string.
    """
    base_url = "https://osmose.openstreetmap.fr/en/issues/open"
    params = {
        "item": item,
        "source": source,
        "class": class_id,
        "username": username,
        "bbox": bbox,
    }
    query_string = urlencode(params)
    return f"{base_url}?{query_string}"


def gen_content_osmose():
    used_z = 19

    endpoint_req = "http://osmose.openstreetmap.fr/api/0.3/issues"

    details_baseurl = "https://osmose.openstreetmap.fr/en/issue/"

    params = {"bbox": bbox_str}

    themes = {
        "Incomplete Footways": {
            "params": {
                "item": "2080",
                "class": "20805",
                "limit": 200,
            },
            "description": "sidewalk without highway=footway|construction|proposed",
        },
        "Wrongly Tagged Crossings": {
            "params": {"item": "9004", "class": "9004002", "limit": 50},
            "description": "wrong crossing tag on a way",
        },
        "Incomplete Crossings": {
            "params": {
                "item": "9018",
                "class": "9018019",
                "limit": 50,
            },
            "description": "crossing=* must be alongside highway=crossing",
        },
        "Conflict Between Tags": {
            "params": {
                "item": "4030",
                "class": "40303",
                "limit": 50,
            },
            "description": "Conflict between tags: `crossing=informal` must be used without `highway=crossing`",
        },
        "Node Like Way": {
            "params": {
                "item": "4090",
                "class": "1",
                "limit": 10,
            },
            "description": "Way node tagged like way",
        },
        "Bad Tag Value": {
            "params": {
                "item": "3040",
                "class": "3040",
                "limit": 10,
            },
            "description": "Bad tag value",
        },
        "Bad Cycle/footway Combination": {
            "params": {
                "item": "9001",
                "class": "9001001",
                "limit": 10,
            },
            "description": "Combined foot- and cycleway without segregated.",
        },
        "Overly Permissive Access Tag": {
            "params": {
                "item": "3220",
                "class": "32201",
                "limit": 10,
            },
            "description": "Overly permissive access (generally access=yes inconsistent with other tags).",
        },
    }

    themes_content = ""

    categories_content = "<table>"

    # stablish the number of columns in the categories:
    c_n_cols = 4

    for i, theme in enumerate(themes):
        params.update(themes[theme]["params"])
        response = requests.get(endpoint_req, params=params)

        category_url = compose_osmose_issues_url(
            themes[theme]["params"]["item"],
            themes[theme]["params"]["class"],
            bbox_str,
        )

        if i % c_n_cols == 0:
            categories_content += f"""
                <tr>
            """

        categories_content += f"""
            <td><a href="{category_url}">{theme}</a></td>
        """

        if (i + 1) % c_n_cols == 0:
            categories_content += f"""
                </tr>
            """

        if response.status_code == 200:
            issues = response.json().get("issues", [])

            for issue in issues:
                lat = issue["lat"]
                lon = issue["lon"]
                id = issue["id"]
                item = issue["item"]

                osm_url = compose_osm_map_url(lon, lat, used_z)

                osmose_url = osmose_issue_mapurl(
                    {
                        "item": item,
                        "zoom": used_z,
                        "lat": lat,
                        "lon": lon,
                        "issue_uuid": id,
                    }
                )

                details_url = details_baseurl + str(id)

                themes_content += f"""
                    <tr>
                        <td><a href="{osm_url}">{lon},{lat}</a></td>
                        <td><a href="{osmose_url}">Map View</a></td>
                        <td><a href="{details_url}">Details</a></td>
                        <td><a href="{category_url}">{themes[theme]["description"]}</a></td>
                    </tr>
                """

    categories_content += "</table>"

    inner_content = f"""
        <p>
            OSM France offers
            <a href="https://wiki.openstreetmap.org/wiki/Osmose">
                Osmose.
            </a>
            A tool for quality assurance of OSM data. We curated categories meant to be related with Pedestrian data. We recommend that you use the map view. Some Features can be at city's surroundings, the since the requests were made using just the bounding box, without further filtering. In few classes some detecttions may be unrelated to Pedestrian data.
        </p>
        
        <p style="font-size: small">
            They also offer a tool to check all detections related to your user,  <a href="https://osmose.openstreetmap.fr/en/byuser/">check it out</a>!
        </p>
        
        {details_item("Categories (Overview at Osmose) - click to expand", categories_content)}
        
        <table>
            <tr>
                <th>Location (OSM View - Surroundings)</th>
                <th>Osmose Map View</th>
                <th>Osmose Details</th>
                <th>Description (link to category overview at Osmose)</th>
            </tr>

            {themes_content}
            
        </table>
        
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
        f'<a href="../index.html">Go to Node Home</a>',
        f'<a href="oswm_qc_main.html">OSWM DQ Main</a>',
        f'<a href="oswm_qc_external.html">External Providers</a>',
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


def create_marker_cluster_html(
    outpath, centerpoint, z_level, tiles="Cartodb Positron", specific_q_category=None, specific_category=None, title="OSWM Quality Assurance Map", back_url="oswm_qc_main.html", back_text="← Back to QC Homepage", logo_url=None, favicon_url=None
):
    logo_url = logo_url or branding_asset_url("logos.project", "../oswm_codebase")
    favicon_url = favicon_url or branding_asset_url("favicon", "../oswm_codebase")

    # Filter data:
    map_view_data_to_use = map_view_data

    if specific_q_category or specific_category:
        special_map_view_data = {}
        for k, v in map_view_data.items():
            q_match = specific_q_category in v["quality_category"] if specific_q_category else True
            c_match = specific_category in v["category"] if specific_category else True
            if q_match and c_match:
                special_map_view_data[k] = v
        map_view_data_to_use = special_map_view_data

    issues_registry = []
    issue_to_id = {}

    features = []
    for item in map_view_data_to_use.values():
        lat, lon = item["point"][0], item["point"][1]
        
        issues = item.get("issues", [])
        issue_ids = []
        for issue in issues:
            issue_key = (issue["category"], issue["key"], issue["value"], issue["comment"])
            if issue_key not in issue_to_id:
                issue_id = len(issues_registry)
                issue_to_id[issue_key] = issue_id
                issues_registry.append(issue)
            else:
                issue_id = issue_to_id[issue_key]
            issue_ids.append(issue_id)

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "id": item["id"],
                "feat_type": item["feat_type"],
                "quality_categories": ", ".join(sorted(list(item["quality_category"]))),
                "issue_ids": json.dumps(issue_ids, ensure_ascii=False),
                "osm_url": osm_feature_url(item["id"], item["feat_type"]),
                "josm_url": f"http://127.0.0.1:8111/load_object?new_layer=false&objects={item['feat_type'][0]}{item['id']}",
                "id_url": f"https://www.openstreetmap.org/edit?editor=id&{item['feat_type']}={item['id']}#map=20/{lat}/{lon}"
            }
        })

    geojson_dict = {
        "type": "FeatureCollection",
        "features": features
    }

    geojson_json_str = json.dumps(geojson_dict, ensure_ascii=False)

    # Inline the city boundary polygon so no runtime fetch is needed
    try:
        _raw_polygon = read_json(boundaries_geojson_path)
        _boundary_feature = {
            "type": "Feature",
            "geometry": _raw_polygon,
            "properties": {}
        }
        boundary_geojson_str = json.dumps(_boundary_feature, ensure_ascii=False)
    except Exception:
        boundary_geojson_str = '{"type":"Feature","geometry":null,"properties":{}}'

    center_lon = centerpoint[1]
    center_lat = centerpoint[0]
    issues_registry_json = json.dumps(issues_registry, ensure_ascii=False)

    geojson_outpath = outpath.replace(".html", ".geojson")
    registry_outpath = outpath.replace(".html", "_registry.json")
    
    with open(geojson_outpath, "w", encoding="utf-8") as f:
        f.write(geojson_json_str)
        
    with open(registry_outpath, "w", encoding="utf-8") as f:
        f.write(issues_registry_json)
        
    geojson_filename = os.path.basename(geojson_outpath)
    registry_filename = os.path.basename(registry_outpath)

    available_q_categories = set()
    for item in map_view_data_to_use.values():
        available_q_categories.update(item["quality_category"])
    
    checkboxes_html = ""
    for cat in sorted(list(available_q_categories)):
        checkboxes_html += f'''
            <label style="display: block; margin-bottom: 5px; font-size: 0.85rem; cursor: pointer;">
                <input type="checkbox" class="cat-filter-checkbox" value="{cat}" checked onchange="applyFilters()"> {cat}
            </label>
        '''
        
    filter_panel_html = ""
    if checkboxes_html:
        filter_panel_html = f'''
        <div id="category-filter-panel" style="position: absolute; top: calc(var(--topbar-height) + 10px); left: 10px; z-index: 9998; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(255,255,255,0.1); padding: 10px 15px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); max-height: calc(100vh - var(--topbar-height) - 40px); overflow-y: auto; color: #f8fafc;">
            <div style="display: flex; justify-content: space-between; align-items: center; cursor: pointer;" onclick="const content = document.getElementById('filter-content'); content.style.display = content.style.display === 'none' ? 'block' : 'none'; const icon = document.getElementById('filter-icon'); icon.textContent = content.style.display === 'none' ? '▼' : '▲';">
                <h4 style="margin: 0; font-size: 0.95rem; font-weight: 500; color: #00f2fe;">Filter Categories</h4>
                <span id="filter-icon" style="font-size: 0.8em; margin-left: 15px; color: #94a3b8;">▼</span>
            </div>
            <div id="filter-content" style="display: none; margin-top: 10px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 10px;">
                {checkboxes_html}
            </div>
        </div>
        '''

    html_content = f"""<!--
  Generated automatically by oswm_codebase/data_quality/dq_funcs.py
  Do not edit this file directly.
-->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="icon" type="image/x-icon" href="{favicon_url}">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet">
    <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
    <style>
        :root {{
            --topbar-height: 57px;
        }}
        body {{
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100vh;
            overflow: hidden;
            background-color: #0f172a;
            font-family: 'Outfit', sans-serif;
        }}
        #map {{
            position: absolute;
            top: var(--topbar-height);
            bottom: 0;
            width: 100%;
        }}
        .maplibregl-ctrl-top-right {{
            top: 10px;
        }}
        .custom-dq-popup {{
            z-index: 1000 !important;
        }}
        .custom-dq-popup .maplibregl-popup-content {{
            background: #ffffff;
            border-radius: 8px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
            padding: 12px 16px;
        }}
    </style>
</head>
<body>
    <div style="position: absolute; top: 0; left: 0; width: 100%; z-index: 9999; background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding: 10px 20px; display: flex; align-items: center; justify-content: space-between; font-family: 'Outfit', sans-serif; box-sizing: border-box; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
        <div style="flex: 1;">
            <a href="{back_url}" style="display: inline-block; background: rgba(255,255,255,0.05); border: 1px solid rgba(0,242,254,0.3); color: #00f2fe; padding: 6px 12px; border-radius: 6px; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: background 0.2s;">{back_text}</a>
        </div>
        <h3 style="margin: 0; color: #f8fafc; font-size: 1.25rem; font-weight: 600; letter-spacing: 0.5px; flex: 1; text-align: center; text-shadow: 0 2px 4px rgba(0,0,0,0.3);"><img src="{logo_url}" alt="OSWM Logo" style="height: 1.5em; vertical-align: middle; margin-right: 15px;">{title}</h3>
        <div style="flex: 1;"></div>
    </div>

    {filter_panel_html}

    <div id="map"></div>

    <script>
        let issuesRegistry = [];
        let geojsonData = null;
        
        fetch('{registry_filename}').then(r => r.json()).then(data => {{
            issuesRegistry = data;
        }}).catch(e => console.error("Could not load registry:", e));

        fetch('{geojson_filename}').then(r => r.json()).then(data => {{
            geojsonData = data;
        }}).catch(e => console.error("Could not load geojson:", e));

        function applyFilters() {{
            if (!geojsonData || !map.getSource('dq-markers')) return;
            const checkedCategories = Array.from(document.querySelectorAll('.cat-filter-checkbox:checked')).map(cb => cb.value);
            
            const filteredFeatures = geojsonData.features.filter(f => {{
                const cats = f.properties.quality_categories.split(', ');
                return cats.some(c => checkedCategories.includes(c));
            }});
            
            map.getSource('dq-markers').setData({{
                type: "FeatureCollection",
                features: filteredFeatures
            }});
        }}

        const map = new maplibregl.Map({{
            container: 'map',
            style: {{
                version: 8,
                sources: {{
                    'carto-positron': {{
                        type: 'raster',
                        tiles: ['https://basemaps.cartocdn.com/rastertiles/light_all/{{z}}/{{x}}/{{y}}.png'],
                        tileSize: 256,
                        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                    }}
                }},
                layers: [{{
                    id: 'carto-tiles',
                    type: 'raster',
                    source: 'carto-positron',
                    minzoom: 0,
                    maxzoom: 20
                }}]
            }},
            center: [{center_lon}, {center_lat}],
            zoom: {z_level}
        }});

        map.addControl(new maplibregl.NavigationControl(), 'top-right');
        map.addControl(new maplibregl.ScaleControl({{ unit: 'metric' }}), 'bottom-right');

        map.on('load', () => {{
            // City boundary outline
            map.addSource('city-boundary', {{
                type: 'geojson',
                data: {boundary_geojson_str}
            }});
            map.addLayer({{
                id: 'city-boundary-line',
                type: 'line',
                source: 'city-boundary',
                paint: {{
                    'line-color': '#9ca3af',
                    'line-width': 1.5,
                    'line-opacity': 0.8
                }}
            }});

            map.addSource('dq-markers', {{
                type: 'geojson',
                data: '{geojson_filename}',
                cluster: true,
                clusterMaxZoom: 14,
                clusterRadius: 50,
                generateId: true
            }});

            map.addLayer({{
                id: 'clusters',
                type: 'circle',
                source: 'dq-markers',
                filter: ['has', 'point_count'],
                paint: {{
                    'circle-color': [
                        'step',
                        ['get', 'point_count'],
                        'rgba(254, 240, 217, 0.9)', 10,
                        'rgba(253, 204, 138, 0.9)', 50,
                        'rgba(252, 141, 89, 0.9)', 100,
                        'rgba(215, 48, 31, 0.9)'
                    ],
                    'circle-radius': [
                        'step',
                        ['get', 'point_count'],
                        18, 10,
                        22, 50,
                        26, 100,
                        32
                    ],
                    'circle-stroke-width': ['case', ['boolean', ['feature-state', 'hover'], false], 4, 2],
                    'circle-stroke-color': ['case', ['boolean', ['feature-state', 'hover'], false], '#ffffff', 'rgba(255,255,255,0.6)']
                }}
            }});

            // Cluster count overlay — HTML divs positioned over each cluster circle.
            // Avoids needing a glyph/font server which can block the map from loading.
            const clusterLabels = new Map();
            const mapCanvas = map.getCanvasContainer();

            function formatCount(n) {{
                if (n >= 1000) return (Math.round(n / 100) / 10) + 'k';
                return String(n);
            }}

            function updateClusterLabels() {{
                const features = map.queryRenderedFeatures({{ layers: ['clusters'] }});
                const seen = new Set();

                features.forEach(f => {{
                    const id = f.properties.cluster_id;
                    const count = f.properties.point_count;
                    const pos = map.project(f.geometry.coordinates);
                    seen.add(id);

                    if (!clusterLabels.has(id)) {{
                        const el = document.createElement('div');
                        el.style.position = 'absolute';
                        el.style.pointerEvents = 'none';
                        el.style.fontFamily = 'Outfit, sans-serif';
                        el.style.fontWeight = '700';
                        el.style.fontSize = '12px';
                        el.style.color = '#1e293b';
                        el.style.transform = 'translate(-50%, -50%)';
                        el.style.whiteSpace = 'nowrap';
                        el.style.zIndex = '10';
                        mapCanvas.appendChild(el);
                        clusterLabels.set(id, el);
                    }}

                    const el = clusterLabels.get(id);
                    el.textContent = formatCount(count);
                    el.style.left = pos.x + 'px';
                    el.style.top = pos.y + 'px';
                    el.style.display = 'block';
                }});

                clusterLabels.forEach((el, id) => {{
                    if (!seen.has(id)) el.style.display = 'none';
                }});
            }}

            map.on('render', updateClusterLabels);

            map.addLayer({{
                id: 'unclustered-point',
                type: 'circle',
                source: 'dq-markers',
                filter: ['!', ['has', 'point_count']],
                paint: {{
                    'circle-color': ['case', ['boolean', ['feature-state', 'hover'], false], '#475569', '#1e293b'],
                    'circle-radius': 7,
                    'circle-stroke-width': ['case', ['boolean', ['feature-state', 'hover'], false], 3, 1.5],
                    'circle-stroke-color': ['case', ['boolean', ['feature-state', 'hover'], false], '#94a3b8', '#64748b']
                }}
            }});

            map.on('click', 'clusters', (e) => {{
                const features = map.queryRenderedFeatures(e.point, {{ layers: ['clusters'] }});
                map.easeTo({{
                    center: features[0].geometry.coordinates,
                    zoom: map.getZoom() + 1,
                    duration: 300
                }});
            }});

            map.on('click', 'unclustered-point', (e) => {{
                const coordinates = e.features[0].geometry.coordinates.slice();
                const props = e.features[0].properties;

                let issues_html = "";
                if (props.issue_ids) {{
                    let idsList;
                    try {{
                        idsList = typeof props.issue_ids === 'string' ? JSON.parse(props.issue_ids) : props.issue_ids;
                    }} catch (err) {{
                        idsList = [];
                    }}
                    idsList.forEach(issueId => {{
                        const issue = issuesRegistry[issueId];
                        if (issue) {{
                            issues_html += `<div style='margin-bottom: 8px; font-size: 13px;'><strong style='color: #4facfe;'>${{issue.category}}</strong><br/><b>Key:</b> ${{issue.key}} | <b>Value:</b> ${{issue.value}}<br/><b>Comment:</b> ${{issue.comment}}</div>`;
                        }}
                    }});
                }}

                const popupHtml = `
                    <div style="font-family: 'Outfit', sans-serif; min-width: 220px; max-width: 320px; max-height: 350px; display: flex; flex-direction: column;">
                        <h4 style="margin: 0 0 5px 0; color: #0088aa; font-size: 15px; border-bottom: 1px solid #eee; padding-bottom: 5px; flex-shrink: 0;">Feature: ${{props.feat_type}} ${{props.id}}</h4>
                        <div style="overflow-y: auto; flex-grow: 1; margin: 10px 0; padding-right: 5px;">
                            ${{issues_html ? issues_html : `<p style="margin: 0 0 12px 0; font-size: 13px; color: #444; line-height: 1.4;"><b>Categories:</b><br>${{props.quality_categories}}</p>`}}
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px; flex-shrink: 0; padding-top: 5px; border-top: 1px solid #eee;">
                            <a href="${{props.osm_url}}" target="_blank" style="background: #4facfe; color: white; padding: 6px 10px; border-radius: 6px; text-decoration: none; font-size: 12px; font-weight: bold; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">↗ Open in OSM</a>
                            <a href="${{props.josm_url}}" target="_blank" style="background: #10b981; color: white; padding: 6px 10px; border-radius: 6px; text-decoration: none; font-size: 12px; font-weight: bold; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">⚙ Open in JOSM</a>
                            <a href="${{props.id_url}}" target="_blank" style="background: #8b5cf6; color: white; padding: 6px 10px; border-radius: 6px; text-decoration: none; font-size: 12px; font-weight: bold; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">✎ Open in iD Editor</a>
                        </div>
                    </div>
                `;

                while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {{
                    coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360;
                }}

                new maplibregl.Popup({{ className: 'custom-dq-popup' }})
                    .setLngLat(coordinates)
                    .setHTML(popupHtml)
                    .addTo(map);
            }});

            // Hover state tracking — clusters
            let hoveredClusterId = null;
            map.on('mousemove', 'clusters', (e) => {{
                const newId = e.features[0].id;
                if (newId !== hoveredClusterId) {{
                    if (hoveredClusterId !== null)
                        map.setFeatureState({{ source: 'dq-markers', id: hoveredClusterId }}, {{ hover: false }});
                    hoveredClusterId = newId;
                    map.setFeatureState({{ source: 'dq-markers', id: hoveredClusterId }}, {{ hover: true }});
                }}
                map.getCanvas().style.cursor = 'pointer';
            }});
            map.on('mouseleave', 'clusters', () => {{
                if (hoveredClusterId !== null)
                    map.setFeatureState({{ source: 'dq-markers', id: hoveredClusterId }}, {{ hover: false }});
                hoveredClusterId = null;
                map.getCanvas().style.cursor = '';
            }});

            // Hover state tracking — individual points
            let hoveredPointId = null;
            map.on('mousemove', 'unclustered-point', (e) => {{
                const newId = e.features[0].id;
                if (newId !== hoveredPointId) {{
                    if (hoveredPointId !== null)
                        map.setFeatureState({{ source: 'dq-markers', id: hoveredPointId }}, {{ hover: false }});
                    hoveredPointId = newId;
                    map.setFeatureState({{ source: 'dq-markers', id: hoveredPointId }}, {{ hover: true }});
                }}
                map.getCanvas().style.cursor = 'pointer';
            }});
            map.on('mouseleave', 'unclustered-point', () => {{
                if (hoveredPointId !== null)
                    map.setFeatureState({{ source: 'dq-markers', id: hoveredPointId }}, {{ hover: false }});
                hoveredPointId = null;
                map.getCanvas().style.cursor = '';
            }});
        }});
    </script>
</body>
</html>
"""

    ensure_parent_folder(outpath)
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html_content)


def gen_quality_report_page_and_files(
    outpath,
    tabledata,
    feat_types,
    category,
    quality_category,
    text,
    occ_type,
    csvpath,
    invert_geom=False,
    iso_19157=None,
):

    # pagename_base = f"{quality_category}_{category}"

    files_url_part = f"""
        <div style="display: flex; gap: 15px; margin-top: 20px; margin-bottom: 20px;">
            <a href="../../tables/{category}/{quality_category}.csv" style="display: inline-block; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(0, 242, 254, 0.3); color: #00f2fe; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-size: 0.95rem; font-weight: 500; transition: all 0.2s; backdrop-filter: blur(8px);">↓ Download Raw .CSV</a>
            <a href="../../json/{category}/{quality_category}.json" style="display: inline-block; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(0, 242, 254, 0.3); color: #00f2fe; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-size: 0.95rem; font-weight: 500; transition: all 0.2s; backdrop-filter: blur(8px);">&#123;&#125; Access Raw .JSON</a>
            <a href="../../maps/{category}/{quality_category}.html" style="display: inline-block; background: rgba(30, 41, 59, 0.7); border: 1px solid #10b981; color: #10b981; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-size: 0.95rem; font-weight: 500; transition: all 0.2s; backdrop-filter: blur(8px);">🗺 Open Map View</a>
        </div>
    """

    tablepart = f"""<tr>
    <th>OSM ID (link)</th>
    <th>Open in iD editor</th>
    <th>Key</th>
    <th>Value</th>
    <th>Commentary</th>
    </tr>"""

    valid_featcount = 0

    # inverting feature type, if needed:
    if invert_geom:
        feat_types = {k: osm_feat_type_inverter(v) for k, v in feat_types.items()}

    op_nodes, op_ways, op_rels = [], [], []

    # the main iteration
    os.makedirs(os.path.dirname(csvpath), exist_ok=True)
    with open(csvpath, "w+", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=",", quotechar='"')
        writer.writerow(["osm_id", "feat_type", "key", "value", "commentary"])

        for line in tabledata:
            try:
                line_as_str = ""
                if line:
                    if len(line) > 2:
                        if not pd.isna(line[2]):

                            feat_type = feat_types[line[0]]
                            
                            if feat_type == "node":
                                op_nodes.append(str(line[0]))
                            elif feat_type == "way":
                                op_ways.append(str(line[0]))
                            elif feat_type == "relation":
                                op_rels.append(str(line[0]))
                            
                            point = [0, 0]
                            if line[0] in map_view_data:
                                point = map_view_data[line[0]]["point"]
                            
                            id_editor_link = f"https://www.openstreetmap.org/edit?editor=id&{feat_type}={line[0]}#map=20/{point[0]}/{point[1]}"
                            id_btn = f'<a href="{id_editor_link}" target="_blank" style="color: #8b5cf6; text-decoration: underline; font-weight: 500;">✎ {line[0]}</a>'

                            writer.writerow(
                                # I know it's kinda ugly:
                                [line[0], feat_type, line[1], line[2], line[3]]
                            )

                            formatted_id_link = return_weblink_V2(line[0], feat_type)

                            line_as_str += "<tr>"
                            line_as_str += f"<td>{str(formatted_id_link)}</td>"
                            line_as_str += f"<td>{id_btn}</td>"
                            line_as_str += f"<td>{str(line[1])}</td>"
                            line_as_str += f"<td>{str(line[2])}</td>"
                            line_as_str += f"<td>{str(line[3])}</td>"
                            line_as_str += "</tr>\n"

                            tablepart += line_as_str

                            valid_featcount += 1
            except Exception as e:
                if line:
                    print(f"skipped {{line}} : {{e}}")

    # read just to export as a json:
    csv_as_df = pd.read_csv(csvpath)
    json_outpath = os.path.join(
        subfolderpaths["json"], category, f"{quality_category}.json"
    )
    csv_as_df.to_json(json_outpath, orient="records")
    
    overpass_query = "(\n"
    if op_nodes:
        overpass_query += f"  node({','.join(op_nodes)});\n"
    if op_ways:
        overpass_query += f"  way({','.join(op_ways)});\n"
    if op_rels:
        overpass_query += f"  relation({','.join(op_rels)});\n"
    overpass_query += ");\nout meta;"

    overpass_html = f"""
    <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(0, 242, 254, 0.3); border-radius: 12px; padding: 1rem; margin-bottom: 1.5rem;">
        <h4 style="margin-top: 0; color: #00f2fe; font-size: 1.1rem; display: flex; justify-content: space-between; align-items: center;">Overpass Query <button onclick="navigator.clipboard.writeText(document.getElementById('op-query-text').value); this.innerText='Copied!'; setTimeout(()=>this.innerText='Copy', 2000);" style="background: rgba(0, 242, 254, 0.2); border: 1px solid #00f2fe; color: #00f2fe; border-radius: 4px; padding: 4px 10px; cursor: pointer; font-size: 0.8rem; font-weight: 500; transition: background 0.2s;">Copy</button></h4>
        <textarea id="op-query-text" readonly style="width: 100%; height: 80px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; color: #cbd5e1; font-family: 'Fira Code', monospace; font-size: 0.85rem; padding: 10px; resize: none; overflow-y: auto;">{overpass_query}</textarea>
    </div>
    """

    # Build ISO 19157 badge HTML for the subpage info card
    iso_badge_subpage = ""
    if iso_19157:
        _iso_colors = {
            "Thematic Accuracy": ("#a78bfa", "rgba(167, 139, 250, 0.15)", "rgba(167, 139, 250, 0.3)"),
            "Logical Consistency": ("#00f2fe", "rgba(0, 242, 254, 0.15)", "rgba(0, 242, 254, 0.3)"),
        }
        _iso_c, _iso_bg, _iso_br = _iso_colors.get(iso_19157["element"], ("#94a3b8", "rgba(148, 163, 184, 0.15)", "rgba(148, 163, 184, 0.3)"))
        iso_badge_subpage = (
            f'<p style="margin: 0; font-size: 1rem; color: #f8fafc;"><b>ISO 19157:2013:</b> '
            f'<span style="display:inline-block; background:{_iso_bg}; border:1px solid {_iso_br}; color:{_iso_c}; padding:3px 10px; border-radius:6px; font-size:0.85rem; font-weight:500;">'
            f'{iso_19157["element"]} \u2192 {iso_19157["sub_element"]}</span> '
            f'<span style="color:#64748b; font-size:0.8rem; font-style:italic; margin-left:8px;">({iso_19157["iso_reference"]})</span></p>'
        )

    with open(outpath, "w+", encoding="utf-8") as writer:

        page = f"""<!--
  Generated automatically by oswm_codebase/data_quality/dq_funcs.py
  Do not edit this file directly.
-->
        <!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        {get_font_style(3)}
        {get_tables_styles(3)}

        <title>OSWM DQT {category[0]} {quality_category}</title>
        <link rel="icon" type="image/x-icon" href="{branding_asset_url('favicon', '../../../oswm_codebase')}">

        </head>
        <body>
        
        <main class="dq-container">
            <div style="text-align: left; margin-bottom: 1rem;">
                <a href="../../oswm_qc_main.html" style="display: inline-block; background: rgba(255,255,255,0.05); border: 1px solid rgba(0,242,254,0.3); color: #00f2fe; padding: 6px 12px; border-radius: 6px; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: background 0.2s;">← Back to DQ Main</a>
            </div>
            
            <h1 style="color: #f8fafc; font-size: 2rem; margin-bottom: 0.5rem;"><img src="{branding_asset_url('logos.project', '../../../oswm_codebase')}" alt="OSWM Logo" style="height: 1.5em; vertical-align: middle; margin-right: 15px;"><a href="../../../index.html" style="color: #00f2fe; text-decoration: none;">OSWM</a> Data Quality Tool</h1>
            <h2 style="color: #94a3b8; font-size: 1.2rem; font-weight: 400; margin-top: 0; margin-bottom: 2rem;">{category} / <span style="color: #f8fafc; font-weight: 600;">{quality_category}</span></h2>
            
            {files_url_part}
            {overpass_html}

            <table style="margin-bottom: 2rem;">
            {tablepart}
            </table>

            <div style="background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <p style="margin: 0 0 10px 0; font-size: 1rem; color: #f8fafc;"><b>About:</b> <span style="color: #cbd5e1;">{text}</span></p>
                <p style="margin: 0 0 10px 0; font-size: 1rem; color: #f8fafc;"><b>Type:</b> <span style="color: #cbd5e1;">{occ_type}</span></p>
                {iso_badge_subpage}
            </div>
        </main>

        </body>
        </html>   

        """

        writer.write(page)

    return valid_featcount
