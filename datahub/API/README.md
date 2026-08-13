# OSWM Serverless API

OSWM exposes its processed data and **ISO-aligned JSON metadata** as a static, serverless API hosted on GitHub Pages. There is no backend — every "endpoint" is a fixed HTTPS URL that returns a static file. Any HTTP `GET` request works: browser `fetch()`, Python `requests`, GDAL, a PMTiles client, etc.

**No authentication. No rate limits beyond GitHub Pages defaults. CORS is open.**

---

## Base URL

```
https://kauevestena.github.io/opensidewalkmap_beta/
```

All paths below are relative to this base URL.

---

## Format-aware Resource Explorer

The generated API page adapts its primary action and usage tabs to each file
format instead of treating every static file like a JSON request:

| Format | Primary action | Usage tabs |
|---|---|---|
| JSON | Preview JSON | JavaScript, Python, cURL |
| CSV | Preview text | JavaScript, Python, cURL |
| GeoJSON | Preview GeoJSON | JavaScript, Python, GDAL/OGR, cURL |
| GeoParquet | Copy the configured spatial-extract command | Python, GDAL/OGR, cURL |
| PMTiles | Inspect archive header and metadata with byte-range requests | JavaScript, GDAL/OGR, cURL |
| VRT | Preview the descriptor | GDAL/OGR, cURL |
| PNG | View the image | cURL |
| OSWM binary graph | Download the graph | JavaScript, Python, cURL |

Non-spatial JSON and CSV resources deliberately do not show a GDAL panel.
GeoParquet examples include schema inspection, full conversion, spatial
extraction, and attribute filtering.

---

## Metadata Catalogue

Every node publishes a metadata catalogue at:

```text
metadata/index.json
```

The `metadata/` tree mirrors `data/` without changing the data layout. Folder
indexes map directly, while data files retain their complete filename and gain
`.metadata.json`:

```text
data/processed/index.json
→ metadata/processed/index.json

data/processed/sidewalks.parquet
→ metadata/processed/sidewalks.parquet.metadata.json
```

Each resource record includes identification, node extent, temporal status,
lineage, quality scope, distribution links, media type, size, and SHA-256. The
interactive API exposes a dedicated **Metadata** tab and a **View Metadata**
link for every indexed data endpoint.

The OSWM JSON profile uses ISO 15836-1 for every record. Geographic and mixed
records additionally align with ISO 19115-1, ISO 19115-2, and ISO 19157-1;
feature resources also use ISO 19110 concepts. It does not claim conformance to
the ISO 19115-3 XML encoding.

---

## Boundaries & Configuration

| URL path | Format | Description |
|---|---|---|
| `data/boundaries/polygon.geojson` | GeoJSON | Polygon(s) of the covered study area |
| `data/boundaries/infos.json` | JSON | Metadata about the covered area (name, source, etc.) |
| `data/updates/registry.json` | JSON | Timestamp of the last data refresh |
| `webmap_params.json` | JSON | Full webmap configuration: bounding box, center, zoom, layer URLs, and all MapLibre GL styles |
| `data/updates/index.html` | HTML | Human-readable page showing update status |

---

## Pedestrian Data Parquet

| URL path | Format | Description |
|---|---|---|
| `data/processed/sidewalks.parquet` | GeoParquet | Processed sidewalks |
| `data/processed/crossings.parquet` | GeoParquet | Processed crossings |
| `data/processed/kerbs.parquet` | GeoParquet | Processed kerbs |
| `data/processed/other_footways.parquet` | GeoParquet | Processed other footways |
| `data/processed/other_footways/*.parquet` | GeoParquet | Processed other-footway sublayers |
| `data/raw/sidewalks.parquet` | GeoParquet | Raw sidewalks |
| `data/raw/crossings.parquet` | GeoParquet | Raw crossings |
| `data/raw/kerbs.parquet` | GeoParquet | Raw kerbs |
| `data/raw/other_footways.parquet` | GeoParquet | Raw other footways |

---

## Pedestrian Data Tiles

