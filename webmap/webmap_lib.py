import sys
sys.path.append('oswm_codebase')
from functions import *

# mapping geometry types to maplibre style
map_geom_type_mapping = {
    'Polygon':'fill',
    'LineString':'line',
    'Point':'circle',
    'MultiPolygon':'fill',
    'MultiLineString':'line',
    'MultiPoint':'circle'
    }
layertypes_dict = { k: map_geom_type_mapping[v] for k,v in all_layers_geom_types.items() }

def get_sources(terrain_url=None,only_urls=False):
    ret = {}
    ret['sources'] = {}
    
    for layername in paths_dict['map_layers']:
        ret[f'{layername}_url'] = f'{node_homepage_url}data/tiles/{layername}.pmtiles'
        
        ret['sources'][f'oswm_pmtiles_{layername}'] = {
            "type": "vector",
            "url": f"pmtiles://{ret[f'{layername}_url']}",
            "promoteId":"id",
            "attribution": '© <a href="https://openstreetmap.org">OpenStreetMap Contributors</a>'}
        
    ret['boundaries_url'] = f'{node_homepage_url}data/boundaries.geojson'


    # basemap:
    ret['sources']['osm'] = {
        "type": "raster",
        "tiles": [BASEMAP_URL],
    }

    # boundaries:
    ret['sources']['boundaries'] = {
        "type": "geojson",
        "data": ret['boundaries_url']
    }
    
    if terrain_url:
        # # # terrain:
        ret['sources']['terrain'] = {
            "type": "raster-dem",
            "url": terrain_url,
            "tileSize": 256
        }
    
    if only_urls:
        del ret['sources']
        return ret
    else:
        return ret