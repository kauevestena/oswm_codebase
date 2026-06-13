import sys, shutil

sys.path.append("oswm_codebase")
from functions import *
import os


# remove old top-level geojson leftovers; nested geojson files can be products
for filename in os.listdir(data_folderpath):
    filepath = os.path.join(data_folderpath, filename)
    if os.path.isfile(filepath) and filename.endswith(".geojson"):
        os.remove(filepath)

# moving the versioning, they now got a subfolder just for them:
create_folder_if_not_exists(versioning_folderpath)
for filename in os.listdir(data_folderpath):
    if filename.endswith("_versioning.json"):
        shutil.move(os.path.join(data_folderpath, filename), versioning_folderpath)
