import sys
sys.path.append('oswm_codebase')
from functions import *
# from constants import *

sidewalks_gdf = gpd.read_file(sidewalks_path_raw)
crossings_gdf = gpd.read_file(crossings_path_raw)
kerbs_gdf = gpd.read_file(kerbs_path_raw)

gdf_dict = {'sidewalks':sidewalks_gdf,'crossings':crossings_gdf,'kerbs':kerbs_gdf}

sidewalks_columns = print_relevant_columnamesV2(sidewalks_gdf)
record_to_json('sidewalks',sidewalks_columns,feat_keys_path)
crossings_columns = print_relevant_columnamesV2(crossings_gdf)
record_to_json('crossings',crossings_columns,feat_keys_path)
kerbs_columns = print_relevant_columnamesV2(kerbs_gdf)
record_to_json('kerbs',kerbs_columns,feat_keys_path)

columns_dict = {'sidewalks':sidewalks_columns,'crossings':crossings_columns,'kerbs':kerbs_columns}

unique_values_dict = {}

for category in columns_dict:
    unique_values_dict[category] = {}
    for osmkey in columns_dict[category]:
        unique_values_dict[category][osmkey] = list(gdf_dict[category][osmkey].unique())

dump_json(unique_values_dict,unique_values_path)

valid_tag_values = {}

for category in fields_values_properties:
    valid_tag_values[category] = {}
    for osmkey in fields_values_properties[category]:
        # excluding musthave keys that are real numbers, the rules must be applied in another fashion
        if osmkey not in ('width','incline','incline:across'):
            valid_tag_values[category][osmkey] = []

            for valid_value in fields_values_properties[category][osmkey]:
                if valid_value:
                    if valid_value not in ('?'):
                        valid_tag_values[category][osmkey].append(valid_value)


dump_json(valid_tag_values,valid_values_path)