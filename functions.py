import csv, os, re
import bs4
from time import sleep, time
import pandas as pd
from datetime import datetime
import json, requests
from xml.etree import ElementTree
import geopandas as gpd
from constants import *
from shapely import box

"""

    READ/ DUMP STUFF

"""


def read_json(inputpath):
    with open(inputpath) as reader:
        data = reader.read()

    return json.loads(data)


def dump_json(inputdict, outputpath, indent=4):
    with open(outputpath, "w+", encoding="utf8") as json_handle:
        json.dump(inputdict, json_handle, indent=indent, ensure_ascii=False)


def file_as_string(inputpath: str):
    if os.path.exists(inputpath):
        with open(inputpath, encoding="utf8") as reader:
            return reader.read()
    else:
        raise (FileNotFoundError)


def str_to_file(inputstr: str, outputpath: str, check_path=False):
    if check_path:
        if not os.path.exists(outputpath):
            raise (FileNotFoundError)

    with open(outputpath, "w+", encoding="utf8") as writer:
        writer.write(inputstr)
        sleep(0.1)


class fileAsStrHandler:

    def __init__(self, inputpath: str):
        self.path = inputpath
        self.content = file_as_string(self.path)

    def simple_replace(self, original_part, new_part=""):
        """default is empty for just remove the selected content"""
        self.content = self.content.replace(original_part, new_part)

    def rewrite(self):
        str_to_file(self.content, self.path)

    def write_to_another_path(self, outputpath):
        str_to_file(self.content, outputpath)


"""

    TIME STUFF

"""


def formatted_datetime_now():
    now = datetime.now()
    return now.strftime("%d/%m/%Y %H:%M:%S")


def record_datetime(key, json_path="data/last_updated.json"):

    datadict = read_json(json_path)

    datadict[key] = formatted_datetime_now()

    dump_json(datadict, json_path)

    sleep(0.1)


def record_to_json(key, obj, json_path):

    datadict = read_json(json_path)

    datadict[key] = obj

    dump_json(datadict, json_path)


"""

    HTML STUFF

"""

FONT_STYLE = f"""

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@500&display=swap" rel="stylesheet"> 


<style>

    {file_as_string('oswm_codebase/assets/styles/font_styles.css')}

</style>

"""

TABLES_STYLE = f"""

<style>
    {file_as_string('oswm_codebase/assets/styles/table_styles.css')}
</style>

"""


def gen_updating_infotable_page(
    outpath="data/data_updating.html", json_path="data/last_updated.json"
):

    tablepart = ""

    records_dict = read_json(json_path)

    for key in records_dict:
        tablepart += f"""
        <tr><th><b>{key}</b></th><th>{records_dict[key]}</th></tr>
        """

    page_as_txt = f"""
    <!DOCTYPE html>
<html lang="en">
<head>

{FONT_STYLE}

<title>OSWM Updating Info</title>

{TABLES_STYLE}

</head>
<body>

<h1><a href="https://kauevestena.github.io/opensidewalkmap_beta">OSWM</a> Updating Info</h1>

<p> About: OSWM is currently hosted at GitHub Pages, which means that it relies on commits to stay updated!!<br>
if the data is too outdated you may <a href="https://github.com/kauevestena/opensidewalkmap_beta/issues">post an issue</a> or contact me!!</p>

<table>

{tablepart}

</table>


<h1>Download Data:</h1>

<table>

<tr>
  <th>Sidewalks</th>
  <th><a href="{node_homepage_url}data/sidewalks_raw{data_format}">Raw</a></th>
  <th><a href="{node_homepage_url}data/sidewalks{data_format}">Filtered</a></th>
  <th><a href="{node_homepage_url}data/sidewalks_versioning.json">Versioning</a></th>
</tr>

<tr>
  <th>Crossings</th>
  <th><a href="{node_homepage_url}data/crossings_raw{data_format}">Raw</a></th>
  <th><a href="{node_homepage_url}data/crossings{data_format}">Filtered</a></th>
  <th><a href="{node_homepage_url}data/crossings_versioning.json">Versioning</a></th>
</tr>

<tr>
  <th>Kerbs</th>
  <th><a href="{node_homepage_url}data/kerbs_raw{data_format}">Raw</a></th>
  <th><a href="{node_homepage_url}data/kerbs{data_format}">Filtered</a></th>
  <th><a href="{node_homepage_url}data/kerbs_versioning.json">Versioning</a></th>
</tr>



</table>



</body>
</html>    
    """

    # with open(outpath,'w+') as writer:
    #     writer.write(page_as_txt)

    str_to_file(page_as_txt, outpath)


