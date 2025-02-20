# import pandas as pd
from dq_funcs import *
from quality_dicts import *


gdf_dict = get_gdfs_dict(raw_data=True)

type_dict = geom_type_dict.copy()

type_dict = {
    k: geom_mapping[v[0]] for k, v in type_dict.items()
}  # TODO: check if this works
# reading
existing_keys = read_json(feat_keys_path)

# iterating through feature categories (main processing):
for category in gdf_dict:
    print("for: ", category)
    for i, row in enumerate(gdf_dict[category].itertuples()):

        if i % 200 == 0:
            print("    ", i, " features")

        # iterating through quality categories:
        for quality_category in categories_dict_keys:

            # using an alias to create a shortcut:
            curr = categories_dict_keys[quality_category]

            if not "feature_types" in curr:
                curr["feature_types"] = {}

            if not category in curr["feature_types"]:
                curr["feature_types"][category] = {}

            if curr["type"] == "keys":
                if isinstance(curr["dict"], dict):

                    for osmkey in curr["dict"][category]:
                        value = getattr(row, osmkey, None)

                        if value:
                            if not row.id in curr["occurrences"][category]:
                                val_list = [
                                    row.id,
                                    osmkey,
                                    value,
                                    curr["dict"][category][osmkey],
                                ]

                                add_to_occurrences(
                                    curr, category, val_list, row.id, row.element
                                )

                                add_to_map_data(row, quality_category)

                if isinstance(curr["dict"], str):
                    curr_ref_dict = read_json(curr["dict"])[category]

                    for osmkey in curr_ref_dict:

                        value = getattr(row, osmkey, None)

                        if value:
                            if not row.id in curr["occurrences"][category]:

                                val_list = [
                                    row.id,
                                    osmkey,
                                    value,
                                    "no wiki page for this key",
                                ]

                                add_to_occurrences(
                                    curr, category, val_list, row.id, row.element
                                )

                                add_to_map_data(row, quality_category)

            if curr["type"] == "values":
                if isinstance(curr["dict"], dict):
                    for osmkey in curr["dict"][category]:
                        for osmvalue in curr["dict"][category][osmkey]:
                            if getattr(row, osmkey, None) == osmvalue:
                                if not row.id in curr["occurrences"][category]:

                                    val_list = [
                                        row.id,
                                        osmkey,
                                        osmvalue,
                                        curr["dict"][category][osmkey][osmvalue],
                                    ]

                                    add_to_occurrences(
                                        curr,
                                        category,
                                        val_list,
                                        row.id,
                                        row.element,
                                    )

                                    add_to_map_data(row, quality_category)

                if isinstance(curr["dict"], str):
                    curr_ref_dict = read_json(curr["dict"])[category]

                    for osmkey in curr_ref_dict:
                        for osmvalue in curr_ref_dict[osmkey]:
                            value = getattr(row, osmkey, None)

                            if value:
                                if value not in curr_ref_dict[osmkey]:
                                    if not row.id in curr["occurrences"][category]:

                                        comment = "unlisted at accepted/known values, probably wrong/misspelled"

                                        val_list = [
                                            row.id,
                                            osmkey,
                                            value,
                                            comment,
                                        ]

                                        add_to_occurrences(
                                            curr,
                                            category,
                                            val_list,
                                            row.id,
                                            row.element,
                                        )

                                        add_to_map_data(row, quality_category)

            if curr["type"] == "tags":

                for character in curr["dict"]:
                    for field in row:
                        if isinstance(field, str):
                            if character in field:
                                comment = "ANY (check at feature link)"

                                val_list = [
                                    row.id,
                                    comment,
                                    field,
                                    curr["dict"][character],
                                ]

                                add_to_occurrences(
                                    curr, category, val_list, row.id, row.element
                                )

                                add_to_map_data(row, quality_category)

                                break


# add the  geometric categories, processed elsewhere:
for quality_category in geom_dict_keys:
    curr = geom_dict_keys[quality_category]

    if not "feature_types" in curr:
        curr["feature_types"] = {}

    input_folderpath = curr["path"]

    for filename in os.listdir(input_folderpath):
        filepath = os.path.join(input_folderpath, filename)

        data_category = filename.split(curr["suffix"])[0]

        gdf = gpd.read_parquet(filepath)

        for row in gdf.itertuples():
            # all entries are detections already, we simply add them:
            val_list = [row.id, *curr["dict"][data_category]["insertions"]]

            add_to_occurrences(curr, data_category, val_list, row.id, row.element)
            add_to_map_data(row, quality_category)

