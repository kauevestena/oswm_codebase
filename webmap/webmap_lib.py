import sys
sys.path.append('oswm_codebase')
from functions import *
from copy import deepcopy

MAP_DATA_LAYERS = [l for l in paths_dict['map_layers']]

# mapping geometry types to maplibre style
map_geom_type_mapping = {
    'Polygon':'fill',
    'LineString':'line',
    'Point':'circle',
    'MultiPolygon':'fill',
    'MultiLineString':'line',
    'MultiPoint':'circle'
    }

# types for each layer:
layertypes_dict = { k: map_geom_type_mapping[v] for k,v in all_layers_geom_types.items() }


# the layers by type:
line_layers = [l for l in MAP_DATA_LAYERS if layertypes_dict[l] == 'line']
fill_layers = [l for l in MAP_DATA_LAYERS if layertypes_dict[l] == 'fill']
circle_layers = [l for l in MAP_DATA_LAYERS if layertypes_dict[l] == 'circle']

layer_type_groups = {
    # the order in this dict determines the order in the webmap:
    'fill':fill_layers,
    'line':line_layers,
    'circle':circle_layers
}


# immutable layers, among different styles:
immutable_layers=  [{
            "id": "osm-baselayer",
            "source": "osm",
            "type": "raster"
        },
        {
            "id": "boundaries",
            "type": "line",
            "source": "boundaries",
            "paint": {
                "line-color": "black",
                "line-opacity": 0.3
            }
        }]

# base dict for a map style:
mapstyle_basedict = {
    "version": 8,
    "sources": {},
    "layers": []
}

# base_dicts for each layer type:
            # "id": "pedestrian_areas",
            # "source": "oswm_pmtiles_pedestrian_areas",
            # "source-layer": "pedestrian_areas",
            # "type": "fill",
            # "paint": {
            #     "fill-color": "gray",
            #     "fill-opacity": 0.5
            # }

layertypes_basedict = {
    'line':{
        "id": "",
        "source": "",
        "source-layer": "",
        "type": "line",
        "paint": {
            "line-color": "steelblue",
            "line-width": 3
        }
    },
    'fill':{
        "id": "",
        "source": "",
        "source-layer": "",
        "type": "fill",
        "paint": {
            "fill-color": "steelblue",
            "fill-opacity": 0.5
        }
    },
    'circle':{
        "id": "",
        "source": "",
        "source-layer": "",
        "type": "circle",
        "minzoom": 16,
        "paint": {
            "circle-color": "steelblue",
            "circle-opacity": 0.8
        }
    }
}

color_attribute = {
    'fill':'fill-color',
    'line':'line-color',
    'circle':'circle-color'
}

def get_sources(terrain_url=None,only_urls=False):
    ret = {}
    ret['sources'] = {}
    
    for layername in paths_dict['map_layers']:
        ret[f'{layername}_url'] = f'{node_homepage_url}data/tiles/{layername}.pmtiles'
        
        ret['sources'][f'oswm_pmtiles_{layername}'] = {
            "type": "vector",
            "url": f"pmtiles://{ret[f'{layername}_url']}",
            "promoteId":"id",
            "attribution": r'© <a href="https://openstreetmap.org">OpenStreetMap Contributors</a>'}
        
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
    
MAP_SOURCES = get_sources()['sources']
    
def sort_keys_by_order(input_dict, order_list):
    ordered_keys = []
    remaining_keys = list(input_dict.keys())
    
    for order in order_list:
        for key in list(remaining_keys):
            if input_dict[key] == order:
                ordered_keys.append(key)
                remaining_keys.remove(key)
                
    ordered_keys.extend(remaining_keys)
    
    return ordered_keys

ordered_map_layers = sort_keys_by_order(layertypes_dict, layer_type_groups.keys())

def create_base_style(sources=MAP_SOURCES,name='Footway Categories'):
    
    style_dict = deepcopy(mapstyle_basedict)
    
    style_dict['sources'] = sources
    
    style_dict['name'] = name
    
    style_dict['layers'].extend(deepcopy(immutable_layers))
    
    for layername in ordered_map_layers:
        layer_type = layertypes_dict[layername]
        
        layer_dict = deepcopy(layertypes_basedict[layer_type])
        
        # now we can set the id and source:
        layer_dict['id'] = layername
        layer_dict['source'] = f'oswm_pmtiles_{layername}'
        layer_dict['source-layer'] = layername
        
                
        style_dict['layers'].append(layer_dict)
        
    
    
    return style_dict

def create_simple_map_style(name,color_schema,sources=MAP_SOURCES):
    style_dict = deepcopy(mapstyle_basedict)
    
    style_dict['sources'] = sources
    
    style_dict['name'] = name
    
    style_dict['layers'].extend(deepcopy(immutable_layers))
    
    for layername in ordered_map_layers:
        layer_type = layertypes_dict[layername]
        
        layer_dict = deepcopy(layertypes_basedict[layer_type])
        
        # now we can set the id and source:
        layer_dict['id'] = layername
        layer_dict['source'] = f'oswm_pmtiles_{layername}'
        layer_dict['source-layer'] = layername
        
        layer_type = layertypes_dict[layername]
        
        layer_dict['paint'][color_attribute[layer_type]] = color_schema
        
                
        style_dict['layers'].append(layer_dict)
        
    
    return style_dict

def get_color_dict(columnname):
    colordict = {}
    
    base_dict = fields_values_properties['sidewalks'][columnname]
    
    for key in base_dict:
        colordict[key] = base_dict[key]['color']
        
    return colordict

def create_maplibre_color_schema(attribute_dict,attribute_name, else_color="black"):
    schema = ["case"]
    for key, value in attribute_dict.items():
        schema.extend([
            ["==", ["get", attribute_name], key],
            value
        ])
    schema.append(else_color)
    return schema