def gen_quality_report_page_and_files(
    outpath,
    tabledata,
    feat_type,
    category,
    quality_category,
    text,
    occ_type,
    csvpath,
    count_page=False,
):

    pagename_base = f"{quality_category}_{category}"

    csv_url = f"""<h2>  
        
            <a href="{node_homepage_url}quality_check/tables/{pagename_base}.csv"> You can also download the raw .csv table </a>

        </h2>"""

    tablepart = f"""<tr>
    <th><b>OSM ID (link)</b></th>
    <th><b>key</b></th>
    <th><b>value</b></th>
    <th><b>commentary</b></th>
    </tr>"""

    if count_page:
        tablepart = f"""<tr>
                    <th><b>OSM ID (link)</b></th>
                    <th><b>count</b></th>"""

        csv_url = ""

    valid_featcount = 0

    with open(csvpath, "w+") as file:
        writer = csv.writer(file, delimiter=",", quotechar='"')
        writer.writerow(["osm_id", "key", "value", "commentary"])

        for line in tabledata:
            try:
                line_as_str = ""
                if line:
                    if len(line) > 2:
                        if not pd.isna(line[2]):

                            writer.writerow(line)

                            line[0] = return_weblink_V2(str(line[0]), feat_type)

                            line_as_str += "<tr>"

                            for element in line:
                                line_as_str += f"<td>{str(element)}</td>"

                            line_as_str += "</tr>\n"

                            tablepart += line_as_str

                            valid_featcount += 1
            except:
                if line:
                    print("skipped", line)

    with open(outpath, "w+") as writer:

        page = f"""

        <!DOCTYPE html>
        <html lang="en">
        <head>

        {FONT_STYLE}

        <title>OSWM DQT {category[0]} {quality_category}</title>

        {TABLES_STYLE}

        </head>
        <body>
        
        <h1><a href="{node_homepage_url}">OSWM</a> Data Quality Tool: {category} {quality_category}</h1>

        <h2>About: {text}</h2>
        <h2>Type: {occ_type}</h2>
        {csv_url}




        <table>

        {tablepart}

        </table>

        


        </table>



        </body>
        </html>   

        """

        writer.write(page)

    return valid_featcount


def find_map_ref(input_htmlpath):
    with open(input_htmlpath) as inf:
        txt = inf.read()
        soup = bs4.BeautifulSoup(txt, features="html5lib")

    refs = soup.find_all(attrs={"class": "folium-map"})

    for found_ref in refs:
        return found_ref["id"]


def find_html_name(
    input_htmlpath, specific_ref, tag_ref="img", specific_tag="src", identifier="id"
):

    with open(input_htmlpath) as inf:
        txt = inf.read()
        soup = bs4.BeautifulSoup(txt, features="html5lib")

    refs = soup.find_all(tag_ref)

    for found_ref in refs:
        # if specific_tag in found_ref:

        if found_ref[specific_tag] == specific_ref:
            return found_ref[identifier]


def style_changer(
    in_out_htmlpath,
    element_key,
    key="style",
    original="bottom",
    new="top",
    append_t=None,
):
    with open(in_out_htmlpath) as inf:
        txt = inf.read()
        soup = bs4.BeautifulSoup(txt, features="html5lib")

    style_refs = soup.find_all(key)

    for style_ref in style_refs:
        as_txt = str(style_ref)
        if element_key in as_txt:

            if new:
                new_text = as_txt.replace(original, new)
            else:
                new_text = as_txt

            if append_t:
                new_text += append_t

            break

    with open(in_out_htmlpath, "w+", encoding="utf-8") as writer:
        writer.write(str(soup).replace(as_txt, new_text))

    sleep(0.2)


def add_to_page_after_first_tag(
    html_filepath, element_string, tag_or_txt="<head>", count=1
):
    """
    Quick and dirty way to insert some stuff directly on the webpage

    Originally intended only for <head>

    beware of tags that repeat! the "count" argument is very important!
    """

    with open(html_filepath) as reader:
        pag_txt = reader.read()

    replace_text = f"{tag_or_txt} \n{element_string}\n"

    with open(html_filepath, "w+") as writer:
        writer.write(pag_txt.replace(tag_or_txt, replace_text, count))

    sleep(0.1)


def replace_at_html(html_filepath, original_text, new_text, count=1):
    """
    Quick and dirty way to replace some stuff directly on the webpage

    Originally intended only for <head>

    beware of tags that repeat! the "count" argument is very important!
    """

    if os.path.exists(html_filepath):
        with open(html_filepath) as reader:
            pag_txt = reader.read()

        with open(html_filepath, "w+") as writer:
            writer.write(pag_txt.replace(original_text, new_text, count))
    else:
        raise ("Error: file not found!!")

    sleep(0.1)


