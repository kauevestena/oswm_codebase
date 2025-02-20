import sys
from urllib.parse import urlencode

sys.path.append("oswm_codebase")

from functions import *
import csv

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
    create_folder_if_not_exists(subfolderpaths[name])


# # # functions:
def add_to_map_data(row_tuple, quality_category):
    if not row_tuple.id in map_view_data:
        rep_point = row_tuple.geometry.representative_point()
        id = row_tuple.id

        if not id in map_view_data:
            map_view_data[id] = {
                "id": row_tuple.id,
                # Leaflet uses lat, lon instead of lon, lat
                "point": (rep_point.y, rep_point.x),
                # as a set:
                "quality_category": {quality_category},
                "feat_type": row_tuple.element,
            }
        else:
            map_view_data[id]["quality_category"].add(quality_category)


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


def create_marker_cluster_html(
    outpath, centerpoint, z_level, tiles="Cartodb Positron", specific_q_category=None
):
    import folium

    from folium.plugins import MarkerCluster

    m = folium.Map(location=centerpoint, zoom_start=z_level, tiles=tiles)

    # "map_view_data" is the source of the data:
    map_view_data_to_use = map_view_data

    if specific_q_category:
        special_map_view_data = {
            k: v
            for k, v in map_view_data.items()
            if specific_q_category in v["quality_category"]
        }.copy()

        map_view_data_to_use = special_map_view_data

    locations = [item["point"] for item in map_view_data_to_use.values()]

    icon_create_function = """\
    function(cluster) {
        return L.divIcon({
        html: '<b>' + cluster.getChildCount() + '</b>',
        className: 'marker-cluster marker-cluster-large',
        iconSize: new L.Point(20, 20)
        });
    }"""

    popup_mold = 'categories: {} <br> </a href="{}">Access on OSM ({})</a>'

    popups = [
        popup_mold.format(
            item["quality_category"],
            osm_feature_url(item["id"], item["feat_type"]),
            item["id"],
        )
        for item in map_view_data_to_use.values()
    ]

    if map_view_data_to_use:

        marker_cluster = MarkerCluster(
            locations=locations,
            popups=popups,
            name="OSWM DQ Markers (clustered)",
            icon_create_function=icon_create_function,
        )

        marker_cluster.add_to(m)

    m.save(outpath)


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
):

    pagename_base = f"{quality_category}_{category}"

    files_url_part = f"""<h2>  
        
            <a href="{node_homepage_url}quality_check/tables/{pagename_base}.csv"> You can also download the raw .csv table </a>
            <a href="{node_homepage_url}quality_check/json/{pagename_base}.json"> You can also access the raw .json </a>

        </h2>"""

    tablepart = f"""<tr>
    <th><b>OSM ID (link)</b></th>
    <th><b>key</b></th>
    <th><b>value</b></th>
    <th><b>commentary</b></th>
    </tr>"""

    valid_featcount = 0

    # inverting feature type, if needed:
    if invert_geom:
        feat_types = {k: osm_feat_type_inverter(v) for k, v in feat_types.items()}

    # the main iteration
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

                            writer.writerow(
                                # I know it's kinda ugly:
                                [line[0], feat_type, line[1], line[2], line[3]]
                            )

                            line[0] = return_weblink_V2(line[0], feat_type)

                            line_as_str += "<tr>"

                            for element in line:
                                line_as_str += f"<td>{str(element)}</td>"

                            line_as_str += "</tr>\n"

                            tablepart += line_as_str

                            valid_featcount += 1
            except:
                if line:
                    print("skipped", line)

    # read just to export as a json:
    csv_as_df = pd.read_csv(csvpath)
    json_outpath = os.path.join(subfolderpaths["json"], f"{pagename_base}.json")
    csv_as_df.to_json(json_outpath, orient="records")

    # the webmap, generate only once per quality category
    if category == "sidewalks":
        webmap_outpath = os.path.join(
            subfolderpaths["maps"], f"{quality_category}.html"
        )
        create_marker_cluster_html(
            webmap_outpath,
            reversed_centerpoint,
            dq_maps_z_default,
            specific_q_category=quality_category,
        )

    with open(outpath, "w+", encoding="utf-8") as writer:

        page = f"""

        <!DOCTYPE html>
        <html lang="en">
        <head>

        {get_font_style(2)}

        <title>OSWM DQT {category[0]} {quality_category}</title>

        {get_tables_styles(2)}

        </head>
        <body>
        
        <h1><a href="{node_homepage_url}">OSWM</a> Data Quality Tool: {category} {quality_category}</h1>

        <h2>About: {text}</h2>
        <h2>Type: {occ_type}</h2>
        {files_url_part}




        <table>

        {tablepart}

        </table>

        


        </table>



        </body>
        </html>   

        """

        writer.write(page)

    return valid_featcount
