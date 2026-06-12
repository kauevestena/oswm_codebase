# OSWM Serverless API

OSWM exposes its processed data as a **static, serverless API** hosted on GitHub Pages. There is no backend — every "endpoint" is a fixed HTTPS URL that returns a static file. Any HTTP `GET` request works: browser `fetch()`, Python `requests`, GDAL, a PMTiles client, etc.

**No authentication. No rate limits beyond GitHub Pages defaults. CORS is open.**

---

## Base URL

```
https://kauevestena.github.io/opensidewalkmap_beta/
```

All paths below are relative to this base URL.

---

## Boundaries & Configuration

| URL path | Format | Description |
|---|---|---|
| `data/boundaries.geojson` | GeoJSON | Polygon(s) of the covered study area |
| `data/boundary_infos.json` | JSON | Metadata about the covered area (name, source, etc.) |
| `data/last_updated.json` | JSON | Timestamp of the last data refresh |
| `webmap_params.json` | JSON | Full webmap configuration: bounding box, center, zoom, layer URLs, and all MapLibre GL styles |
| `data/data_updating.html` | HTML | Human-readable page showing update status |

---

## Pedestrian Data Tiles

Vector tile files in [PMTiles](https://protomaps.com/pmtiles) format. Requires a PMTiles-capable client (e.g. MapLibre GL + `pmtiles.js`, GDAL ≥ 3.6, or the `pmtiles` CLI).

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

## Data Versioning / Age Tracking

JSON files tracking the edit history and age of each feature layer.

| URL path | Format | Layer |
|---|---|---|
| `data/versioning/sidewalks_versioning.json` | JSON | Sidewalks |
| `data/versioning/crossings_versioning.json` | JSON | Crossings |
| `data/versioning/kerbs_versioning.json` | JSON | Kerbs |
| `data/versioning/other_footways_versioning.json` | JSON | Other footways (stairways, main/potential/informal footways, pedestrian areas) |

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

boundary = requests.get(BASE + "data/boundaries.geojson").json()
infos    = requests.get(BASE + "data/boundary_infos.json").json()
```

### Fetch a tile layer (JavaScript / MapLibre GL)

```js
import { PMTiles, leafletRasterLayer } from "pmtiles";

const tilesBase = "https://kauevestena.github.io/opensidewalkmap_beta/data/tiles/";

// Add to a MapLibre map source:
map.addSource("sidewalks", {
  type: "vector",
  url: `pmtiles://${tilesBase}sidewalks.pmtiles`,
});
```

### Open with GDAL/OGR

```bash
ogrinfo /vsicurl/https://kauevestena.github.io/opensidewalkmap_beta/data/vrts/data.vrt
```

---

## Notes

- All responses are static files served by GitHub Pages; there is no query-string filtering or server-side logic.
- PMTiles tiles can be read byte-range–efficiently without downloading the full file.
- The data is refreshed periodically; check `data/last_updated.json` for the current timestamp.
