# oswm_codebase
This repository holds the code that is used to create the static data for each node of project OpenSidewalkMap or OSWM for short.

OSWM is a decentered and modular project, leveraging OpenStreetMap data for sidewalk data management.

Project's main repository: https://github.com/kauevestena/opensidewalkmap

OSWM organization: https://github.com/opensidewalkmap/


## Local development:

use local_setup.sh

## Accessibility-aware routing

The static routing module supports shortest-distance, wheelchair,
blind/low-vision and elderly profiles. Profile judgments are maintained as
plain Python dictionaries and precomputed during node generation. See
[`routing/README.md`](routing/README.md) for the architecture, slope-source
hierarchy and calibration workflow.
