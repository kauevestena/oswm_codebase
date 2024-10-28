import sys
from tqdm import tqdm
from dq_funcs import *

tags_dict = read_json("quality_check/feature_keys.json")

wiki_absence_dict = {}

for category in tqdm(tags_dict):
    wiki_absence_dict[category] = []
    for osm_key in tqdm(tags_dict[category], desc=category):
        # print("testing ", osm_key)

        if not check_if_wikipage_exists(osm_key):
            print("    ", osm_key, " absent!!")
            wiki_absence_dict[category].append(osm_key)


dump_json(wiki_absence_dict, "quality_check/keys_without_wiki.json")

# to record data aging:
record_datetime("Wiki check for keys")
sleep(0.1)

# generate the "report" of the updating info
gen_updating_infotable_page()
