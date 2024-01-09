from osm_fetch import *
from constants import *
from oswm_codebase.functions import *
from time import sleep

import osmnx as ox


# downloading the boundaries if doesn't exist:
if not os.path.exists(boundaries_path):
    try:
        get_territory_polygon(CITY_NAME,boundaries_path,boundaries_md_path)
        boundaries_gdf = gpd.read_file(boundaries_path)
        boundary_polygon = boundaries_gdf['geometry'].iloc[0]

        # test if it's a polygon:
        if boundary_polygon.geom_type != 'Polygon':
            raise ValueError('not a polygon')
    except:
        # if there's no polygon, use the bounding box as input polygon:
        boundaries_gdf = bbox_geodataframe(BOUNDING_BOX)
        boundaries_gdf.to_file(boundaries_path, driver='GeoJSON')
        metadata = {"class": "bounding_box"}
        dump_json(metadata, boundaries_md_path)
        boundary_polygon = boundaries_gdf['geometry'].iloc[0]
else:
    boundaries_gdf = gpd.read_file(boundaries_path)
    boundary_polygon = boundaries_gdf['geometry'].iloc[0]



for key in layer_tags_dict:
    outpath = f'data/{key}_raw.geojson'

    print('generating ', key, '\n')

    # as_gdf = ox.features_from_bbox(
    # BOUNDING_BOX[2], BOUNDING_BOX[0], BOUNDING_BOX[3], BOUNDING_BOX[1], layer_tags_dict[key])

    as_gdf = ox.features_from_polygon(boundary_polygon, layer_tags_dict[key])

    # working around with Fiona not supporting columns parsed as lists
    for column in as_gdf.columns:
        if as_gdf[column].dtype == object:
            as_gdf[column] = as_gdf[column].astype(str)

    # small adaptations as OSMNX works differently
    as_gdf.reset_index(inplace=True)
    as_gdf.replace('nan', None, inplace=True)
    as_gdf.rename(columns={'osmid': 'id'}, inplace=True)

    as_gdf.to_file(outpath, driver='GeoJSON')


# to record data aging:
record_datetime('Data Fetching')
sleep(.1)

# generate the "report" of the updating info
gen_updating_infotable_page(node_page_url=node_homepage_url)
