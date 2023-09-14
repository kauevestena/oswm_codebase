import csv, os, re
import bs4
from time import sleep, time
import pandas as pd
from datetime import datetime 
import json, requests
from xml.etree import ElementTree
import geopandas as gpd


"""

    READ/ DUMP STUFF

"""
def read_json(inputpath):
    with open(inputpath) as reader:
        data = reader.read()

    return json.loads(data)
    
def dump_json(inputdict,outputpath,indent=4):
    with open(outputpath,'w+',encoding='utf8') as json_handle:
        json.dump(inputdict,json_handle,indent=indent,ensure_ascii=False)

def file_as_string(inputpath:str):
    if os.path.exists(inputpath):
        with open(inputpath) as reader:
            return reader.read()
    else:
        raise(FileNotFoundError)
    
def str_to_file(inputstr:str,outputpath:str,check_path=False):
    if check_path:
       if not os.path.exists(outputpath):
            raise(FileNotFoundError)


    with open(outputpath,'w+',encoding='utf8') as writer:
        writer.write(inputstr)
        sleep(0.1)

class fileAsStrHandler:

    def __init__(self,inputpath:str):
        self.path = inputpath
        self.content = file_as_string(self.path)

    def simple_replace(self,original_part,new_part=''):
        """default is empty to just remove"""
        self.content = self.content.replace(original_part,new_part)

    def rewrite(self):
        str_to_file(self.content,self.path)
    
    def write_to_another_path(self,outputpath):
        str_to_file(self.content,outputpath)


"""

    TIME STUFF

"""

def formatted_datetime_now():
    now = datetime.now()
    return now.strftime("%d/%m/%Y %H:%M:%S")



def record_datetime(key,json_path='data/last_updated.json'):

    datadict = read_json(json_path)

    datadict[key] = formatted_datetime_now()

    dump_json(datadict,json_path)

    sleep(.1)

def record_to_json(key,obj,json_path):

    datadict = read_json(json_path)

    datadict[key] = obj

    dump_json(datadict,json_path)



"""

    HTML STUFF

"""

FONT_STYLE = f"""

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@500&display=swap" rel="stylesheet"> 


<style>

    {file_as_string('oswm_codebase/assets/styles/font_styles.css')}

</style>

"""

TABLES_STYLE = f"""

<style>
    {file_as_string('oswm_codebase/assets/styles/table_styles.css')}
</style>

"""

def gen_updating_infotable_page(outpath='data/data_updating.html',json_path='data/last_updated.json',node_page_url='https://kauevestena.github.io/opensidewalkmap_beta/'):


    tablepart = ''

    records_dict = read_json(json_path)

    for key in records_dict:
        tablepart += f"""
        <tr><th><b>{key}</b></th><th>{records_dict[key]}</th></tr>
        """

    page_as_txt = f'''
    <!DOCTYPE html>
<html lang="en">
<head>

{FONT_STYLE}

<title>OSWM Updating Info</title>

{TABLES_STYLE}

</head>
<body>

<h1><a href="https://kauevestena.github.io/opensidewalkmap_beta">OSWM</a> Updating Info</h1>

<p> About: OSWM is currently hosted at GitHub Pages, which means that it relies on commits to stay updated!!<br>
if the data is too outdated you may <a href="https://github.com/kauevestena/opensidewalkmap_beta/issues">post an issue</a> or contact me!!</p>

<table>

{tablepart}

</table>


<h1>Download Data:</h1>

<table>

<tr>
  <th>Sidewalks</th>
  <th><a href="https://kauevestena.github.io/opensidewalkmap_beta/data/sidewalks_raw.geojson">Raw</a></th>
  <th><a href="https://kauevestena.github.io/opensidewalkmap_beta/data/sidewalks.geojson">Filtered</a></th>
  <th><a href="https://kauevestena.github.io/opensidewalkmap_beta/data/sidewalks_versioning.json">Versioning</a></th>
</tr>

<tr>
  <th>Crossings</th>
  <th><a href="https://kauevestena.github.io/opensidewalkmap_beta/data/crossings_raw.geojson">Raw</a></th>
  <th><a href="https://kauevestena.github.io/opensidewalkmap_beta/data/crossings.geojson">Filtered</a></th>
  <th><a href="https://kauevestena.github.io/opensidewalkmap_beta/data/crossings_versioning.json">Versioning</a></th>
</tr>

<tr>
  <th>Kerbs</th>
  <th><a href="https://kauevestena.github.io/opensidewalkmap_beta/data/kerbs_raw.geojson">Raw</a></th>
  <th><a href="https://kauevestena.github.io/opensidewalkmap_beta/data/kerbs.geojson">Filtered</a></th>
  <th><a href="https://kauevestena.github.io/opensidewalkmap_beta/data/kerbs_versioning.json">Versioning</a></th>
</tr>



</table>



</body>
</html>    
    '''

    with open(outpath,'w+') as writer:
        writer.write(page_as_txt)


