from functions import *
from modules_info import *
import re


files_obj_dict = {
    'homepage' : fileAsStrHandler(node_home_path),
    'readme' : fileAsStrHandler(readme_path),
}


# REPLACEMENTS BETWEEN TWO SPECIFIC STRINGS:

fifths_for_replace_between = [
    # [begin_of_string,end_of_string,new_middle,file_as_string,consider linebreaks (generally False)]
    ['https://','.github.io',USERNAME,files_obj_dict['homepage'],False],
    ['<CITYNAME>','<CITYNAME>',CITY_NAME,files_obj_dict['readme'],False],
    ['<!--CITYNAME INSERTION-->','<!--CITYNAME INSERTION-->',CITY_NAME,files_obj_dict['homepage'],False],
    ['.github.io/','/data/data_updating.html',REPO_NAME,files_obj_dict['homepage'],False],
    ['<!--MODULES INSERTION POINT-->','<!--MODULES INSERTION POINT-->',modules_as_str,files_obj_dict['homepage'],True],
]

# print(find_between_strings(readme_as_str,'<CITYNAME>','<CITYNAME>'))

for i,fifth in enumerate(fifths_for_replace_between):
    # firstly, finding matches:
    for match in find_between_strings(fifth[3].content,fifth[0],fifth[1],exclusions=['buttons'],include_linebreaks=fifth[4]):
        if len(match) < 100:
            print(i,'replacing between',fifth[0],fifth[1],'match: ',match)

        original_str = f'{fifth[0]}{match}{fifth[1]}'
        new_str      = f'{fifth[0]}{fifth[2]}{fifth[1]}'

        fifth[3].simple_replace(original_str,new_str)




triads_for_simple_replacements = [
    # always: [ORIGINAL STRING, NEW STRING, FILE OBJ]
    ['https://opensidewalkmap.github.io/oswm_codebase/','https://kauevestena.github.io/oswm_codebase/',files_obj_dict['homepage']], # doing the ugly way, temporarily
]

    
for triad in triads_for_simple_replacements:
    triad[2].simple_replace(triad[0],triad[1])

# print(readme_as_str)

# commiting changes:
for entry in files_obj_dict:
    files_obj_dict[entry].rewrite()




