from constants import *
from functions import *
import re


files_obj_dict = {
    'homepage' : fileAsStrHandler(node_home_path),
    'readme' : fileAsStrHandler(readme_path),
}


# REPLACEMENTS BETWEEN TWO SPECIFIC STRINGS:

quads_for_replace_between = [
    # [begin_of_string,end_of_string,new_middle,file_as_string]
    ['https://','.github.io',USERNAME,files_obj_dict['homepage']],
    ['<CITYNAME>','<CITYNAME>',CITY_NAME,files_obj_dict['readme']],
    ['<!--CITYNAME INSERTION-->','<!--CITYNAME INSERTION-->',CITY_NAME,files_obj_dict['homepage']],

    ['.github.io/','/data/data_updating.html',REPO_NAME,files_obj_dict['homepage']]
]

# print(find_between_strings(readme_as_str,'<CITYNAME>','<CITYNAME>'))

for i,quad in enumerate(quads_for_replace_between):
    # firstly, finding matches:
    for match in find_between_strings(quad[3].content,quad[0],quad[1],exclusions=['buttons','opensidewalkmap']):
        if len(match) < 100:
            print(i,'replacing between',quad[0],quad[1],'match: ',match)

        original_str = f'{quad[0]}{match}{quad[1]}'
        new_str      = f'{quad[0]}{quad[2]}{quad[1]}'

        quad[3].simple_replace(original_str,new_str)


triads_for_simple_replacements = [
    # always: [ORIGINAL STRING, NEW STRING, FILE OBJ]
]
    
for triad in triads_for_simple_replacements:
    triad[2].simple_replace(triad[0],triad[1])

# print(readme_as_str)

# commiting changes:
for entry in files_obj_dict:
    files_obj_dict[entry].rewrite()




