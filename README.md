# oswm_codebase
This repository holds the code that is used to create the static data for each node of project OpenSidewalkMap or OSWM for short.

OSWM is a decentered and modular project, leveraging OpenStreetMap data for sidewalk data management.

Project's main repository: https://github.com/kauevestena/opensidewalkmap

OSWM organization: https://github.com/opensidewalkmap/


## Local development:

Clone the original node (or other alternatively), then initialize the submodules, most of this codebase is meant to run from the main folder of an OSWM node. :

    git clone https://github.com/kauevestena/opensidewalkmap_beta
    git submodule init
    git submodule update

Then create & setup a virtual enviroment, install requirements from oswm_codebase/requirements.txt

    pip install requirements -r oswm_codebase/requirements.txt


#### If in vscode: 
-Reload Window
-change the checkout to main (it will create a random tag)

You can do the same with other OSWM nodes.
