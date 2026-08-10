# import pandas as pd
from dq_funcs import *
from quality_dicts import *
from functions import *
from branding import branding_asset_url




def main():
    qc_logo_url = branding_asset_url("logos.project", "../oswm_codebase")
    qc_favicon_url = branding_asset_url("favicon", "../oswm_codebase")
    gdf_dict = get_gdfs_dict(raw_data=True)

    # Load processed data to access the 'age' and 'last_update' attributes for temporal quality checks
    gdf_dict_processed = get_gdfs_dict(raw_data=False)
    age_lookup = {}
    for cat, p_df in gdf_dict_processed.items():
        if not p_df.empty and 'age' in p_df.columns and 'last_update' in p_df.columns:
            age_lookup[cat] = p_df.set_index('id')[['age', 'last_update']].to_dict('index')


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

                                    add_to_map_data(row, quality_category, category)

                    if isinstance(curr["dict"], str):
                        curr_ref_dict = (
                            read_json(curr["dict"]).get(category, {})
                            if os.path.exists(curr["dict"])
                            else {}
                        )

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

                                    add_to_map_data(row, quality_category, category)

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

                                        add_to_map_data(row, quality_category, category)

                    if isinstance(curr["dict"], str):
                        curr_ref_dict = (
                            read_json(curr["dict"]).get(category, {})
                            if os.path.exists(curr["dict"])
                            else {}
                        )

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

                                            add_to_map_data(row, quality_category, category)

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

                                    add_to_map_data(row, quality_category, category)

                                    break

                if curr["type"] == "age":
                    age_info = age_lookup.get(category, {}).get(row.id)
                    if age_info and age_info['age'] >= 5:
                        comment = "Feature has not been updated in 5 years or more"
                        val_list = [
                            row.id,
                            "last_update",
                            age_info['last_update'],
                            comment,
                        ]
                        add_to_occurrences(
                            curr, category, val_list, row.id, row.element
                        )
                        add_to_map_data(row, quality_category, category)

    # add the  geometric categories, processed elsewhere:
    for quality_category in geom_dict_keys:
        curr = geom_dict_keys[quality_category]

        if not "feature_types" in curr:
            curr["feature_types"] = {}

        input_folderpath = curr["path"]

        for filename in os.listdir(input_folderpath):
            if not filename.endswith(".parquet"):
                continue

            filepath = os.path.join(input_folderpath, filename)

            data_category = filename.split(curr["suffix"])[0]

            gdf = gpd.read_parquet(filepath)

            for row in gdf.itertuples():
                # all entries are detections already, we simply add them:
                val_list = [row.id, *curr["dict"][data_category]["insertions"]]

                add_to_occurrences(curr, data_category, val_list, row.id, row.element)
                add_to_map_data(row, quality_category, data_category)

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
                iso_19157=curr.get("iso_19157", None),
            )

            webmap_outpath = f"quality_check/maps/{category}/{quality_category}.html"
            create_marker_cluster_html(
                webmap_outpath,
                reversed_centerpoint,
                dq_maps_z_default,
                specific_q_category=quality_category,
                specific_category=category,
                title=f"{category} / {quality_category}",
                back_url=f"../../pages/{category}/{quality_category}.html",
                back_text=f"← Back to {quality_category}",
                logo_url=branding_asset_url("logos.project", "../../../oswm_codebase"),
                favicon_url=branding_asset_url("favicon", "../../../oswm_codebase")
            )

    ######### PART 3: Quality Check Main page

    print("generating QC main page")

    tablepart = f"""

        <tr>
        <th><b>Category</b></th>
        {'\n'.join(table_category_headers)}
        <th><b>ISO 19157 Type</b></th>
    
        </tr>

    """

    about_part = ""


    topbar = write_dq_topbar(1)

    # the webmap!!
    create_marker_cluster_html(qc_main_webmap_path, reversed_centerpoint, dq_maps_z_default)

    # ISO 19157 element badge colors
    iso_badge_colors = {
        "Thematic Accuracy": ("#a78bfa", "rgba(167, 139, 250, 0.15)", "rgba(167, 139, 250, 0.3)"),
        "Logical Consistency": ("#00f2fe", "rgba(0, 242, 254, 0.15)", "rgba(0, 242, 254, 0.3)"),
    }

    def iso_badge_html(iso_info):
        """Generate a styled badge for an ISO 19157 element."""
        element = iso_info["element"]
        sub_el = iso_info["sub_element"]
        color, bg, border = iso_badge_colors.get(element, ("#94a3b8", "rgba(148, 163, 184, 0.15)", "rgba(148, 163, 184, 0.3)"))
        return f'<span style="display:inline-block; background:{bg}; border:1px solid {border}; color:{color}; padding:3px 10px; border-radius:6px; font-size:0.8rem; font-weight:500; line-height:1.4;">{element}<br><span style="font-size:0.7rem; opacity:0.85;">→ {sub_el}</span></span>'

    for quality_category in categories_dict_keys:

        tablepart += "<tr>"

        tablepart += f"<td>{quality_category}</td>"

        for category in gdf_dict:

            tablepart += f'<td>  <a href="pages/{category}/{quality_category}.html"> {categories_dict_keys[quality_category]["occ_count"][category]} </a> </td>'

        # ISO 19157 column
        iso_info = categories_dict_keys[quality_category].get("iso_19157", {})
        if iso_info:
            tablepart += f'<td>{iso_badge_html(iso_info)}</td>'
        else:
            tablepart += '<td>—</td>'

        tablepart += "</tr>\n"

        # about section with ISO info
        iso_label = ""
        if iso_info:
            iso_label = f' — <em style="color:#94a3b8;">ISO 19157: {iso_info["element"]} → {iso_info["sub_element"]}</em>'
        about_part += (
            f'<div style="background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 0.8rem 1rem; margin-bottom: 0.5rem;">'
            f'<b style="color:#f8fafc;">{quality_category}</b> : '
            f'<span style="color:#cbd5e1;">{categories_dict_keys[quality_category]["about"]}</span>'
            f'{iso_label}</div>\n'
        )

    print("generating subpages and files")

    tablepart += "<tr>"
    tablepart += "<td><b>Totals:</b></td>"
    for category in gdf_dict:
        tot_cat = 0
        for quality_category in categories_dict_keys:
            tot_cat += categories_dict_keys[quality_category]["occ_count"][category]
        tablepart += f"<td><b>{tot_cat}</b></td>"
    tablepart += "<td></td>"  # empty cell for ISO column in totals row
    tablepart += "</tr>\n"

    print("generating QC main page")

    # ISO 19157 reference legend
    iso_legend = """
    <div style="background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 1.5rem; margin: 1.5rem 0; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h3 style="margin-top: 0; color: #f8fafc; font-size: 1.3rem;">📐 ISO 19157:2013 — Data Quality Reference</h3>
        <p style="color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.5rem;">Each quality category is classified according to <a href="https://www.iso.org/standard/32575.html" style="color: #00f2fe; text-decoration: none;">ISO 19157:2013</a>. The classification uses the standard's 5 main quality elements:</p>
        
        <div style="display: flex; flex-direction: column; gap: 1rem;">
            
            <div style="background: rgba(167, 139, 250, 0.1); border: 1px solid rgba(167, 139, 250, 0.3); border-radius: 8px; padding: 1rem;">
                <h4 style="color: #a78bfa; margin: 0 0 0.5rem 0; font-size: 1rem; font-weight: 600;">Thematic Accuracy</h4>
                <div style="color: #cbd5e1; font-size: 0.85rem; display: flex; flex-wrap: wrap; gap: 1.5rem;">
                    <span>• <b>Non-quantitative Attribute Accuracy</b></span>
                    <span>• Classification Correctness</span>
                    <span>• Quantitative Attribute Accuracy</span>
                </div>
            </div>

            <div style="background: rgba(0, 242, 254, 0.1); border: 1px solid rgba(0, 242, 254, 0.3); border-radius: 8px; padding: 1rem;">
                <h4 style="color: #00f2fe; margin: 0 0 0.5rem 0; font-size: 1rem; font-weight: 600;">Logical Consistency</h4>
                <div style="color: #cbd5e1; font-size: 0.85rem; display: flex; flex-wrap: wrap; gap: 1.5rem;">
                    <span>• <b>Topological Consistency</b></span>
                    <span>• <b>Conceptual Consistency</b></span>
                    <span>• <b>Format Consistency</b></span>
                    <span>• Domain Consistency</span>
                </div>
            </div>
            
            <div style="background: rgba(148, 163, 184, 0.1); border: 1px solid rgba(148, 163, 184, 0.3); border-radius: 8px; padding: 1rem;">
                <h4 style="color: #94a3b8; margin: 0 0 0.5rem 0; font-size: 1rem; font-weight: 600;">Temporal Accuracy</h4>
                <div style="color: #cbd5e1; font-size: 0.85rem; display: flex; flex-wrap: wrap; gap: 1.5rem;">
                    <span>• <b>Temporal Validity</b></span>
                    <span>• Temporal Consistency</span>
                    <span>• Accuracy of a Time Measurement</span>
                </div>
            </div>

            <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px; padding: 1rem;">
                <h4 style="color: #38bdf8; margin: 0 0 0.5rem 0; font-size: 1rem; font-weight: 600;">Positional Accuracy</h4>
                <div style="color: #cbd5e1; font-size: 0.85rem; display: flex; flex-wrap: wrap; gap: 1.5rem;">
                    <span>• Absolute or External Accuracy</span>
                    <span>• Relative or Internal Accuracy</span>
                    <span>• Gridded Data Position Accuracy</span>
                </div>
            </div>

            <div style="background: rgba(74, 222, 128, 0.1); border: 1px solid rgba(74, 222, 128, 0.3); border-radius: 8px; padding: 1rem;">
                <h4 style="color: #4ade80; margin: 0 0 0.5rem 0; font-size: 1rem; font-weight: 600;">Completeness</h4>
                <div style="color: #cbd5e1; font-size: 0.85rem; display: flex; flex-wrap: wrap; gap: 1.5rem;">
                    <span>• Commission (excess data)</span>
                    <span>• Omission (missing data)</span>
                </div>
                <div style="color: #cbd5e1; font-size: 0.85rem; margin-top: 0.5rem; font-style: italic;">Note: Completeness is evaluated in a zonal-based fashion in the <a href="completeness/index.html" style="color: #4ade80;">OSWM Completeness Map</a>.</div>
            </div>

        </div>
        <p style="color: #64748b; font-size: 0.8rem; margin: 1rem 0 0 0; font-style: italic;">Bold sub-elements are currently used in the per-feature quality checks.</p>
    </div>
    """

    # generating the main page:

    qcmainpage_txt = f"""<!--
      Generated automatically by oswm_codebase/data_quality/quality_check_compiling.py
      Do not edit this file directly.
    -->
    <!DOCTYPE html>

    <!-- thx, w3schools, this page was made following their tutorial!! -->

    <html lang="en">
    <head>

    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
    
    {get_font_style(1)}

    {get_tables_styles(1)}

    <link rel="stylesheet" href="../oswm_codebase/assets/styles/topnav_styles.css">

    <title>OSWM DQ Home</title>

    <link rel="icon" type="image/x-icon" href="{qc_favicon_url}">

    </head>
    <body>
    {topbar}
    {js_functions_dq}

    <main class="dq-container">
        <h1><img src="{qc_logo_url}" alt="OSWM Logo" style="height: 1.5em; vertical-align: middle; margin-right: 15px;">OpenSidewalkMap Data Quality Tool</h1>

        <div style="display: flex; gap: 1rem; margin: 1rem 0; flex-wrap: wrap;">
            <div style="flex: 1; min-width: 300px; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(0, 242, 254, 0.3); border-radius: 12px; padding: 1.5rem; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.15);">
                <h3 style="margin-top: 0; color: #00f2fe;">Interactive QA Webmap</h3>
                <p style="font-size: 0.9rem; margin-bottom: 1rem;">Explore all generated detections clustered on a map.</p>
                <a href="map.html" style="display: inline-block; background: linear-gradient(to right, #00f2fe, #4facfe); color: #0f172a; padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 1rem; transition: transform 0.2s;">Open Quality Assurance Map</a>
            </div>
            
            <div style="flex: 1; min-width: 300px; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 12px; padding: 1.5rem; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.15);">
                <h3 style="margin-top: 0; color: #d8b4fe;">Completeness Webmap</h3>
                <p style="font-size: 0.9rem; margin-bottom: 1rem;">Analyze temporal footway and sidewalk completeness.</p>
                <a href="completeness/index.html" style="display: inline-block; background: linear-gradient(to right, #c084fc, #e879f9); color: #0f172a; padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 1rem; transition: transform 0.2s;">Open Completeness Map</a>
            </div>
        </div>

        <p>
        This Section is dedicated to find errors in the Features of interest in the Context of OSWM project.<br>
        In some cases it's a clear mistake, but it can be just a mispelling or an uncommon value<br><br>

        currently, there are the categories presented at the table,<br> each one with the number of occurrences that are item-wise detailed at each link<br>
        <a href="{codebase_issues_url}">you can post suggestions at repo "issues" section</a>
        </p>

        <table>

        {tablepart}

        </table>

        <p style="font-size: 0.9em">
        The information here can be <b>outdated</b><br>
        <a href="../updating_infos.html">here you can check the last update and read more about this</a>
        </p>

        {iso_legend}

        <h2>Explaining Each category: </h2>

        {about_part}
    </main>
    </body>
    </html> 
    """

    # saving the quality check categories (enriched with ISO 19157), so one can request to retrieve them:
    quality_categories_shortened = {}
    for k, v in categories_dict_keys.items():
        entry = {"about": v["about"]}
        iso = v.get("iso_19157", {})
        if iso:
            entry["iso_19157_element"] = iso["element"]
            entry["iso_19157_sub_element"] = iso["sub_element"]
        quality_categories_shortened[k] = entry
    dump_json(quality_categories_shortened, qc_categories_index_path)

    str_to_file(qcmainpage_txt, qc_mainpage_path)
    str_to_file(qcmainpage_txt, os.path.join(dq_rootfolder, "index.html"))

    # AGING RECORDING PART:

    # generate the "report" of the updating info
    record_datetime("Data Quality Tool")
    sleep(0.1)

    gen_updating_infotable_page()

if __name__ == '__main__':
    main()
