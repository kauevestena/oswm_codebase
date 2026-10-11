# Regional PBF acquisition fallback

Full acquisition now tries the configured Overpass endpoints and retries, then
downloads a current Geofabrik `.osm.pbf` snapshot if they all fail. No API key is
required. This applies to both pedestrian layers in `getting_data.py` and the
road network used by current completeness analysis. Existing ohsome incremental
updates still run first when eligible.

The fallback selects the smallest Geofabrik region whose download boundary
covers the entire requested polygon. For Hiroshima's stored boundary and its
completeness bounding box, that region is `chugoku`. A boundary spanning multiple
extracts needs a covering parent region; extracts are not silently stitched or
selected by centroid. Downloads exceeding the configured size limit fail.
If the catalogue omits a region's geometry, the resolver loads its individual
Geofabrik GeoJSON boundary, following covering parent regions. These small
documents are cached for 24 hours; at most 32 missing boundaries are fetched.

## Configuration

Existing nodes inherit these defaults without a `config.py` migration:

```python
PBF_FALLBACK_ENABLED = True
PBF_REGION = "auto"          # Or a Geofabrik ID, e.g. "chugoku"; coverage checked
PBF_CACHE_DIR = ".cache/oswm/pbf"
PBF_MAX_DOWNLOAD_MIB = 1024
PBF_MAX_AGE_HOURS = 72
```

Set `PBF_FALLBACK_ENABLED = False` to retain Overpass-only full acquisition.
The runtime and development dependency locks include `osmium` (pyosmium);
no additional native command-line tools are required.

## Data and failure behavior

- Tag matching uses OSMnx's union semantics. Pyosmium retains referenced nodes,
  ways and multipolygon members; OSMnx's local XML reader supplies the existing
  feature index, tags, WGS84 CRS and geometry classification. Spatial filtering
  retains intersecting features, including crossing ways and enclosing polygons.
  A streaming envelope filter reduces the regional PBF to the AOI before OSMnx
  loads the XML, avoiding a regional XML document in Python memory.
- Missing references, malformed or empty results, unavailable providers,
  excessive download size/time and stale snapshots fail acquisition. They do
  not become successful empty layers. Existing raw layers and the acquisition
  timestamp are unchanged when all providers fail before writing.
- A PBF needs its `osmosis_replication_timestamp`. The full-fetch path rejects
  snapshots older than the last successful acquisition, and records that cutoff
  as `Data Fetching` rather than using the download time. Snapshots older than
  72 hours or with a future cutoff are also rejected by default.
- Downloads stream into temporary files. Cache replacement happens only after
  the header passes validation. Reuse within 24 hours checks SHA-256 and snapshot
  freshness. The cache is outside generated data, survives local rebuild resets,
  and is not committed. Ephemeral runners start without it unless separately
  configured to persist this directory.
- `data/updates/acquisition.json` records the provider, region, source URL,
  snapshot cutoff, acquisition time, checksum and cache usage. Completeness roads
  record their source in `roads_for_completeness.parquet.source.json` beside the
  existing road cache. Overpass acquisitions replace these reports with their
  own provider attribution.

This fallback supplies a current snapshot. Historical completeness, contributor
statistics, changesets and other history-dependent ohsome work are unchanged.
It also does not address the separate Hiroshima runtime-validation errors for
legacy `oswm_codebase/` asset URLs.

## Verification

`python -m pytest -q tests/test_pbf_acquisition.py` builds real binary PBF fixtures
and tests OSMnx-compatible geometry, complete references, region coverage,
freshness, bounded downloads, cache integrity, provider ordering, and both
acquisition entry points. These tests need no network access.

Provider and parser references:

- [Geofabrik region catalogue](https://download.geofabrik.de/index-v1.json)
- [Chūgoku extract](https://download.geofabrik.de/asia/japan/chugoku.html)
- [OSMnx features_from_xml](https://osmnx.readthedocs.io/en/stable/user-reference.html#osmnx.features.features_from_xml)
- [Pyosmium writing data and references](https://docs.osmcode.org/pyosmium/latest/user_manual/06-Writing-Data/)
