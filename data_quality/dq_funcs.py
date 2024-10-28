import sys

sys.path.append("oswm_codebase")

from functions import *
import csv

occurrence_per_feature = {k: {} for k in geom_type_dict.keys()}


def add_to_occurrences(category, id):
    if id in occurrence_per_feature[category]:
        occurrence_per_feature[category][id] += 1
    else:
        occurrence_per_feature[category][id] = 1