# add the "geoms_dicts_keys" to "categories_dict_keys":
for quality_category in geom_dict_keys:
    categories_dict_keys[quality_category] = geom_dict_keys[quality_category]


######### PART 2: files generation

print("generating subpages and files")

# to have all categories in the header:
table_category_headers = []

# iterating again to generate the files:
for category in gdf_dict:
    table_category_headers.append(f"<th><b>{category}</b></th>")

    for quality_category in categories_dict_keys:
        csvpath = f"quality_check/tables/{category}/{quality_category}.csv"

        pagepath = f"quality_check/pages/{category}/{quality_category}.html"

        curr = categories_dict_keys[quality_category]

        # print(quality_category['occurrences'])

        curr["occ_count"][category] = gen_quality_report_page_and_files(
            outpath=pagepath,
            tabledata=list(curr["occurrences"][category].values()),
            feat_types=curr["feature_types"],
            category=category,
            quality_category=quality_category,
            text=curr["about"],
            occ_type=curr["type"],
            csvpath=csvpath,
            invert_geom=curr["invert_geomtype"],
        )

        print(curr["occ_count"][category])


######### PART 3: Quality Check Main page

print("generating QC main page")

tablepart = f"""

    <tr>
    <th><b>Category</b></th>
    {'\n'.join(table_category_headers)}

    
    </tr>

"""

about_part = """
<h3>

"""


topbar = write_dq_topbar(1)

# the webmap!!
create_marker_cluster_html(qc_main_webmap_path, reversed_centerpoint, dq_maps_z_default)

for quality_category in categories_dict_keys:

    tablepart += "<tr>"

    tablepart += f"<td>{quality_category}</td>"

    for category in gdf_dict:

        tablepart += f'<td>  <a href="{node_homepage_url}quality_check/pages/{category}/{quality_category}.html"> {categories_dict_keys[quality_category]["occ_count"][category]} </a> </td>'

    tablepart += "</tr>\n"

    about_part += (
        f"{quality_category} : {categories_dict_keys[quality_category]['about']}<br>\n"
    )

about_part += "</h3>"

# generating the main page:

qcmainpage_txt = f"""

<!DOCTYPE html>

<!-- thx, w3schools, this page was made following their tutorial!! -->

<html lang="en">
<head>

<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
    

{get_font_style(1)}

{get_tables_styles(1)}

<link rel="stylesheet" href="../oswm_codebase/assets/styles/topnav_styles.css">

<style>

h3 {{
    font-size :  16px;
    text-align: left;
    text-align: left;


}}

h2 {{
    font-size :  25px;

}}

h1 {{
    text-align:center;
    font-size :  30px;
}}


</style>

{topbar}

{js_functions_dq}


<title>OSWM DQ Home</title>

<link rel="icon" type="image/x-icon" href="https://kauevestena.github.io/oswm_codebase/assets/homepage/favicon_homepage.png">

</head>
<body>

<h1>OpenSidewalkMap Data Quality Tool</h1>

<p>
This Section is dedicated to find errors in the Features of interest in the Context of OSWM project.<br>
In some cases it's a clear mistake, but it can be just a mispelling or an uncommon value<br><br>

currently, there are the categories presented at the table,<br> each one with the number of occurrences that are item-wise detailed at each link<br>
<a href="{node_homepage_url}issues">you can post suggestions at repo "issues" section</a>

</p>

<table>

{tablepart}


</table>

<p>
The information here can be <b>outdated</b><br>
<a href="{node_homepage_url}data/data_updating.html">here you can check the last update and read more about this</a>
<br>
</p>

<h2>Explaining Each category: </h2>

{about_part}


</body>
</html> 

"""

# saving the quality check categories, so one can request to retrieve them:
quality_categories_shortened = {k: v["about"] for k, v in categories_dict_keys.items()}
dump_json(quality_categories_shortened, qc_categories_index_path)

str_to_file(qcmainpage_txt, qc_mainpage_path)

# AGING RECORDING PART:

# generate the "report" of the updating info
record_datetime("Data Quality Tool")
sleep(0.1)

gen_updating_infotable_page()
