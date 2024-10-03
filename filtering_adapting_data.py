from constants import *
from oswm_codebase.functions import *
import pandas as pd
import geopandas as gpd
from time import sleep
from shapely import unary_union

import os

print("     - Reading Data")

# gdf_dict = {datalayerpath: gpd.read_parquet(paths_dict['data_raw'][datalayerpath]) for datalayerpath in paths_dict['data_raw']}

gdf_dict = get_gdfs_dict(raw_data=True)

print("     - Fetching updating info")
# updating info:

# updating_dict = {}

# for datalayerpath in paths_dict['versioning']:
# 	updating_dict[datalayerpath] = pd.read_json(paths_dict['versioning'][datalayerpath])

# updating_dict = {datalayerpath: pd.read_json(paths_dict['versioning'].get(datalayerpath,StringIO(r"{}")))
#                 for datalayerpath
#                 in paths_dict['versioning']}

updating_dict = {}
for category in paths_dict["versioning"]:
    category_path = paths_dict["versioning"][category]

    if os.path.exists(category_path):
        updating_dict[category] = pd.read_json(category_path)
    else:
        updating_dict[category] = pd.DataFrame()


# sidewalks_updating = pd.read_json(sidewalks_path_versioning)
# crossings_updating = pd.read_json(crossings_path_versioning)
# kerbs_updating = pd.read_json(kerbs_path_versioning)

# updating_dict = {'sidewalks':sidewalks_updating,'crossings':crossings_updating,'kerbs':kerbs_updating}


# # reading the conversion table from  surface and smoothness:
# # exported from: https://docs.google.com/spreadsheets/d/18FiIDUV4xGeTskx3R2i841zir_OO1Cdc_zluPLdPq     -w/edit#gid=0
# smoothness_surface_conservation = pd.read_csv('data/smoothness_surface_conservationscore.csv',index_col='surface').transpose()

# creating the symlinks for specific stuff:
sidewalks_gdf = gdf_dict["sidewalks"]
crossings_gdf = gdf_dict["crossings"]
local_utm = (
    sidewalks_gdf.estimate_utm_crs()
)  # TODO: establish a global method to have this

# # removing unconnected crossings and kerbs (preparation):
sidewalks_big_unary_buffer = (
    sidewalks_gdf.to_crs(local_utm)
    .buffer(max_radius_cutoff)
    .to_crs("EPSG:4326")
    .unary_union
)

crossings_big_unary_buffer = (
    crossings_gdf.to_crs(local_utm)
    .buffer(max_radius_cutoff)
    .to_crs("EPSG:4326")
    .unary_union
)

sidewalks_crossings_unary_buffer = unary_union(
    [sidewalks_big_unary_buffer, crossings_big_unary_buffer]
)

