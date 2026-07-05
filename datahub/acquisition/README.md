# OSWM Data Acquisition

This is a submodule aimed for getting projects on platforms with Project Managing capabilities, aimed on organized acquisition or validation of data!

Currently 3 services are meant to be supported:
- HOT Tasking Manager and its flavours (Teach OSM, Open Sidewalks...)
- Pic4Review (almost discontinued — graceful offline handling)
- MapRoulette

## How it works

1. Reads the node's bounding box from `data/boundaries/polygon.geojson` (falls back to `BOUNDING_BOX` in `config.py`).
2. Queries each supported service instance for each keyword (first N from `SEARCH_KEYWORDS`, default N=4 via `DEFAULT_ACQ_KEYWORDS_COUNT` in `constants.py`).
3. Deduplicates results across keywords (same project found by multiple keywords gets merged).
4. Post-filters results against the node's polygon geometry (keeps projects without geometry info).
5. Writes `hub/acquisition/results.json` (structured index) and `hub/acquisition/index.html` (interactive dashboard).

## Usage

### As a script

```bash
python generate_acquisition.py              # full run (default 4 keywords)
python generate_acquisition.py --keywords 6 # use first 6 keywords
python generate_acquisition.py --dry-run    # print API URLs, skip HTTP requests
```

### Key files

| File | Purpose |
|---|---|
| `acq_lib.py` | Constants (keywords, services) and query/parse functions |
| `generate_acquisition.py` | Runner script: collects, deduplicates, filters, writes outputs |

## Output files

| Output | Description |
|---|---|
| `hub/acquisition/results.json` | JSON index of all discovered projects |
| `hub/acquisition/index.html` | Interactive dashboard with search, filters, and service status |

## Service API endpoints

| Service | API endpoint used |
|---|---|
| Tasking Manager | `GET /api/v2/projects/?textSearch={kw}&bbox={bbox}` |
| MapRoulette | `GET /api/v2/challenges/extendedFind?bb={bbox}&cs={kw}` |
| Pic4Review | No search API — online health-check only |

## Architecture

- The relevant constants are available at `oswm_codebase/datahub/acquisition/acq_lib.py`
- This is a submodule that is meant to be a sibling of the API submodule, whose index is generated using `oswm_codebase/datahub/API/generate_api.py`
- Keyword count is configurable via `DEFAULT_ACQ_KEYWORDS_COUNT` in `oswm_codebase/constants.py`