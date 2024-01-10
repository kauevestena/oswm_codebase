from osm_fetch import *
from constants import *
from oswm_codebase.functions import *
from time import sleep, time
import osmnx as ox

# Getting the boundaries:
# downloading the boundaries if doesn't exist:
print('checking boundaries...')
if not os.path.exists(boundaries_geojson_path):
    try:
        get_territory_polygon(CITY_NAME,boundaries_geojson_path,boundaries_md_path)
        boundaries_gdf = gpd.read_file(boundaries_geojson_path)
        boundary_polygon = boundaries_gdf['geometry'].iloc[0]

        # test if it's a polygon:
        if boundary_polygon.geom_type != 'Polygon' or boundary_polygon.geom_type != 'MultiPolygon':
            raise ValueError('not a polygon')
        
        # if it's a polygon, save it as geoparquet:
        save_geoparquet(boundaries_gdf, boundaries_path)
    except:
        # if there's no polygon, use the bounding box as input polygon:
        boundaries_gdf = bbox_geodataframe(BOUNDING_BOX)
        boundaries_gdf.to_file(boundaries_geojson_path)
        save_geoparquet(boundaries_gdf, boundaries_path)
        metadata = {"class": "bounding_box"}
        dump_json(metadata, boundaries_md_path)
        boundary_polygon = boundaries_gdf['geometry'].iloc[0]
else:
    boundaries_gdf = gpd.read_file(boundaries_geojson_path)
    boundary_polygon = boundaries_gdf['geometry'].iloc[0]


# New approach: download all categories at once and then split in different layers:
print ('downloading all data')

t1 = time()
as_gdf = ox.features_from_polygon(boundary_polygon,merge_list_of_dictionaries(layer_tags_dict.values()))
print(f'    took {time()-t1:.2f} seconds, with {len(as_gdf)} features')

# removing all with globally invalid values:
as_gdf = as_gdf[~as_gdf.isin(OTHER_FOOTWAY_EXCLUSION_RULES).any(axis=1)]
print(f'    now with {len(as_gdf)} features after filtering out with exclusion rules')

# working around with Fiona not supporting columns parsed as lists
for column in as_gdf.columns:
    if as_gdf[column].dtype == object:
        as_gdf[column] = as_gdf[column].astype(str)

# adapting osmnx output:
as_gdf.reset_index(inplace=True)
as_gdf.replace('nan', None, inplace=True)
as_gdf.rename(columns={'osmid': 'id'}, inplace=True)

print('splitting layers:')
# small adaptations as OSMNX works differentlydownloaded in
for category in layer_tags_dict:
    # outpath = f'data/{category}_raw.geojson'
    outpath = paths_dict['data_raw'][category]

    belonging = as_gdf.isin(layer_tags_dict[category]).any(axis=1)

    # as_gdf[belonging].to_file(outpath)
    save_geoparquet(as_gdf[belonging], outpath)

    as_gdf = as_gdf[~belonging]

    print('    picking', category,'from data, with', len(as_gdf),'remaining')

    # as_gdf = ox.features_from_bbox(
    # BOUNDING_BOX[2], BOUNDING_BOX[0], BOUNDING_BOX[3], BOUNDING_BOX[1], layer_tags_dict[category])

print('finishing...')
# to record data aging:
record_datetime('Data Fetching')
sleep(.1)

# generate the "report" of the updating info
gen_updating_infotable_page()
