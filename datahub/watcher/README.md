# OSWM Watcher

The watcher is an **update watchdog** for the OSWM data pipeline. Its single responsibility is answering:

> *"Has the underlying OSM data changed since the last time we ran the pipeline?"*

If the answer is no, the entire download-and-process pipeline can be skipped, saving time and API bandwidth.

## How it works

1. Reads the last-processed timestamp from `data/last_updated.json` (key `"Data Fetching"`).
2. Reads the study-area boundary from `data/boundaries.geojson` and derives a bounding box.
3. Queries the [OHSOME API](https://api.ohsome.org/) for the count of OSM **contributions** (additions, modifications, deletions) in that area, for each layer, since that timestamp.
4. Returns a per-layer verdict: `True` (needs update), `False` (up to date), or `None` (check inconclusive).

The check is **conservative**: if any layer returns `True` or `None`, the pipeline should run.

## Usage

### As a library

```python
from watcher_lib import needs_update, any_layer_needs_update

# Check all layers
results = needs_update()
# → {'sidewalks': False, 'crossings': True, 'kerbs': False, 'other_footways': False}

# Or just ask: should we run the pipeline at all?
if any_layer_needs_update():
    # run download + processing pipeline
    ...

# Check specific layers only
results = needs_update(layers=["sidewalks", "kerbs"])

# Use a different reference timestamp key
results = needs_update(since_key="Data Pre-Processing")
```

### As a script

```bash
python watcher_lib.py
```

- **Exit 0** — no changes detected, pipeline can be skipped.
- **Exit 1** — at least one layer changed, or a check was inconclusive.

### CI/CD integration

```bash
# Run the full pipeline only when the watcher signals a change
python watcher_lib.py || python getting_data.py
```

## OHSOME filter mapping

Each OSWM layer maps to an [OHSOME filter expression](https://docs.ohsome.org/ohsome-api/stable/filter.html):

| Layer | OHSOME filter |
|---|---|
| `sidewalks` | `footway=sidewalk and type:way` |
| `crossings` | `footway=crossing and type:way` |
| `kerbs` | `(barrier=kerb or kerb=*) and type:node` |
| `other_footways` | `(highway=footway or highway=steps or … or footway=yes) and type:way` |

The `other_footways` filter is derived from `OTHER_FOOTWAY_RULES` in `config.py`.

## Reference timestamp keys

The watcher reads timestamps from `data/last_updated.json`. Available keys (written by the pipeline):

| Key | Written by |
|---|---|
| `Data Fetching` | `getting_data.py` (default for watcher) |
| `Data Pre-Processing` | processing steps |
| `Versioning Data` | `getting_feature_versioning_data.py` |
| `Statistical Charts` | statistics generation |
| `Data Quality Tool` | quality check pipeline |