def gen_quality_report_page_and_files(outpath,tabledata,feat_type,category,quality_category,text,occ_type,csvpath,count_page=False):

    pagename_base = f'{quality_category}_{category}'

    csv_url = f"""<h2>  
        
            <a href="https://kauevestena.github.io/opensidewalkmap_beta/quality_check/tables/{pagename_base}.csv"> You can also download the raw .csv table </a>

        </h2>"""

    tablepart = f"""<tr>
    <th><b>OSM ID (link)</b></th>
    <th><b>key</b></th>
    <th><b>value</b></th>
    <th><b>commentary</b></th>
    </tr>"""


    if count_page:
        tablepart = f"""<tr>
                    <th><b>OSM ID (link)</b></th>
                    <th><b>count</b></th>"""

        csv_url = ""

    valid_featcount = 0

    with open(csvpath,'w+') as file:
            writer = csv.writer(file,delimiter=',',quotechar='"')
            writer.writerow(['osm_id','key','value','commentary'])

            for line in tabledata:
                try:
                    line_as_str = ''
                    if line:
                        if len(line)> 2:
                            if not pd.isna(line[2]): 

                                writer.writerow(line)

                                line[0] = return_weblinkV2(str(line[0]),feat_type)
                        
                                line_as_str += "<tr>"
                        
                                for element in line:
                                    line_as_str += f"<td>{str(element)}</td>"
                        
                                line_as_str += "</tr>\n"

                                tablepart += line_as_str

                                valid_featcount += 1
                except:
                    if line:
                        print('skipped',line)


    with open(outpath,'w+') as writer:

        page = f"""

        <!DOCTYPE html>
        <html lang="en">
        <head>

        {FONT_STYLE}

        <title>OSWM DQT {category[0]} {quality_category}</title>

        {TABLES_STYLE}

        </head>
        <body>

        <h1><a href="https://kauevestena.github.io/opensidewalkmap_beta">OSWM</a> Data Quality Tool: {category} {quality_category}</h1>

        <h2>About: {text}</h2>
        <h2>Type: {occ_type}</h2>
        {csv_url}




        <table>

        {tablepart}

        </table>

        


        </table>



        </body>
        </html>   

        """

        writer.write(page)

    return valid_featcount



def find_map_ref(input_htmlpath):
    with open(input_htmlpath) as inf:
        txt = inf.read()
        soup = bs4.BeautifulSoup(txt,features='html5lib')

    refs = soup.find_all(attrs={'class':"folium-map"})

    for found_ref in refs:
        return found_ref['id']




def find_html_name(input_htmlpath,specific_ref,tag_ref='img',specific_tag='src',identifier='id'):

    with open(input_htmlpath) as inf:
        txt = inf.read()
        soup = bs4.BeautifulSoup(txt,features='html5lib')

    refs = soup.find_all(tag_ref)


    for found_ref in refs:
        # if specific_tag in found_ref:

        if found_ref[specific_tag] == specific_ref:
            return found_ref[identifier]
            

