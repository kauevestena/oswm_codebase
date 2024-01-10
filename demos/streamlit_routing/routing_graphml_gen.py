import osmnx as ox
import geopandas as gpd
import pandas as pd
from shapely.geometry import box


"""
 thx, Boeing, G. 2017. OSMnx: New Methods for Acquiring, Constructing, Analyzing, and Visualizing Complex Street Networks. Computers, Environment and Urban Systems, 65, 126-139. https://doi.org/10.1016/j.compenvurbsys.2017.05.004

"""
routing_elevation = False


Slat = -25.46340831586
Wlgt = -49.26485433156466
Nlat = -25.45836407828201
Elgt = -49.257818266840495


G_tenblocks = ox.graph_from_bbox( Nlat,Slat,Elgt,Wlgt,
# network_type="walk",
custom_filter='["footway"~"sidewalk|crossing"]',
simplify=False,
# retain_all=True,
)


tenb_nodes, tenb_edges = ox.utils_graph.graph_to_gdfs(G_tenblocks)

working_crs = tenb_edges.estimate_utm_crs()


sidewalks_gdf = gpd.read_parquet(sidewalks_path) #.to_crs(WORKING_CRS)
crossings_gdf = gpd.read_parquet(crossings_path).set_index(['id']) #.to_crs(WORKING_CRS)
kerbs_gdf = gpd.read_parquet(kerbs_path).set_index(['id']) #.to_crs(WORKING_CRS)

kerbs_gdf['final_score'].fillna(-30,inplace=True)
crossings_gdf['final_score'].fillna(0,inplace=True)
sidewalks_gdf['final_score'].fillna(0,inplace=True)

kerbs_buffered_gdf = kerbs_gdf.copy()

kerbs_buffered_gdf['geometry'] = kerbs_gdf.to_crs(working_crs).buffer(1).to_crs('EPSG:4326')

clipbox = box(*tenb_edges.total_bounds)

kerbs_buffered_gdf = gpd.clip(kerbs_buffered_gdf,clipbox)
crossings_gdf = gpd.clip(crossings_gdf,clipbox)
sidewalks_gdf = gpd.clip(sidewalks_gdf,clipbox)


crossings_extra_score = []


for index,crossing_row in crossings_gdf.iterrows():

    additional_score = 0


    for index2,kerb_row in kerbs_buffered_gdf.iterrows():
        # print(row['final_score'],row2['final_score'])

        if not kerb_row.geometry.disjoint(crossing_row.geometry):
            additional_score += kerb_row['final_score']

    crossings_extra_score.append(additional_score)


crossings_gdf['final_score'] += crossings_extra_score

lines_gdf = pd.concat([sidewalks_gdf,crossings_gdf])

tenb_edges_joined = tenb_edges.reset_index().set_index('osmid').join(lines_gdf['final_score']).reset_index().set_index(['u','v','key']).drop(columns=['index'])



def signal_change(entry):
    if entry < -1.2:
        return -entry
    else:
        return entry
    

if routing_elevation:
    # elevation part:
    G = ox.utils_graph.graph_from_gdfs(tenb_nodes, tenb_edges_joined)

    G = ox.elevation.add_node_elevations_raster(G,'elevation_data/cwb_dtm.tif')
    G = ox.elevation.add_edge_grades(G, add_absolute=True)

    tenb_nodes2, tenb_edges2 = ox.utils_graph.graph_to_gdfs(G)

    # according to NBR ABNT 9050 the max allowed ramp is 12.5% slope, so there's no meaning in a lower weight for too sloped descents

    tenb_edges2['corrected_grade'] = tenb_edges2['grade'].apply(signal_change)

    tenb_edges2['beta_wh_weight'] = (tenb_edges2['length']/(tenb_edges2['final_score']+1)) * (1.0 + tenb_edges2['corrected_grade'])

    # no negative weights
    tenb_edges2['beta_wh_weight'] += (min(tenb_edges2['beta_wh_weight'])+0.0001)

    tenb_edges2['beta_wh_weight'] = (tenb_edges2['beta_wh_weight'].fillna(round(max(tenb_edges2['beta_wh_weight']))+1))*100


    G_final = ox.utils_graph.graph_from_gdfs(tenb_nodes2, tenb_edges2)

    ox.io.save_graphml(G_final,'routing_graph.graphml')
else:
    tenb_edges_joined['beta_wh_weight'] = tenb_edges_joined['final_score']

    G = ox.utils_graph.graph_from_gdfs(tenb_nodes, tenb_edges_joined)
    ox.io.save_graphml(G,'osmnx_routing/routing_graph.graphml')
    tenb_edges_joined.to_file('osmnx_routing/sample_routing.geojson')








