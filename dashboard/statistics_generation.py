from statistics_specs import *
import argparse
import numpy as np

# add an option "--single" to generate a single chart specified as an string
parser = argparse.ArgumentParser()
parser.add_argument("--single", type=str, default=None)

# add an argument to raise on failure:
parser.add_argument("--to_raise", action="store_true")

args = parser.parse_args()

single_chart = args.single

# loading the data:
gdfs_dict = get_gdfs_dict(include_all_data_dummy=True)

# data adaptation (preprocessing)
for category in gdfs_dict:
    # creating the  folder if it does not exist
    create_folder_if_not_exists(os.path.join(statistics_basepath, category))
    create_folder_if_not_exists(os.path.join(statistcs_specs_path, category))

    if category == "all_data":
        continue

    # creating a ref to improve readability
    cat_gdf = gdfs_dict[category]

    print("Adaptations for:", category)

    # creating additional fields

    if "LineString" in geom_type_dict[category]:
        create_length_field(cat_gdf)

    if category != "other_footways":
        cat_gdf["category"] = category
    else:
        cat_gdf["category"] = cat_gdf[oswm_footway_fieldname]

    # if category == "kerbs":
    #     cat_gdf["length(km)"] = 0

    # replace the -1 in "n_revs" with np.nan
    if "n_revs" in cat_gdf:
        cat_gdf["n_revs"] = cat_gdf["n_revs"].replace(-1, np.nan)

# # creating a meta-category "all_data" for all data:
gdfs_dict["all_data"] = pd.concat(gdfs_dict.values(), ignore_index=True)

# storing chart infos:
generated_list_dict = {}
charts_titles = {}
charts_explanations = {}

# generating the charts by using the specifications
with open(os.path.join(statistics_basepath, "failed_gen.txt"), "w+") as error_report:
    charts_specs = get_charts_specs(gdfs_dict=gdfs_dict)

    for category in charts_specs:
        generated_list_dict[category] = []
        for chart_spec in charts_specs[category]:

            # to add the hability to generate a single chart, mainly for testing
            if single_chart:
                if chart_spec != single_chart:
                    continue

            try:
                spec = charts_specs[category][chart_spec]
                outpath = os.path.join(
                    statistics_basepath, category, chart_spec + ".html"
                )

                # the json spec:
                json_outpath = os.path.join(
                    statistcs_specs_path, category, chart_spec + ".json"
                )

                # remove_if_exists(outpath)

                print("generating ", outpath)
                chart_obj = spec["function"](**spec["params"])
                chart_obj.save(outpath)

                print("generating ", json_outpath)
                chart_obj.save(json_outpath)

                generated_list_dict[category].append(outpath)

                # # extra charts info:
                # Title:
                charts_titles[outpath] = spec["title"]

                # Explanation:
                charts_explanations[outpath] = explanation_base.format(
                    spec["explanation"]
                )

            except Exception as e:
                print(
                    "failed ",
                    chart_spec,
                    ' writing to report file at "statistics folder"',
                )
                error_report.write(chart_spec + "\n")

                if args.to_raise:
                    raise

# the topbar for each category
topbar = f"""
    
    <div class="topnav" id="stTopnav">
        <a href="{node_homepage_url}" class="active">Go to Node Home</a>
    """

print(generated_list_dict)

for category in generated_list_dict:
    if not generated_list_dict[category]:
        print("no charts generated for: ", category)
        continue

    category_homepage = get_url(generated_list_dict[category][0])

    topbar += f'<a href="{category_homepage}">{category.replace("_", " ").title()} Charts</a>\n'


topbar += """
   <a href="javascript:void(0);" class="icon" onclick="responsiveTopNav()">
     <i class="fa fa-bars"></i>
   </a>
 </div>
 
 """

sidebar_begin = '<div class="sidebar">\n'

category_bars = {}

for category in generated_list_dict:
    # url_list = [get_url(rel_path) for rel_path in generated_list_dict[category]]

    # this dict is meant to be temporary and merely classwise:
    full_url_dict = {}
    for rel_path in generated_list_dict[category]:
        full_url_dict[rel_path] = get_url(rel_path)

    category_bars[category] = topbar + sidebar_begin

    for rel_path in full_url_dict:
        category_bars[
            category
        ] += f'  <a href="{full_url_dict[rel_path]}">{charts_titles[rel_path]}</a>\n'

    category_bars[category] += "</div>\n\n"

# iterating again to modify pages only once:
for category in generated_list_dict:
    for i, rel_path in enumerate(generated_list_dict[category]):
        # creating the file handler object
        fileObj = fileAsStrHandler(rel_path)

        # global insertions, they are meant to be inserted in every file
        for insertpoint in global_insertions:
            fileObj.simple_replace(insertpoint, global_insertions[insertpoint])

        # global exclusions, they are meant to be removed in every file
        for exclusion_specs in global_exclusions:
            to_remove = find_between_strings(
                fileObj.content,
                *exclusion_specs["points"],
                include_linebreaks=exclusion_specs["multiline"],
            )
            for removable in to_remove:
                fileObj.simple_replace(
                    exclusion_specs["points"][0]
                    + removable
                    + exclusion_specs["points"][1]
                )

        # category specific insertions (topbar and sidebar)
        fileObj.simple_replace("<head>", "<head>\n" + category_bars[category])

        # inserting the explanations:
        fileObj.simple_replace("</body>", charts_explanations[rel_path] + "\n</body>")

        fileObj.rewrite()

        # # # dashboard homepage writing:
        # if i == 0 and category == "sidewalks":

        #     fileObj.write_to_another_path(
        #         os.path.join(statistics_basepath, "index.html")
        #     )

# Dashboard homepage writing:
fileObj = fileAsStrHandler(
    os.path.join(statistics_basepath, "index.html"), start_over=True
)

fileObj.content = basic_html

for insertpoint in global_insertions:
    fileObj.simple_replace(insertpoint, global_insertions[insertpoint])

fileObj.simple_replace("<head>", "<head>\n" + topbar)

for inclusion in dashboard_main_page_insertions:
    fileObj.simple_replace(inclusion, dashboard_main_page_insertions[inclusion])

fileObj.rewrite()

# to record data aging:
record_datetime("Statistical Charts")
# generate the "report" of the updating info
gen_updating_infotable_page()