def style_changer(in_out_htmlpath,element_key,key='style',original='bottom',new='top',append_t=None):
    with open(in_out_htmlpath) as inf:
        txt = inf.read()
        soup = bs4.BeautifulSoup(txt,features='html5lib')

    style_refs = soup.find_all(key)

    for style_ref in style_refs:
        as_txt = str(style_ref)
        if element_key in as_txt:

            if new:
                new_text = as_txt.replace(original,new)
            else:
                new_text = as_txt

            if append_t:
                new_text += append_t

            break


    with open(in_out_htmlpath,'w+', encoding='utf-8') as writer:
        writer.write(str(soup).replace(as_txt,new_text))

    sleep(0.2)

        
def add_to_page_after_first_tag(html_filepath,element_string,tag_or_txt='<head>',count=1):
    '''
    Quick and dirty way to insert some stuff directly on the webpage 

    Originally intended only for <head>

    beware of tags that repeat! the "count" argument is very important!
    '''


    with open(html_filepath) as reader:
        pag_txt = reader.read()

    replace_text = f'{tag_or_txt} \n{element_string}\n'

    
    with open(html_filepath,'w+') as writer:
        writer.write(pag_txt.replace(tag_or_txt,replace_text,count))

    sleep(.1)

def replace_at_html(html_filepath,original_text,new_text,count=1):
    '''
    Quick and dirty way to replace some stuff directly on the webpage 

    Originally intended only for <head>

    beware of tags that repeat! the "count" argument is very important!
    '''

    if os.path.exists(html_filepath):
        with open(html_filepath) as reader:
            pag_txt = reader.read()

        
        with open(html_filepath,'w+') as writer:
            writer.write(pag_txt.replace(original_text,new_text,count))
    else:
        raise('Error: file not found!!')

    sleep(.1)


# def file_to_str(filepath):
#     if os.path.exists(filepath):
#         with open(filepath) as reader:
#             pag_txt = reader.read()

#         return pag_txt

def find_between_strings(string, start, end,return_unique=True,exclusions:list=None,include_linebreaks=False):
    pattern = f"{start}(.*){end}"
    # print(pattern)
    if include_linebreaks:
        matches =  re.findall(pattern, string,re.DOTALL)
    else:
        matches =  re.findall(pattern, string)

    if return_unique:
        matches = list(set(matches))

    if exclusions:
        matches = [match for match in matches if match not in exclusions]

    return matches


# (geo)Pandas stuff:
def get_score_df(inputdict,category='sidewalks',osm_key='surface',input_field='score_default',output_field_base='score'):

    output_field_name = f'{category}_{osm_key}_{output_field_base}'
    dict = {osm_key:[],output_field_name:[]}

    for val_key in inputdict[category][osm_key]:
        dict[osm_key].append(val_key)
        dict[output_field_name].append(inputdict[category][osm_key][val_key][input_field])

    return  pd.DataFrame(dict), output_field_name


def get_attr_dict(inputdict,category='sidewalks',osm_tag='surface',attr='color'):
    color_dict = {}
    for tag_value in inputdict[category][osm_tag]:
        color_dict[tag_value] = inputdict[category][osm_tag][tag_value][attr]

    return color_dict

def return_weblink_way(string_id):
    return f"<a href=https://www.openstreetmap.org/way/{string_id}>{string_id}</a>"

def return_weblink_node(string_id):
    return f"<a href=https://www.openstreetmap.org/node/{string_id}>{string_id}</a>"

def return_weblinkV2(string_id,featuretype):
    return f"<a href=https://www.openstreetmap.org/{featuretype}/{string_id}>{string_id}</a>"

'''

HISTORY STUFF

'''