# def file_to_str(filepath):
#     if os.path.exists(filepath):
#         with open(filepath) as reader:
#             pag_txt = reader.read()

#         return pag_txt


def find_between_strings(
    string,
    start,
    end,
    return_unique=True,
    exclusions: list = None,
    include_linebreaks=False,
):
    pattern = f"{start}(.*){end}"
    # print(pattern)
    if include_linebreaks:
        matches = re.findall(pattern, string, re.DOTALL)
    else:
        matches = re.findall(pattern, string)

    if return_unique:
        matches = list(set(matches))

    if exclusions:
        matches = [match for match in matches if match not in exclusions]

    return matches


# (geo)Pandas stuff:
def get_score_df(
    inputdict,
    category="sidewalks",
    osm_key="surface",
    input_field="score_default",
    output_field_base="score",
):

    output_field_name = f"{category}_{osm_key}_{output_field_base}"
    dict = {osm_key: [], output_field_name: []}

    for val_key in inputdict[category][osm_key]:
        dict[osm_key].append(val_key)
        dict[output_field_name].append(
            inputdict[category][osm_key][val_key][input_field]
        )

    return pd.DataFrame(dict), output_field_name


def get_attr_dict(inputdict, category="sidewalks", osm_tag="surface", attr="color"):
    color_dict = {}
    for tag_value in inputdict[category][osm_tag]:
        color_dict[tag_value] = inputdict[category][osm_tag][tag_value][attr]

    return color_dict


def return_weblink_way(string_id):
    return f"<a href=https://www.openstreetmap.org/way/{string_id}>{string_id}</a>"


def return_weblink_node(string_id):
    return f"<a href=https://www.openstreetmap.org/node/{string_id}>{string_id}</a>"


def return_weblink_V2(string_id, featuretype):
    return f"<a href=https://www.openstreetmap.org/{featuretype}/{string_id}>{string_id}</a>"


def return_weblink_V3(type_id_string):
    featuretype, string_id = type_id_string.split("_")
    return f"<a href=https://www.openstreetmap.org/{featuretype}/{string_id}>{string_id}</a>"


"""

HISTORY STUFF

"""


def get_feature_history_url(featureid, type="way"):
    return f"https://www.openstreetmap.org/api/0.6/{type}/{featureid}/history"


def parse_datetime_str(inputstr, format="ymdhms"):

    format_dict = {
        "ymdhms": "%Y-%m-%dT%H:%M:%S",
    }

    return datetime.strptime(inputstr, format_dict[format])


def get_datetime_last_update(
    featureid,
    featuretype="way",
    onlylast=True,
    return_parsed=True,
    return_special_tuple=True,
):
    # TODO: use osmapi!

    h_url = get_feature_history_url(featureid, featuretype)

    try:
        response = requests.get(h_url)
    except:
        if onlylast:
            if return_parsed and return_special_tuple:
                return [None] * 4  # 4 Nones

            return ""
        else:
            return []

    if response.status_code == 200:
        tree = ElementTree.fromstring(response.content)

        element_list = tree.findall(featuretype)

        if element_list:
            date_rec = [element.attrib["timestamp"][:-1] for element in element_list]

            if onlylast:
                if return_parsed:
                    if return_special_tuple:
                        # parsed = datetime.strptime(date_rec[-1],'%Y-%m-%dT%H:%M:%S')
                        parsed = parse_datetime_str(date_rec[-1])
                        return len(date_rec), parsed.day, parsed.month, parsed.year

                    else:
                        # return datetime.strptime(date_rec[-1],'%Y-%m-%dT%H:%M:%S')
                        return parse_datetime_str(date_rec[-1])

                else:
                    return date_rec[-1]

            else:
                if return_parsed:
                    return [parse_datetime_str(record) for record in date_rec]

                else:
                    return date_rec

        else:
            if onlylast:
                return ""
            else:
                return []

    else:
        print("bad request, check feature id/type")
        if onlylast:
            return ""
        else:
            return []


class GetDatetimeLastUpdate:
    import osmapi

    api = osmapi.OsmApi()

    def __init__(self):
        pass

    def get_datetime_last_update_way(self, featureid):
        try:
            res = self.api.WayGet(featureid)
            dt = res["timestamp"]  # date time object
            return res["version"], dt.day, dt.month, dt.year
        except:
            return -1, default_missing_day, default_missing_month, default_missing_year

    def get_datetime_last_update_node(self, featureid):
        try:
            res = self.api.NodeGet(featureid)
            dt = res["timestamp"]  # date time object
            return res["version"], dt.day, dt.month, dt.year
        except:
            return -1, default_missing_day, default_missing_month, default_missing_year


