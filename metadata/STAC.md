# Static STAC publishing pilot

OSWM can export its current processed pedestrian layers and analytical routing
network as STAC 1.1.0. Each node hosts `stac/catalog.json`; each selected product
has a Collection and one mutable `current.json` Item. Existing data and detailed
metadata remain at their existing URLs. This is an opt-in exporter, not a search
server or an archive of historical releases.

## Enable one node

From the node root, add these settings to `config.py` after checking the dataset
license for the selected products:

```python
STAC_ENABLED = True
STAC_LICENSES = {"processed": "ODbL-1.0"}
```

`processed` selects sidewalks, crossings, kerbs, other footways, and its
subcategories under `data/processed/other_footways/`. Empty layers are reported
and omitted. Raw extracts and completeness-analysis roads are outside this
pilot. A missing or invalid license selection fails generation.

`routing` selects `data/routing/network.parquet` and its profiles/provenance
metadata. Add its reviewed SPDX license ID to `STAC_LICENSES` to include it.
Review the configured elevation inputs too: a node can use municipal data in
addition to the default DEM. For custom or combined terms, use
`{"id": "other", "url": "https://your-published-license-page"}`. The software
repository's MIT license is never used as a data-license default.

Generate, inspect and validate before publishing:

```bash
python oswm_codebase/metadata/metadata_generation.py
python oswm_codebase/metadata/stac_generation.py
python oswm_codebase/metadata/stac_generation.py --validate-only
git diff --check
git status --short
```

The daily (including no-change), weekly and setup runners call the exporter
with `--if-enabled` after metadata generation and before API discovery. The
records appear in the API page's Metadata tab. Daily/weekly/setup/custom staging
includes `stac/`. A STAC failure makes the runner fail.

The thin-node reusable builder checks out the reviewed core revision ephemerally
and stages `stac/` with the other generated products. Legacy submodule nodes use
the same runner integration. Publish configuration, metadata and catalog records
together with their corresponding data outputs. After deployment, verify public HTTP access and
CORS at the catalog and asset URLs. This PR does not activate or deploy nodes.
Updating the core alone does not enable STAC across the fleet.

Setting `STAC_ENABLED = False` removes this exporter's records on the next runner
execution so that a disabled catalog cannot silently become stale. Unmanaged
STAC files are preserved; collisions with them fail instead of overwriting them.

## Publication semantics

| Field or behavior | Meaning |
|---|---|
| Item `datetime` | Product generation: `Data Pre-Processing` for processed data; routing metadata's `generated_at` for the network |
| `oswm:datetime_semantics` | `product-generation`; not sidewalk observation dates |
| `oswm:source_fetched_at` | Separate data-fetch time, if known and no later than the product; not individual OSM observation time |
| Legacy timestamps | Node timezone: explicit `METADATA_TIMEZONE` or inference from the configured center/bounds |
| `geometry` and `bbox` | WGS84 envelope of actual published GeoParquet geometries, not the administrative boundary |
| Collection extent | Extent of the one current Item; no fabricated historical interval |
| `oswm:metadata_codebase_commit` | Revision generating the detailed metadata, not asserted to be the data-processing revision |
| `oswm:sha256`, `oswm:byte_size` | Asset integrity checked against local bytes and the existing metadata |
| `oswm:feature_count` | Analytical dataset rows; subcategories overlap the aggregate other-footways product |

`oswm:*` are application fields, not claims to implement a community STAC
extension. Linked OSWM metadata retains fuller provenance and quality details.
Missing product dates are errors; the exporter never substitutes file modification
times, wall-clock time, wiki checks or pipeline-success timestamps. Old registry
dates are reported as old dates.

Item IDs and asset URLs describe **current state**. Historical Items require
retained, immutable assets and a separate retention policy. Catalog records and
data should be deployed as one completed publication.

## PMTiles correspondence

Both vector-tile generators record the SHA-256 of their input GeoParquet in
successful generation reports. STAC includes a `visual` asset only when that
checksum matches the current analytical file. The PMTiles' own bytes must also
match their detailed metadata.

Old reports without this provenance are omitted until a tile rebuild. This
handles weekly processing that refreshes GeoParquet independently of tiles.
PMTiles are labeled as a display representation with potentially different
geometry/attributes, rather than an analytical substitute.

## Global catalog from the fleet registry

After the selected node catalog is deployed, generate the global entry point
in the index repository's publication tree:

```bash
python /path/to/oswm_codebase/metadata/stac_fleet.py \
  --registry /path/to/oswm_codebase/fleet/registry.toml \
  --node milan \
  --output stac/catalog.json \
  --public-url https://opensidewalkmap.github.io/stac/catalog.json
```

Supply the actual public URL of the chosen index deployment. Repeat `--node`
for additional deployed nodes. Being registered does not mean STAC is deployed:
selection is explicit, and each selected node must be enabled in the registry
and serve a valid STAC 1.1.0 Catalog before the global file is written. A failed
HTTP request or invalid catalog preserves the existing global file. No token,
cross-repository write or workflow dispatch is involved.

## Validation and pilot evidence

The exporter validates every document against locally stored, unmodified STAC
1.1.0 and GeoJSON schemas, checks local catalog relationships, and verifies asset
checksums before replacing documents. Validation is offline. Regression tests
cover reprojection, geometry columns, empty/point layers, UTC/legacy dates,
stale metadata and tiles, determinism, pruning, CLI execution, staging and
runner failures.

A local pilot used Milan at commit
`77b065ee8f61eac9b78f4b11b082f9f09fe78b9c`, with the processed family selected:

- 9 Collections, 9 Items, 19 STAC documents.
- PySTAC 1.15.2 traversed all 9 Items; repeated generation was byte-identical.
- Schema, relationship and asset-integrity validation passed.
- Items used `2026-09-27T14:53:19Z`, the processing time, rather than later
  maintenance or pipeline-success dates.
- Existing tile reports lacked source checksums; visual assets were omitted.

Only a local checkout was used. Production configuration, workflows and
published data were not changed.
