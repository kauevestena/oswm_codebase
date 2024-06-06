# from constants import *
from functions import *
from shutil import rmtree, copytree, copy

"""
script reserved for eventual modifications that shall happen on all nodes
"""

# Replacing the workflows from the node to the newest ones:
rmtree(workflows_path,ignore_errors=True)
copytree('./oswm_codebase/workflows',workflows_path)

# copying requirements.txt:
# copy('./oswm_codebase/requirements.txt','./requirements.txt')

# resetting the boundaries:
# remove_if_exists(boundaries_path)
# remove_if_exists(boundaries_md_path)

# TODO: make a full resetting_node.py script