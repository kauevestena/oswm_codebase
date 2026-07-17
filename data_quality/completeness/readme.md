# Pedestrian Network Completeness Analysis

This module performs a cell-wise spatial analysis of the pedestrian network (footways and sidewalks) compared to the motorized vehicle network (roads). It leverages the **OHSOME API** and mercantile tile grids to calculate completeness ratios across an entire OSWM node at multiple zoom levels (Z12–Z17).

## Methodology

1. **Spatial Grid:** The analysis divides the city boundary into standard Web Mercator tiles for zoom levels 12 through 17.
2. **Length Ratios:** For each tile, it queries OHSOME to sum the length of roads, footways, and sidewalks. It then calculates the ratio of footways-to-roads and sidewalks-to-roads.
3. **Temporal Tracking:** To monitor progress over time, the pipeline queries historical snapshots (spanning back 12 months), allowing for dynamic time-series visualizations.

## Components

*   `completeness_runner.py`: The main orchestration script. It handles timestamp generation, triggers the spatial analysis, manages incremental data updates, and generates the final output files. It supports automated execution via the `--silent` flag.
*   `completeness_lib.py`: The core logic library. Handles the heavy lifting, including mercantile grid bounding box math, OHSOME API batched query logic, exponential backoff retries, and the generation of the standalone MapLibre GL JS map template.

## Execution

The pipeline is designed to be executed monthly via a cron job or manual trigger:

```bash
# Standard interactive execution with progress bars
python oswm_codebase/data_quality/completeness/completeness_runner.py

# Automated background execution (no console output)
python oswm_codebase/data_quality/completeness/completeness_runner.py --silent
```

*Note: A full city-wide run across Z12–Z17 for 13 historical timestamps generates a significant number of API requests and may take several hours to complete depending on the size of the OSWM node bounds.*

## Outputs

The module generates artifacts in the standard OSWM Data Quality output directory (`quality_check/completeness/`):

1.  **`data.json`**: A structured JSON dataset containing the raw nested multi-zoom results and historical timestamp tracking.
2.  **`index.html`**: A standalone, interactive MapLibre GL JS choropleth map. It features an integrated UI that allows users to toggle between "Footways to Roads" and "Sidewalks to Roads" metrics, and scrub through historical timeframes using an interactive slider.