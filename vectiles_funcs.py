'''
 module intended for only the vector tiles-relevant functions
'''
from functions import *
from constants import *

def vectile_base_insertions(filepath):

    layer_imports = ''

    for layername in layernames:
        layer_imports += f'<script type="text/javascript" src="assets/mapdata/{layername}.js"></script>\n\t\t'

    base_insertions_dict ={ 
        "</head>":
        f"""
        <script src="https://unpkg.com/leaflet.vectorgrid@latest/dist/Leaflet.VectorGrid.bundled.js"></script>

        {layer_imports}
        
        </head>
        """

    }

    for insertion_point in base_insertions_dict:
        replace_at_html(filepath, insertion_point, base_insertions_dict[insertion_point])

sample_style = {
    'fillColor': "red",
    'color': "red",
    'weight': 3,
}

def simple_style(props_dict):
    props = ''

    for prop in props_dict:
        props += f'{prop}: "{props_dict[prop]}",\n'


    return f"""{{
        
        {props}

    }}"""



"""
function (properties, zoom) {{
    var p = properties.surface;
    return {{

        color: p === "concrete" ? "blue" : p === "sett" ? "green" : "purple",
        weight: 3
    }},


}}
"""
default_slicer_options = {
    'maxZoom': 22,
    'tolerance': 15,
    'indexMaxZoom': 18,   
    'debug': 0,
    'extent': 4096,
    'indexMaxZoom': 18,
    'interactive': True,
}

def dump_for_javascript(inputdict,additional_string=''):
    as_str = json.dumps(inputdict)

    return as_str.replace('{','').replace('}','').replace('"','').replace(',',',\n')+',\n'+additional_string

def veclayer_options(options_dict):
    options = ''

    for option in options_dict:
        if options_dict[option]:
            options += f'{option}: "{options_dict[option]}",\n'

    return options



def create_vectorgrid_slicer(map_reference,layername,style_part=simple_style(sample_style),slicer_options=dump_for_javascript(default_slicer_options)+'promoteId:"id",'):


    layer_varname = f'vectorGrid_{layername}'

    layer_call = f'{layername}_layer'

    as_txt = f"""
            <script>

            var {layer_varname} = L.vectorGrid.slicer(

                        {layer_call},


                        {{

                            rendererFactory: L.svg.tile,
                            //   rendererFactory: L.canvas.tile,
                            vectorTileLayerStyles: {{
                                sliced:

                                {style_part}
                            }},

                            {slicer_options}

                            getFeatureId: function (f) {{
                                return f.properties.id;
                            }}
                        }}






                    )
                        .on('mouseover', function (e) {{

                            var properties = e.layer.properties;



                            var popup = L.popup()

                            popup.setContent(properties.surface).setLatLng(e.latlng).openOn(map);


                            p = properties.surface;

                            var style = {{
                                color: p === "concrete" ? "blue" : p === "sett" ? "green" : "purple",
                                weight: 12
                            }};
                            lastHoveredFeatureId = properties.id;

                            {layer_varname}.setFeatureStyle(lastHoveredFeatureId, style);
                        }}
                        )
                        .addTo({map_reference});

                    {layer_varname}.on('mouseout', function (e) {{
                        if (lastHoveredFeatureId) {{
                            {layer_varname}.resetFeatureStyle(lastHoveredFeatureId);
                            map.closePopup();
                            // L.closePopup();
                        }}
                    }})
                    </script>
            """
    
    return as_txt