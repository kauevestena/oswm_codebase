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
    'color': "black"}

def simple_style(props_dict):
    props = ''

    for prop in props_dict:
        props += f'{prop}: "{props_dict[prop]}",\n'


    return f"""{{
        
        {props}

    """



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

def generate_color_style_for_vectiles(variable_name='p'):
    resulting_styles = {}

    for layername in fields_values_properties:
        resulting_styles[layername] = {}

        for tag_key in fields_values_properties[layername]:
            
            
            resulting_styles[layername][tag_key] = 'color: '

            default = 'black'
            for tag_value in fields_values_properties[layername][tag_key]:
                color = fields_values_properties[layername][tag_key][tag_value]['color']
                if tag_value == '?':
                    default = color
                else:
                    resulting_styles[layername][tag_key] += f' {variable_name} === "{tag_value}" ? "{color}" :'


            resulting_styles[layername][tag_key] += f'"{default}",'

    return resulting_styles

color_styles = generate_color_style_for_vectiles()

def prepare_custom_colorstyle(layername,tag_key):
    style_string = color_styles[layername][tag_key]

    return f"""
        function (properties, zoom) {{
        var p = properties.surface;
        return {{
            {style_string}
    
    """


def create_vectorgrid_slicer(map_reference,layername,style_part=simple_style(sample_style),highlight_style=None,slicer_options=dump_for_javascript(default_slicer_options)+'promoteId:"id",',normal_weight=3,highlight_weight=12):


    layer_varname = f'vectorGrid_{layername}'

    layer_call = f'{layername}_layer'

    highlight_part1 = ''
    highlight_part2 = ''


    if highlight_style:
        highlight_part1 = f"""
        .on('mouseover', function (e) {{

                            var properties = e.layer.properties;



                            var popup = L.popup()

                            popup.setContent(properties.surface).setLatLng(e.latlng).openOn({map_reference});


                            p = properties.surface;

                            var style = {{
                                {highlight_style}
                                weight: {highlight_weight}
                            }};
                            lastHoveredFeatureId = properties.id;

                            {layer_varname}.setFeatureStyle(lastHoveredFeatureId, style);
                        }}
                        )
        """
        highlight_part2 = f"""
                            {layer_varname}.on('mouseout', function (e) {{
                        if (lastHoveredFeatureId) {{
                            {layer_varname}.resetFeatureStyle(lastHoveredFeatureId);
                            //{map_reference}.closePopup();
                            // L.closePopup();
                        }}
                    }})
        
        """

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

                                weight: {normal_weight},
                            }},

                            }},

                            {slicer_options}

                            getFeatureId: function (f) {{
                                return f.properties.id;
                            }}
                        }}




                    )

                        {highlight_part1}
                        
                        .addTo({map_reference});

                        {highlight_part2}


                    </script>
            """
    
    return as_txt