def get_feature_history_url(featureid,type='way'):
    return f'https://www.openstreetmap.org/api/0.6/{type}/{featureid}/history'

def parse_datetime_str(inputstr,format='ymdhms'):

    format_dict = {
        'ymdhms' : '%Y-%m-%dT%H:%M:%S',
    }

    return datetime.strptime(inputstr,format_dict[format])


def get_datetime_last_update(featureid,featuretype='way',onlylast=True,return_parsed=True,return_special_tuple=True):

    h_url = get_feature_history_url(featureid,featuretype)

    try:
        response = requests.get(h_url)
    except:
        if onlylast:
            if return_parsed and return_special_tuple:
                return [None]*4 #4 Nones

            return ''
        else:
            return []

    if response.status_code == 200:
        tree = ElementTree.fromstring(response.content)

        element_list = tree.findall(featuretype)

        if element_list:
            date_rec = [element.attrib['timestamp'][:-1] for element in element_list]

            if onlylast:
                if return_parsed:
                    if return_special_tuple:
                        # parsed = datetime.strptime(date_rec[-1],'%Y-%m-%dT%H:%M:%S')
                        parsed = parse_datetime_str(date_rec[-1])
                        return len(date_rec),parsed.day,parsed.month,parsed.year

                    else:
                        # return datetime.strptime(date_rec[-1],'%Y-%m-%dT%H:%M:%S')
                        return parse_datetime_str(date_rec[-1])

                
                else:
                    return date_rec[-1]

            else:
                if return_parsed:
                    return [parse_datetime_str(record) for record in date_rec]

                else:
                    return date_rec


        else:
            if onlylast:
                return ''
            else:
                return []
    
    else:
        print('bad request, check feature id/type')
        if onlylast:
            return ''
        else:
            return []


def get_datetime_last_update_node(featureid):
    # all default options
    return get_datetime_last_update(featureid,featuretype='node')


def print_relevant_columnamesV2(input_df,not_include=('score','geometry','type','id'),outfilepath=None):

    as_list = [column for column in input_df.columns if not any(word in column for word in not_include)]

    # print(*as_list)

    if outfilepath:
        with open(outfilepath,'w+') as writer:
            writer.write(','.join(as_list))

    return as_list


def check_if_wikipage_exists(name,category="Key:",wiki_page='https://wiki.openstreetmap.org/wiki/'):

    url = f'{wiki_page}{category}{name}'

    while True:
        try:
            status = requests.head(url).status_code
            break
        except:
            pass

    return status == 200

"""
    geopandas

"""

def gdf_to_js_file(input_gdf,output_path,output_varname):
    """
        this function converts a geopandas dataframe to a javascript file, was the only thing that worked for vectorGrid module 

        returns the importing to be included in the html file
    """

    input_gdf.to_file(output_path,driver='GeoJSON')

    as_str = f"{output_varname} = "+ file_as_string(output_path)

    str_to_file(as_str,output_path)

    return f'<script type="text/javascript" src="{output_path}"></script>'

def create_length_field(input_gdf,fieldname='length(km)',in_km=True):
    factor = 1
    if in_km:
        factor = 1000

    utm_crs = input_gdf.estimate_utm_crs()
    input_gdf['length(km)'] = input_gdf.to_crs(utm_crs).length/factor

def create_weblink_field(input_gdf,featuretype='LineString',inputfield='id',fieldname='weblink'):
    if featuretype == 'LineString':
        input_gdf[fieldname] = input_gdf[inputfield].astype('string').apply(return_weblink_way)
    if featuretype == 'Point':
        input_gdf[fieldname] = input_gdf[inputfield].astype('string').apply(return_weblink_node)


def create_folder_if_not_exists(folderpath):
    if not os.path.exists(folderpath):
        os.makedirs(folderpath)

def remove_if_exists(pathfile):
    if os.path.exists(pathfile):
        os.remove(pathfile)
