import sys
import os

# Ensure the repository root (one level above this file) is on sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from functions import *


create_folderlist([datahub_root, acquisition_folder, api_folder, watcher_folder])