Vector tile files in [PMTiles](https://protomaps.com/pmtiles) format. Requires a PMTiles-capable client (e.g. MapLibre GL + `pmtiles.js`, GDAL ≥ 3.8, or the `pmtiles` CLI).

| URL path | Description |
|---|---|
| `data/tiles/sidewalks.pmtiles` | Footways juxtaposed to roads |
| `data/tiles/crossings.pmtiles` | Pedestrian road crossings |
| `data/tiles/kerbs.pmtiles` | Kerb access points at crossings |
| `data/tiles/stairways.pmtiles` | Pathways composed of steps |
| `data/tiles/main_footways.pmtiles` | Paths whose primary purpose is pedestrian movement |
| `data/tiles/potential_footways.pmtiles` | Paths with vague descriptions, potentially walkable |
| `data/tiles/informal_footways.pmtiles` | Paths used informally due to the absence of proper footways |
| `data/tiles/pedestrian_areas.pmtiles` | Areas where pedestrians can move freely |

---

## Accessibility Routing

| URL path | Format | Description |
|---|---|---|
| `data/routing/network.oswmg` | OSWM binary graph | Versioned topology, directional profile costs, and snapping index used by the routing worker |
| `data/routing/network.pmtiles` | PMTiles | Lightweight network geometry used only for MapLibre rendering |
| `data/routing/network.parquet` | GeoParquet | Downloadable routing geometry and directional grades for expert scrutiny |
| `data/routing/profiles.json` | JSON | Routing labels, speeds, profile order, and graph/display contract |
| `data/routing/metadata.json` | JSON | Ruleset provenance, graph checksum, counts, and grade audit |

---

## Data Versioning / Age Tracking

JSON files tracking the edit history and age of each feature layer.

| URL path | Format | Layer |
|---|---|---|
| `data/updates/versioning/sidewalks_versioning.json` | JSON | Sidewalks |
| `data/updates/versioning/crossings_versioning.json` | JSON | Crossings |
| `data/updates/versioning/kerbs_versioning.json` | JSON | Kerbs |
| `data/updates/versioning/other_footways_versioning.json` | JSON | Other footways (stairways, main/potential/informal footways, pedestrian areas) |

---

## VRT Descriptors (GDAL)

[GDAL VRT](https://gdal.org/drivers/vector/vrt.html) descriptors for opening the dataset directly with GDAL/OGR tools.

| URL path | Description |
|---|---|
| `data/vrts/data.vrt` | Filtered/processed data layers |
| `data/vrts/data_raw.vrt` | Raw (unfiltered) data layers |
| `data/vrts/tiles.vrt` | Tile-oriented virtual dataset |

---

## Data Quality

Output of the OSWM quality-check pipeline. Files are available as JSON and CSV.

### Summary files

| URL path | Format | Description |
|---|---|---|
| `quality_check/categories.json` | JSON | QC issue categories |
| `quality_check/feature_keys.json` | JSON | Keys observed per feature type |
| `quality_check/keys_without_wiki.json` | JSON | Tag keys that lack an OSM Wiki page |
| `quality_check/unique_tag_values.json` | JSON | All unique tag values found in the dataset |
| `quality_check/valid_tag_values.json` | JSON | Tag values considered valid by OSWM rules |

### Per-layer reports

Replace `{layer}` with one of: `sidewalks`, `crossings`, `kerbs`, `other_footways`.

| URL pattern | Format | Description |
|---|---|---|
| `quality_check/tables/{layer}/` | CSV | QC report tables per layer |
| `quality_check/json/{layer}/` | JSON | QC report data per layer |

---

## Statistics Specifications

Chart/plot specifications used to generate the statistics dashboard. These describe the expected structure and metadata for each chart.

Replace `{layer}` with one of: `sidewalks`, `crossings`, `kerbs`, `other_footways`, `all_data`.

| URL pattern | Description |
|---|---|
| `statistics_specs/{layer}/` | Chart specification files for that layer |

---

## Usage Examples

### Fetch boundary info (Python)

```python
import requests, json

BASE = "https://kauevestena.github.io/opensidewalkmap_beta/"

boundary = requests.get(BASE + "data/boundaries/polygon.geojson").json()
infos    = requests.get(BASE + "data/boundaries/infos.json").json()
```

### Fetch a tile layer (JavaScript / MapLibre GL)

```js
import { Protocol } from "pmtiles";

const tilesBase = "https://kauevestena.github.io/opensidewalkmap_beta/data/tiles/";
const protocol = new Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);

// Add to a MapLibre map source:
map.addSource("sidewalks", {
  type: "vector",
  url: `pmtiles://${tilesBase}sidewalks.pmtiles`,
});
```

### Inspect and convert a remote GeoParquet file

```bash
QA_URL="https://kauevestena.github.io/opensidewalkmap_beta/data/data_quality/crossings_lacking_kerbs/crossings_lacking_kerbs.parquet"

ogrinfo -ro -al -so "/vsicurl/${QA_URL}"
ogr2ogr -f GeoJSON crossings_lacking_kerbs.geojson "/vsicurl/${QA_URL}"
```

Use exactly one shell-quoting layer around the `/vsicurl/` datasource. A form
such as `'"/vsicurl/https://…"'` passes the double-quote characters to GDAL as
part of the filename and therefore fails even when the remote file exists.

GeoParquet support requires GDAL 3.8+ built with the Parquet/Arrow driver. Check
the installed drivers with `ogrinfo --formats` if a valid URL still cannot be
opened.

### Extract a 1 km downtown square

The template node configures Praça Tiradentes as Curitiba's downtown example.
The box is 1 km × 1 km (approximately 500 m from the centre in each direction)
and is passed in longitude/latitude order through `OGC:CRS84`:

```bash
SIDEWALKS_URL="https://kauevestena.github.io/opensidewalkmap_beta/data/processed/sidewalks.parquet"

ogr2ogr -f GeoJSON \
  -spat -49.276933 -25.434222 -49.266987 -25.425238 \
  -spat_srs OGC:CRS84 \
  sidewalks-downtown-1km.geojson \
  "/vsicurl/${SIDEWALKS_URL}"
```

Nodes can set `API_EXAMPLE_CENTER_LAT`, `API_EXAMPLE_CENTER_LON`,
`API_EXAMPLE_AREA_LABEL`, and `API_EXAMPLE_BBOX_SIZE_M`. Older configs fall
back to the node's map centre and a 1,000 m square.

### Filter by an attribute

```bash
ogr2ogr -f GeoJSON \
  -where "surface = 'asphalt'" \
  sidewalks-asphalt.geojson \
  "/vsicurl/${SIDEWALKS_URL}"
```

### Inspect and convert PMTiles

```bash
PMTILES_URL="https://kauevestena.github.io/opensidewalkmap_beta/data/tiles/sidewalks.pmtiles"

ogrinfo -ro -al -so "/vsicurl/${PMTILES_URL}"
ogr2ogr -f GPKG sidewalks-tiles.gpkg "/vsicurl/${PMTILES_URL}"
```

---

## Notes

- All responses are static files served by GitHub Pages; there is no query-string filtering or server-side logic.
- Spatial and attribute filters in the examples run in GDAL on the client and write a local extract.
- PMTiles tiles can be read byte-range–efficiently without downloading the full file.
- The data is refreshed periodically; check `data/updates/registry.json` for the current timestamp.
