# First metadata generation after checkout

Use this guide after checking out an `oswm_codebase` revision that contains the
metadata generator, or after updating a node's pinned `oswm_codebase`
submodule. Run every command from the **node repository root**, not from inside
`oswm_codebase/`.

## 1. Confirm the node and submodule

```bash
git submodule update --init oswm_codebase
git -C oswm_codebase status --short --branch
test -f config.py
test -d data
```

For reproducible deployment, the node should ultimately commit the tested
`oswm_codebase` gitlink rather than depend on an unrecorded local branch.

## 2. Configure metadata localisation

The metadata generator automatically publishes records in English (`METADATA_LANGUAGE = "en"`)
and determines the node's timezone (`METADATA_TIMEZONE`) from `MID_LAT` and `MID_LGT`
(or `BOUNDING_BOX` center coordinates) using `timezonefinder`.

If needed, an explicit timezone override can be defined in the node's `config.py`:

```python
METADATA_TIMEZONE = "America/Sao_Paulo"  # Optional override
```


Existing node identity settings (`CITY_NAME`, `USERNAME`, and `REPO_NAME`) are
used to construct titles, responsible-party entries, repository links, and
GitHub Pages URLs.

## 3. Generate metadata only

This is the safest first run. It creates or refreshes the sibling `metadata/`
tree and does not modify `data/`:

```bash
python oswm_codebase/metadata/metadata_generation.py
python oswm_codebase/metadata/metadata_generation.py \
  --validate-only --verify-checksums
```

Expected outputs include:

```text
metadata/index.json
metadata/<data-folder>/index.json
metadata/<data-folder>/<complete-data-filename>.metadata.json
```

The number of records depends on the node. One catalogue/collection record is
created for every directory under `data/`, and one sidecar is created for every
non-`index.json` data file. Existing generated records are deterministic;
unknown or manually managed JSON files are preserved.

## 4. Refresh the user-facing API and Data Hub

After metadata validation succeeds, regenerate discovery pages so users see
the **Metadata** tab and **View Metadata** links:

```bash
python oswm_codebase/datahub/API/generate_api.py
python oswm_codebase/datahub/datahub_index_generator.py
```

The API generator also refreshes the existing `data/**/index.json` folder
manifests. It does not move or rewrite the actual GeoParquet, GeoJSON, PMTiles,
VRT, or other data products. Review those manifest diffs before committing.

## Alternative: run the daily cycle

The normal daily runner already executes metadata generation before the API
and Data Hub generators, including its no-OSM-change path:

```bash
sh oswm_codebase/runners/daily.sh
```

Use this route when the node is ready for a complete update. Unlike the
metadata-only command, the daily cycle may contact external services and
regenerate many data, quality, routing, hazard, dashboard, and Webmap outputs.
It is therefore slower and has a much broader working-tree impact.

## 5. Inspect and stage node outputs

```bash
git status --short
git diff --check
git diff --stat
```

Confirm at minimum that:

- `metadata/index.json` exists and identifies `resource_type` as `catalog`;
- every expected data resource has its mirrored metadata sidecar;
- geographic records have a node extent when boundary information is
  available;
- non-geographic records do not claim alignment with geographic ISO standards;
- `hub/API/index.html` contains the Metadata tab if the API was regenerated;
- no actual dataset below `data/` was unexpectedly changed.

When the diff is correct, a typical node stages the pinned codebase revision
and generated discovery outputs with:

```bash
git add oswm_codebase metadata
git add hub/API/index.html hub/index.html
git add config.py  # only when localisation settings were added or changed
```

If the API generator refreshed `data/**/index.json`, inspect and stage only the
expected manifests. Do not use a broad staging command until the complete node
diff has been reviewed.
