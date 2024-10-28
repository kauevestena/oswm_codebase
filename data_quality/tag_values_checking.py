import sys

sys.path.append("oswm_codebase")
from functions import *

gdf_dict = get_gdfs_dict(raw_data=True)
columns_dict = read_json(feat_keys_path)

unique_values_dict = {}

for category in columns_dict:
    unique_values_dict[category] = {}
    for osmkey in columns_dict[category]:
        unique_values_dict[category][osmkey] = list(
            gdf_dict[category][osmkey].dropna().unique()
        )

dump_json(unique_values_dict, unique_values_path)

valid_tag_values = {}

for category in fields_values_properties:
    valid_tag_values[category] = {}
    for osmkey in fields_values_properties[category]:
        # excluding musthave keys that are real numbers, the rules must be applied in another fashion
        if osmkey not in ("width", "incline", "incline:across"):
            valid_tag_values[category][osmkey] = []

            for valid_value in fields_values_properties[category][osmkey]:
                if valid_value:
                    if valid_value not in ("?"):
                        valid_tag_values[category][osmkey].append(valid_value)


dump_json(valid_tag_values, valid_values_path)
