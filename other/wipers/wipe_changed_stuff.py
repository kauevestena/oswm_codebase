import sys, shutil
sys.path.append('oswm_codebase')
from functions import *
import os


# remove geojsons, they were replaced by geoparquet
for root, dirs, files in os.walk('data'):
    for file in files:
        if file.endswith('.geojson'):
            os.remove(os.path.join(root, file))

# moving the versioning, they now got a subfolder just for them:
create_folder_if_not_exists(versioning_folderpath)
for filename in os.listdir('data'):
    if filename.endswith('_versioning.json'):
        shutil.move(os.path.join('data', filename), versioning_folderpath)

