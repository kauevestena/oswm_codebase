from constants import *
from functions import *
import re


homepage_as_str = file_as_string(node_home_path)

readme_as_str = file_as_string(readme_path)

# https://kauevestena.github.io

files_dict = {
    'homepage' : homepage_as_str,
    'readme' : readme_as_str,
}

repl_filepaths_dict = {
    'homepage' : node_home_path,
    'readme' : readme_path,
}


# REPLACEMENTS BETWEEN TWO SPECIFIC STRINGS:

quads_for_replace_between = [
    # [begin_of_string,end_of_string,new_middle,file_as_string]
    ['https://','.github.io',USERNAME,files_dict['homepage']],
    ['<CITYNAME>','<CITYNAME>',CITY_NAME,files_dict['readme']],
    ['<!--CITYNAME INSERTION-->','<!--CITYNAME INSERTION-->',CITY_NAME,files_dict['homepage']],

    # the dependent ones, which
    [user_homepage,'/',REPO_NAME,files_dict['homepage']]
]

for quad in quads_for_replace_between:
    # firstly, finding matches:
    for match in find_between_strings(homepage_as_str,quad[0],quad[1],exclusions=['buttons']):

        original_str = f'{quad[0]}{match}{quad[1]}'
        new_str      = f'{quad[0]}{quad[2]}{quad[1]}'

        quad[3] = quad[3].replace(original_str,new_str)

triads_for_simple_replacements = [
    # always: [ORIGINAL STRING, NEW STRING, FILE AS STRING]
]
    
for triad in triads_for_simple_replacements:
    triad[2] = triad[2].replace(triad[0],triad[1])

# commiting changes:
for entry in files_dict:
    str_to_file(files_dict[entry],repl_filepaths_dict[entry])


# # first, simple replacements:
# print(find_between_strings(homepage_as_str,begin_str,end_str,exclusions=['buttons']))

# replace_at_html(node_home_path,'kauevestena.github.io')