# removing entries that arent in the buffer:
# dealing with the data:
for category in gdf_dict:
    print(category)

    if (category != "sidewalks") and (category != "other_footways"):
        print(f"     - Removing unconnected features")

        create_folder_if_not_exists(disjointed_folderpath)

        # TODO: include other footways here
        if category != "kerbs":
            disjointed = gdf_dict[category].disjoint(sidewalks_big_unary_buffer)
        else:
            disjointed = gdf_dict[category].disjoint(sidewalks_crossings_unary_buffer)

        outfilepath = os.path.join(
            disjointed_folderpath, f"{category}_disjointed" + data_format
        )

        # gdf_dict[category][disjointed].to_file(os.path.join(disjointed_folderpath,f'{category}_disjointed' + data_format))

        save_geoparquet(gdf_dict[category][disjointed], outfilepath)

        gdf_dict[category] = gdf_dict[category][~disjointed]

    print("     - Removing features with improper geometry type")
    # removing the ones that aren't of the specific intended geometry type:
    # but first saving them for quality tool:

    create_folder_if_not_exists(improper_geoms_folderpath)
    outpath_improper = os.path.join(
        improper_geoms_folderpath, f"{category}_improper_geoms" + data_format
    )
    # the boolean Series:
    are_proper_geom = gdf_dict[category].geometry.type.isin(
        geom_type_dict[category]
    )  # TODO: test this out     -of     -the     -box
    # saving:
    # gdf_dict[category][~are_proper_geom].to_file(outpath_improper)

    save_geoparquet(gdf_dict[category][~are_proper_geom], outpath_improper)

    # now keeping only the ones with proper geometries:
    gdf_dict[category] = gdf_dict[category][are_proper_geom]

    # print('     - Filling invalids with "?"')

    # # referencing the geodataframe:
    # for req_col in req_fields[category]:
    #     if not req_col in gdf_dict[category]:
    #         gdf_dict[category][req_col] = '?'

    #         # also creating a default note
    #         gdf_dict[category][f'{req_col}_score'] = default_score

    # # replacing missing values with '?', again:
    gdf_dict[category].fillna("?", inplace=True)

    # replacing wrong values with "?" (unknown) or misspelled with the nearest valid:
    # TODO: check if this is the better approach to handle invalid values
    print("     - Replacing Utterly invalid values")
    for subkey in wrong_misspelled_values[category]:
        gdf_dict[category].loc[:, subkey] = gdf_dict[category][subkey].replace(
            wrong_misspelled_values[category][subkey]
        )

    # print('     - Computing scores')
    # # conservation state (as a score):
    # if category != 'kerbs':
    #     gdf_dict[category]['conservation_score'] = [smoothness_surface_conservation[surface][smoothness] for surface,smoothness in zip(gdf_dict[category]['surface'],gdf_dict[category]['smoothness'])]

    # # creating a score for each field, based on the "default_scores"
    # # in future other categories may be crated
    # for osm_key in fields_values_properties[category]:
    #     # print(category,' : ',osm_key)
    #     gdf_dict[category] = gdf_dict[category].join(scores_dfs[category][osm_key].set_index(osm_key), on=osm_key)

    # if category != 'kerbs':
    #     # gdf_dict[category]['initial_score'] = 'Point'
    #     # crating aliases
    #     sf = gdf_dict[category][scores_dfs_fieldnames[category]['surface']]
    #     co = gdf_dict[category]['conservation_score']

    #     # harmonic mean:
    #     gdf_dict[category]['final_score'] = (2*sf*co)/(sf+co)

    # mapping surface+smoothness to score of conservation:

    # mapping surface to notes:

    # creating a simple metric for the

    # if category == 'kerbs':
    #     # just a mere copy, but it may be improved in the future...

    #     gdf_dict[category]['final_score'] = gdf_dict[category][scores_dfs_fieldnames[category]['kerb']]

    #     pass

    # if category == 'crossings':
    #     # same as sidewalks but with bonifications

    #     gdf_dict[category]['final_score'] += gdf_dict[category][scores_dfs_fieldnames[category]['crossing']]

    print("     - Adding update data")

    # inserting last update:
    if not updating_dict[category].empty:

        updating_dict[category]["last_update"] = (
            updating_dict[category]["rev_day"].astype(str)
            + "-"
            + updating_dict[category]["rev_month"].astype(str)
            + "-"
            + updating_dict[category]["rev_year"].astype(str)
        )

        updating_dict[category]["age"] = updating_dict[category].apply(
            create_date_age, axis=1
        )

        # joining the updating info dict to the geodataframe:
        gdf_dict[category] = (
            gdf_dict[category]
            .set_index("id")
            .join(
                updating_dict[category].set_index("osmid")["last_update"]
                # ,rsuffix = 'r_remove',lsuffix = 'l_remove',
            )
            .reset_index()
        )
    else:
        gdf_dict[category]["last_update"] = "unavailable"
        gdf_dict[category]["age"] = -1

    # gdf_dict[category]['last_update'] = gdf_dict[category]['update_date']

    # now spliting the Other_Footways into categories:
    if category == "other_footways":
        create_folder_if_not_exists(other_footways_folderpath)

        print("     - Splitting Other_Footways into subcategories")
        # first of all, saving the polygons/multipolygons to a separate category, called "pedestrian areas":
        are_areas = gdf_dict[category].geometry.type.isin(["Polygon", "MultiPolygon"])
        print("       - Saving pedestrian areas")

        ped_areas_gdf = gdf_dict[category][are_areas].copy()
        remove_empty_columns(ped_areas_gdf)

        save_geoparquet(
            ped_areas_gdf,
            paths_dict["other_footways_subcategories"]["pedestrian_areas"],
        )

        other_footways_gdf = gdf_dict[category][~are_areas].copy()
        remove_empty_columns(other_footways_gdf)

        for subcategory in other_footways_subcatecories:
            print("       - Saving ", subcategory)

            if subcategory == "pedestrian_areas":
                continue

            belonging = row_query(
                other_footways_gdf, other_footways_subcatecories[subcategory]
            )

            belonging_gdf = other_footways_gdf[belonging].copy()
            remove_empty_columns(belonging_gdf)

            save_geoparquet(
                belonging_gdf, paths_dict["other_footways_subcategories"][subcategory]
            )

            # optimize keeping only the remaining rows
            other_footways_gdf = other_footways_gdf[~belonging]

    # removing empty columns:
    remove_empty_columns(gdf_dict[category])
    save_geoparquet(gdf_dict[category], f"data/{category}" + data_format)


# generate the "report" of the updating info
record_datetime("Data Pre     -Processing")
sleep(0.1)

gen_updating_infotable_page()
