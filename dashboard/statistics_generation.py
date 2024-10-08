from statistics_specs import *
import argparse

# add an option "--single" to generate a single chart specified as an string
parser = argparse.ArgumentParser()
parser.add_argument("--single", type=str, default=None)
args = parser.parse_args()

single_chart = args.single

# data adaptation
for category in gdfs_dict:
    # creating the  folder if it does not exist
    create_folder_if_not_exists(os.path.join(statistics_basepath, category))
    create_folder_if_not_exists(os.path.join(statistcs_specs_path, category))

    # creating a ref to improve readability
    cat_gdf = gdfs_dict[category]
    update_df = updating_dicts[category]

    print("Adaptations for:", category)

    # creating additional fields

    if "LineString" in geom_type_dict[category]:
        create_length_field(cat_gdf)
        create_weblink_field(cat_gdf)
    elif "Point" in geom_type_dict[category]:
        create_weblink_field(cat_gdf, "Point")

    # uncertain about polygon cases
    # elif (:
    #     geom_type_dict[category] == "Polygon"
    #     or geom_type_dict[category] == "MultiPolygon"
    # ):
    #     create_weblink_field(gdfs_dict[category])

    if "survey:date" in cat_gdf.columns:

        cat_gdf["Year of Survey"] = cat_gdf["survey:date"].apply(get_year_surveydate)

    # updating info:
    update_df["month_year"] = (
        update_df["rev_month"].map("{:02d}".format)
        + "_"
        + update_df["rev_year"].astype(str)
    )

    update_df["year_month"] = (
        update_df["rev_year"].astype(str)
        + "_"
        + update_df["rev_month"].map("{:02d}".format)
    )

    update_df.sort_values("year_month", inplace=True)

    # Fill missing values with a default (e.g., 1 for month or day) TODO: move to data adaptation script
    update_df["rev_year"] = (
        update_df["rev_year"].fillna(default_missing_year).astype(int)
    )
    update_df["rev_month"] = (
        update_df["rev_month"].fillna(default_missing_month).astype(int)
    )
    update_df["rev_day"] = update_df["rev_day"].fillna(default_missing_day).astype(int)

    update_df["rev_date_obj"] = update_df.apply(create_rev_date, axis=1)

    update_df["age_years"] = (
        pd.Timestamp(datetime.today()) - update_df["rev_date_obj"]
    ).dt.days / 365.25

    cat_gdf["category"] = category

# creating a meta-category "all_data" for all data:
gdfs_dict["all_data"] = pd.concat(gdfs_dict.values(), ignore_index=True)

# storing chart infos:
generated_list_dict = {}
charts_titles = {}

# generating the charts by using the specifications
with open(os.path.join(statistics_basepath, "failed_gen.txt"), "w+") as error_report:
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
                chart_obj = spec["function"](*spec["params"])
                chart_obj.save(outpath)

                print("generating ", json_outpath)
                chart_obj.save(json_outpath)

                generated_list_dict[category].append(outpath)
                charts_titles[outpath] = spec["title"]
            except Exception as e:
                print(
                    "failed ",
                    chart_spec,
                    ' writing to report file at "statistics folder"',
                )
                error_report.write(chart_spec + "\n")

# the topbar for each category
topbar = f"""
    
    <div class="topnav" id="stTopnav">
        <a href="{node_homepage_url}" class="active">Home</a>
    """

print(generated_list_dict)

for category in generated_list_dict:
    if not generated_list_dict[category]:
        print("no charts generated for: ", category)
        continue

    category_homepage = get_url(generated_list_dict[category][0])

    topbar += f'<a href="{category_homepage}">{category.capitalize()} Charts</a>\n'


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
        fileObj = fileAsStrHandler(rel_path)

        for insertpoint in global_insertions:
            fileObj.simple_replace(insertpoint, global_insertions[insertpoint])

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

        fileObj.simple_replace("<head>", "<head>\n" + category_bars[category])

        fileObj.rewrite()

        if i == 0 and category == "sidewalks":
            fileObj.write_to_another_path(
                os.path.join(statistics_basepath, "index.html")
            )


# to record data aging:
record_datetime("Statistical Charts")
# generate the "report" of the updating info
gen_updating_infotable_page()