def get_datetime_last_update_node(featureid):
    # all default options
    return get_datetime_last_update(featureid, featuretype="node")


def print_relevant_columnamesV2(
    input_df, not_include=("score", "geometry", "type", "id"), outfilepath=None
):

    as_list = [
        column
        for column in input_df.columns
        if not any(word in column for word in not_include)
    ]

    # print(*as_list)

    if outfilepath:
        with open(outfilepath, "w+") as writer:
            writer.write(",".join(as_list))

    return as_list


def check_if_wikipage_exists(
    name, category="Key:", wiki_page="https://wiki.openstreetmap.org/wiki/"
):

    url = f"{wiki_page}{category}{name}"

    while True:
        try:
            status = requests.head(url).status_code
            break
        except:
            pass

    return status == 200


"""
    geopandas

"""


def gdf_to_js_file(input_gdf, output_path, output_varname):
    """
    this function converts a geopandas dataframe to a javascript file, was the only thing that worked for vectorGrid module

    returns the importing to be included in the html file
    """

    input_gdf.to_file(output_path)

    as_str = f"{output_varname} = " + file_as_string(output_path)

    str_to_file(as_str, output_path)

    return f'<script type="text/javascript" src="{output_path}"></script>'


def create_length_field(input_gdf, fieldname="length(km)", in_km=True):
    factor = 1
    if in_km:
        factor = 1000

    utm_crs = input_gdf.estimate_utm_crs()
    input_gdf[fieldname] = input_gdf.to_crs(utm_crs).length / factor


def create_weblink_field(
    input_gdf, featuretype="LineString", inputfield="id", fieldname="weblink"
):
    if featuretype == "LineString":
        input_gdf[fieldname] = (
            input_gdf[inputfield].astype("string").apply(return_weblink_way)
        )
    if featuretype == "Point":
        input_gdf[fieldname] = (
            input_gdf[inputfield].astype("string").apply(return_weblink_node)
        )


def create_folder_if_not_exists(folderpath):
    if not os.path.exists(folderpath):
        os.makedirs(folderpath)


def create_folderlist(folderlist):
    for folder in folderlist:
        create_folder_if_not_exists(folder)


def remove_if_exists(pathfile):
    if os.path.exists(pathfile):
        os.remove(pathfile)


def listdir_fullpath(path):
    return [os.path.join(path, file) for file in os.listdir(path)]


def get_territory_polygon(place_name, outpath=None, outpath_metadata=None):
    """
    This function takes a place name as input and retrieves the corresponding territory polygon using the Nominatim API. It can also optionally save the polygon as a GeoJSON file.

    Parameters:
        place_name (str): The name of the place for which the territory polygon is to be retrieved.
        outpath (str, optional): The path where the GeoJSON file should be saved. If not provided, the polygon will not be saved.

    Returns:
        dict: The territory polygon as a GeoJSON object.
    """
    # Make a request to Nominatim API with the place name
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": place_name, "format": "json", "polygon_geojson": 1}
    response = requests.get(url, params=params)

    # Parse the response as a JSON object
    data = response.json()

    # sort data by "importance", that is a key in each dictionary of the list:
    data.sort(key=lambda x: x["importance"], reverse=True)

    # Get the polygon of the territory as a GeoJSON object
    polygon = data[0]["geojson"]

    if outpath:
        dump_json(polygon, outpath)

    if outpath_metadata:

        if "geojson" in data[0]:
            del data[0]["geojson"]

        dump_json(data[0], outpath_metadata)

    # Return the polygon
    return polygon


def geodataframe_from_a_geometry(geometry):
    return gpd.GeoDataFrame(geometry=[geometry])


def bbox_geodataframe(bbox, resort=True):
    if resort:
        bbox = resort_bbox(bbox)

    return gpd.GeoDataFrame(geometry=[box(*bbox)])


def resort_bbox(bbox):
    return [bbox[1], bbox[0], bbox[3], bbox[2]]


def merge_list_of_dictionaries(list_of_dicts):
    merged_dict = {}

    for dictionary in list_of_dicts:
        for key, value in dictionary.items():
            if key in merged_dict:
                if not isinstance(merged_dict[key], list):
                    merged_dict[key] = [merged_dict[key]]
                if isinstance(value, list):
                    merged_dict[key].extend(value)
                else:
                    merged_dict[key].append(value)
            else:
                merged_dict[key] = (
                    value if not isinstance(value, list) else value.copy()
                )

    return merged_dict


def join_to_node_homepage(input_list_or_str):
    if isinstance(input_list_or_str, list):
        return os.path.join(node_homepage_url, *input_list_or_str)
    else:
        return os.path.join(node_homepage_url, input_list_or_str)


def save_geoparquet(input_gdf, outpath, rem_empty_columns=True, replace_invalid=None):
    """
    Saves a GeoDataFrame to a Parquet file.
    If the GeoDataFrame is empty, creates an empty Parquet file.

    Workaround for: https://github.com/geopandas/geopandas/issues/3137
    """
    if input_gdf.empty:
        gpd.GeoDataFrame(columns=["geometry"]).to_parquet(outpath)
    else:
        # do all default operations for data exporting
        if rem_empty_columns:
            input_gdf = input_gdf.dropna(axis="columns", how="all")

        if replace_invalid:
            input_gdf = input_gdf.fillna(replace_invalid)

        input_gdf.to_parquet(outpath)


def row_query(df, querydict, mode="any", reverse=False):
    """
    Apply a query to each row in a DataFrame and return a boolean result.

    Args:
        df (DataFrame): The DataFrame/GeoDataFrame to be queried.
        querydict (dict): A dictionary containing the values to query for each column.
        selector (callable): The function to apply to the boolean result for each row. Defaults to any().

    Returns:
        Series: A boolean result for each row of the DataFrame.

    Examples:
        >>> df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
        >>> querydict = {'A': 2, 'B': 6}
        >>> row_query(df, querydict)
        0    False
        1     True
        2    False
        dtype: bool
    """
    if mode == "any":
        selection = df.isin(querydict).any(axis=1)
    elif mode == "all":
        selection = df.isin(querydict).all(axis=1)

    if reverse:
        return ~selection
    else:
        return selection


def get_gdfs_dict(raw_data=False):
    # used dict: paths_dict
    category_group = "data_raw" if raw_data else "data"

    return {
        category: gpd.read_parquet(paths_dict[category_group][category])
        for category in paths_dict[category_group]
    }


def get_gdfs_dict_v2():
    """
    shall include also the specialized categories
    """

    return {
        category: gpd.read_parquet(paths_dict["map_layers"][category])
        for category in paths_dict["map_layers"]
    }


def remove_empty_columns(gdf, report=False):
    if report:
        prev = len(gdf.columns)

    gdf.dropna(axis="columns", how="all", inplace=True)

    if report:
        print(f"    removed {prev-len(gdf.columns)} empty columns")


def get_boundaries_bbox():
    return list(gpd.read_file(boundaries_geojson_path).total_bounds)


def rename_dict_key(
    dictionary, old_key, new_key, ignore_missing=True, ignore_existing=True
):
    if old_key in dictionary and not ignore_missing:
        raise KeyError(f"Key {old_key} not found in dictionary")

    if new_key in dictionary and not ignore_existing:
        raise KeyError(f"Key {new_key} already exists in dictionary")

    if old_key in dictionary:
        dictionary[new_key] = dictionary.pop(old_key)


def create_rev_date(row):
    try:
        return datetime(
            year=int(row["rev_year"]),
            month=int(row["rev_month"]),
            day=int(row["rev_day"]),
        )
    except ValueError:
        # Handle invalid dates, you can return None or a specific default date
        return datetime(
            default_missing_year, default_missing_month, default_missing_day
        )


def create_date_age(row):
    try:
        rev = datetime(
            year=int(row["rev_year"]),
            month=int(row["rev_month"]),
            day=int(row["rev_day"]),
        )
    except ValueError:
        # Handle invalid dates, you can return None or a specific default date
        return -1

    return (datetime.today() - rev).days / 365.25


def get_spaces(number, max_digits=2):
    total_length = max_digits + 1  # +1 for consistent spacing
    num_digits = len(str(number))
    num_spaces = total_length - num_digits
    return " " * num_spaces


def get_formatted_interval_string(n1, n2, max_digits=2):
    spaces1 = get_spaces(n1, max_digits)
    spaces2 = get_spaces(n2, max_digits)

    # # a small correction in case of spaces1 and spaces2 are not equal
    # # not sure if works for max_digits>2
    # if len(spaces1) != len(spaces2):
    #     spaces2 += " "

    if spaces1 == "  ":
        return f" {n1}{spaces1}-{spaces2}{n2}"
    else:
        return f"{n1}{spaces1}-{spaces2}{n2}"
