import os
import sys
import json

# Ensure parent `datahub` directory is on sys.path so `dh_lib` can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dh_lib import *

# Ensure standard libraries are available
import urllib.parse

# List of API Endpoints
endpoints_config = [
    {
        "category": "API Index",
        "path": "data/index.json",
        "format": "JSON",
        "description": "Returns the list of all available directories and files in this serverless API, including descriptions of what they contain.",
        "playground": True
    },
    {
        "category": "Boundaries & Config",
        "path": "data/boundaries/polygon.geojson",
        "format": "GeoJSON",
        "description": "Polygon geometry of the study/mapping area boundaries (study boundaries).",
        "playground": True
    },
    {
        "category": "Boundaries & Config",
        "path": "data/boundaries/infos.json",
        "format": "JSON",
        "description": "Metadata properties of the study area (name, source, importance, bounds, etc.).",
        "playground": True
    },
    {
        "category": "Boundaries & Config",
        "path": "data/updates/registry.json",
        "format": "JSON",
        "description": "Timestamps recording when different steps of the pipeline (data fetching, filtering, stats, quality compiling, etc.) were last successfully executed.",
        "playground": True
    },
    {
        "category": "Boundaries & Config",
        "path": "webmap_params.json",
        "format": "JSON",
        "description": "Full configuration for the webmap, including center coordinates, initial zoom level, layers, MapLibre GL styles, and configurations.",
        "playground": True
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/processed/sidewalks.parquet",
        "format": "GeoParquet",
        "description": "Processed and filtered sidewalks in GeoParquet format. Juxtaposed to roads.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/processed/crossings.parquet",
        "format": "GeoParquet",
        "description": "Processed pedestrian road crossings in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/processed/kerbs.parquet",
        "format": "GeoParquet",
        "description": "Processed kerb access points at crossings in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/processed/other_footways.parquet",
        "format": "GeoParquet",
        "description": "Processed other footway features in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/processed/other_footways/stairways.parquet",
        "format": "GeoParquet",
        "description": "Processed stairways sublayer (pathways composed of steps) in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/processed/other_footways/main_footways.parquet",
        "format": "GeoParquet",
        "description": "Processed main footways sublayer (primarily for pedestrian transit) in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/processed/other_footways/potential_footways.parquet",
        "format": "GeoParquet",
        "description": "Processed potential footways sublayer (vague or secondary paths) in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/processed/other_footways/informal_footways.parquet",
        "format": "GeoParquet",
        "description": "Processed informal footways sublayer (paths created/used informally) in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/processed/other_footways/pedestrian_areas.parquet",
        "format": "GeoParquet",
        "description": "Processed pedestrian areas sublayer (polygons where pedestrians move freely) in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/raw/sidewalks.parquet",
        "format": "GeoParquet",
        "description": "Raw sidewalks dataset directly from OSM (unfiltered) in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/raw/crossings.parquet",
        "format": "GeoParquet",
        "description": "Raw crossings dataset directly from OSM (unfiltered) in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/raw/kerbs.parquet",
        "format": "GeoParquet",
        "description": "Raw kerbs dataset directly from OSM (unfiltered) in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Pedestrian Data (Parquet)",
        "path": "data/raw/other_footways.parquet",
        "format": "GeoParquet",
        "description": "Raw other footways dataset directly from OSM (unfiltered) in GeoParquet format.",
        "playground": False
    },
    {
        "category": "Vector Tiles (PMTiles)",
        "path": "data/tiles/sidewalks.pmtiles",
        "format": "PMTiles",
        "description": "Vector tile package containing processed sidewalks for web rendering.",
        "playground": False
    },
    {
        "category": "Vector Tiles (PMTiles)",
        "path": "data/tiles/crossings.pmtiles",
        "format": "PMTiles",
        "description": "Vector tile package containing processed crossings.",
        "playground": False
    },
    {
        "category": "Vector Tiles (PMTiles)",
        "path": "data/tiles/kerbs.pmtiles",
        "format": "PMTiles",
        "description": "Vector tile package containing processed kerbs.",
        "playground": False
    },
    {
        "category": "Vector Tiles (PMTiles)",
        "path": "data/tiles/stairways.pmtiles",
        "format": "PMTiles",
        "description": "Vector tile package containing stairways.",
        "playground": False
    },
    {
        "category": "Vector Tiles (PMTiles)",
        "path": "data/tiles/main_footways.pmtiles",
        "format": "PMTiles",
        "description": "Vector tile package containing main footways.",
        "playground": False
    },
    {
        "category": "Vector Tiles (PMTiles)",
        "path": "data/tiles/potential_footways.pmtiles",
        "format": "PMTiles",
        "description": "Vector tile package containing potential footways.",
        "playground": False
    },
    {
        "category": "Vector Tiles (PMTiles)",
        "path": "data/tiles/informal_footways.pmtiles",
        "format": "PMTiles",
        "description": "Vector tile package containing informal footways.",
        "playground": False
    },
    {
        "category": "Vector Tiles (PMTiles)",
        "path": "data/tiles/pedestrian_areas.pmtiles",
        "format": "PMTiles",
        "description": "Vector tile package containing pedestrian areas.",
        "playground": False
    },
    {
        "category": "Data Quality Reports",
        "path": "quality_check/categories.json",
        "format": "JSON",
        "description": "List of quality check category descriptions and metadata.",
        "playground": True
    },
    {
        "category": "Data Quality Reports",
        "path": "quality_check/feature_keys.json",
        "format": "JSON",
        "description": "Summary of tag keys present in the database.",
        "playground": True
    },
    {
        "category": "Data Quality Reports",
        "path": "quality_check/keys_without_wiki.json",
        "format": "JSON",
        "description": "List of tag keys missing documentation in the OSM Wiki.",
        "playground": True
    },
    {
        "category": "Data Quality Reports",
        "path": "quality_check/unique_tag_values.json",
        "format": "JSON",
        "description": "Unique tag keys and values found across all downloaded features.",
        "playground": True
    },
    {
        "category": "Data Quality Reports",
        "path": "quality_check/valid_tag_values.json",
        "format": "JSON",
        "description": "Predefined list of OSM tag values considered valid by OSWM quality checks.",
        "playground": True
    },
    {
        "category": "Data Aging & Versioning",
        "path": "data/updates/versioning/sidewalks_versioning.json",
        "format": "JSON",
        "description": "Detailed modification dates, changeset stats, and age metrics for sidewalks.",
        "playground": True
    },
    {
        "category": "Data Aging & Versioning",
        "path": "data/updates/versioning/crossings_versioning.json",
        "format": "JSON",
        "description": "Detailed age tracking metrics for crossing features.",
        "playground": True
    },
    {
        "category": "Data Aging & Versioning",
        "path": "data/updates/versioning/kerbs_versioning.json",
        "format": "JSON",
        "description": "Detailed age tracking metrics for kerb features.",
        "playground": True
    },
    {
        "category": "Data Aging & Versioning",
        "path": "data/updates/versioning/other_footways_versioning.json",
        "format": "JSON",
        "description": "Detailed age tracking metrics for other footways layers.",
        "playground": True
    },
    {
        "category": "GDAL VRT Descriptors",
        "path": "data/vrts/data.vrt",
        "format": "XML/VRT",
        "description": "GDAL Virtual Format file linking all processed parquet files together.",
        "playground": True
    },
    {
        "category": "GDAL VRT Descriptors",
        "path": "data/vrts/data_raw.vrt",
        "format": "XML/VRT",
        "description": "GDAL Virtual Format file linking all raw parquet files together.",
        "playground": True
    },
    {
        "category": "GDAL VRT Descriptors",
        "path": "data/vrts/tiles.vrt",
        "format": "XML/VRT",
        "description": "GDAL Virtual Format file referencing tile-oriented datasets.",
        "playground": True
    },
    {
        "category": "Routing & Demos",
        "path": "data/routing/demo.geojson",
        "format": "GeoJSON",
        "description": "GeoJSON routing network sample containing intersections and road segments for demo routing.",
        "playground": True
    }
]

def generate_data_index():
    """Generates the data/index.json file mapping subfolders to descriptions."""
    print("Generating data/index.json...")
    
    data_idx = {
        "node_name": CITY_NAME,
        "username": USERNAME,
        "repository": REPO_NAME,
        "base_url": node_homepage_url,
        "description": f"Serverless API data index for OSWM node: {CITY_NAME}",
        "folders": {}
    }
    
    folder_meta = {
        "boundaries": {
            "description": "Polygon boundary and metadata about the study area.",
            "path": "data/boundaries"
        },
        "processed": {
            "description": "Cleaned, filtered, and structured pedestrian network layers in GeoParquet format.",
            "path": "data/processed"
        },
        "raw": {
            "description": "Raw, unfiltered pedestrian network datasets downloaded directly from OpenStreetMap.",
            "path": "data/raw"
        },
        "tiles": {
            "description": "Pedestrian network layers packaged as vector tiles in PMTiles format.",
            "path": "data/tiles"
        },
        "updates": {
            "description": "Data update logs, registry status, and historical version tracking.",
            "path": "data/updates"
        },
        "vrts": {
            "description": "GDAL Vector Virtual Dataset (VRT) descriptors for direct GIS integrations.",
            "path": "data/vrts"
        },
        "data_quality": {
            "description": "Spatial parquet layers highlighting topological and tagging inconsistencies.",
            "path": "data/data_quality"
        },
        "routing": {
            "description": "Routing files, network properties, and routing demo data.",
            "path": "data/routing"
        }
    }
    
    for key, meta in folder_meta.items():
        folder_path = os.path.join("data", key)
        files = []
        if os.path.exists(folder_path):
            # Recursively find all files in the directory
            for root, dirs, filenames in os.walk(folder_path):
                for f in filenames:
                    rel_f = os.path.relpath(os.path.join(root, f), folder_path)
                    # Ignore hidden/system files
                    if not f.startswith('.'):
                        files.append(rel_f)
        else:
            # Fallbacks if folder has not been populated yet during fresh setup
            if key == "boundaries":
                files = ["polygon.geojson", "infos.json", "metadata.json"]
            elif key == "processed":
                files = ["sidewalks.parquet", "crossings.parquet", "kerbs.parquet", "other_footways.parquet"]
            elif key == "raw":
                files = ["sidewalks.parquet", "crossings.parquet", "kerbs.parquet", "other_footways.parquet"]
            elif key == "tiles":
                files = ["sidewalks.pmtiles", "crossings.pmtiles", "kerbs.pmtiles", "stairways.pmtiles", "main_footways.pmtiles", "potential_footways.pmtiles", "informal_footways.pmtiles", "pedestrian_areas.pmtiles"]
            elif key == "updates":
                files = ["registry.json", "index.html", "versioning/sidewalks_versioning.json", "versioning/crossings_versioning.json", "versioning/kerbs_versioning.json", "versioning/other_footways_versioning.json"]
            elif key == "vrts":
                files = ["data.vrt", "data_raw.vrt", "tiles.vrt"]
            elif key == "data_quality":
                files = ["improper_geoms/sidewalks_improper_geoms.parquet", "improper_geoms/crossings_improper_geoms.parquet", "improper_geoms/kerbs_improper_geoms.parquet", "disjointed/crossings_disjointed.parquet", "disjointed/kerbs_disjointed.parquet"]
            elif key == "routing":
                files = ["demo.geojson"]
        
        data_idx["folders"][key] = {
            "description": meta["description"],
            "path": meta["path"],
            "files": sorted(files)
        }
        
    index_json_path = os.path.join("data", "index.json")
    os.makedirs("data", exist_ok=True)
    with open(index_json_path, "w", encoding="utf-8") as f:
        json.dump(data_idx, f, indent=4, ensure_ascii=False)
    print(f"Index successfully written to {index_json_path}")

def generate_api_html():
    """Generates the interactive API page at hub/acquisition/API/index.html."""
    print("Generating hub/acquisition/API/index.html...")
    
    # HTML endpoints data structure for JS
    endpoints_js = json.dumps(endpoints_config, indent=2)
    
    # Use standard template string with replaces to avoid syntax errors from literal braces in JS and CSS.
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSWM Serverless API | [CITY_NAME]</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-gradient: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            --card-bg: rgba(30, 41, 59, 0.7);
            --card-border: rgba(255, 255, 255, 0.08);
            --primary: #00f2fe;
            --primary-glow: rgba(0, 242, 254, 0.15);
            --secondary: #4facfe;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --sidebar-width: 340px;
            --accent-success: #10b981;
            --accent-error: #ef4444;
            --accent-purple: #8b5cf6;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg-gradient);
            color: var(--text-main);
            min-height: 100vh;
            line-height: 1.6;
            overflow-x: hidden;
            display: flex;
            flex-direction: column;
        }

        /* Glow effects */
        body::before {
            content: '';
            position: fixed;
            top: -20%;
            left: -10%;
            width: 600px;
            height: 600px;
            background: radial-gradient(circle, rgba(0, 242, 254, 0.12) 0%, rgba(0,0,0,0) 70%);
            z-index: -1;
            pointer-events: none;
        }

        body::after {
            content: '';
            position: fixed;
            bottom: -10%;
            right: -10%;
            width: 700px;
            height: 700px;
            background: radial-gradient(circle, rgba(139, 92, 246, 0.1) 0%, rgba(0,0,0,0) 70%);
            z-index: -1;
            pointer-events: none;
        }

        header {
            background: rgba(15, 23, 42, 0.6);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--card-border);
            position: sticky;
            top: 0;
            z-index: 100;
            width: 100%;
        }

        .header-container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 1.25rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: 100%;
        }

        .logo-section {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .logo-section img {
            height: 38px;
            width: auto;
        }

        .logo-section h1 {
            font-size: 1.35rem;
            font-weight: 600;
            letter-spacing: -0.5px;
            background: linear-gradient(to right, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .nav-buttons {
            display: flex;
            gap: 1rem;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.5rem 1.15rem;
            border-radius: 8px;
            font-weight: 500;
            font-size: 0.9rem;
            text-decoration: none;
            transition: all 0.2s ease;
            cursor: pointer;
            border: 1px solid transparent;
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-main);
            border-color: var(--card-border);
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.2);
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: #0f172a;
            font-weight: 600;
            box-shadow: 0 4px 12px var(--primary-glow);
        }

        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(0, 242, 254, 0.25);
        }

        .container {
            width: 100%;
            max-width: 1600px;
            margin: 2rem auto;
            padding: 0 2rem;
            flex-grow: 1;
            display: flex;
            gap: 2rem;
        }

        /* Left Sidebar - Endpoints list */
        .sidebar {
            width: var(--sidebar-width);
            flex-shrink: 0;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .glass-panel {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        }

        .info-card h2 {
            font-size: 1.1rem;
            margin-bottom: 0.75rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .info-card p {
            font-size: 0.88rem;
            color: var(--text-muted);
            margin-bottom: 0.75rem;
        }

        .base-url-box {
            background: rgba(15, 23, 42, 0.5);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 0.6rem 0.8rem;
            font-family: 'Fira Code', monospace;
            font-size: 0.82rem;
            word-break: break-all;
            color: var(--primary);
        }

        .endpoint-selector-group {
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
            max-height: 600px;
            overflow-y: auto;
            padding-right: 0.5rem;
        }

        /* Scrollbar styles */
        .endpoint-selector-group::-webkit-scrollbar,
        .code-pre::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        .endpoint-selector-group::-webkit-scrollbar-thumb,
        .code-pre::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        }
        .endpoint-selector-group::-webkit-scrollbar-thumb:hover,
        .code-pre::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.25);
        }

        .category-block h3 {
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-muted);
            margin-bottom: 0.6rem;
            border-left: 2px solid var(--secondary);
            padding-left: 0.5rem;
        }

        .endpoint-list {
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }

        .endpoint-item {
            display: flex;
            flex-direction: column;
            padding: 0.65rem 0.85rem;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid transparent;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .endpoint-item:hover {
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.05);
        }

        .endpoint-item.active {
            background: rgba(0, 242, 254, 0.06);
            border-color: rgba(0, 242, 254, 0.25);
            box-shadow: inset 0 0 10px rgba(0, 242, 254, 0.05);
        }

        .endpoint-item .path {
            font-family: 'Fira Code', monospace;
            font-size: 0.82rem;
            font-weight: 500;
            color: var(--text-main);
            word-break: break-all;
        }

        .endpoint-item.active .path {
            color: var(--primary);
        }

        .endpoint-item .meta-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 0.35rem;
        }

        .badge {
            font-size: 0.72rem;
            padding: 0.1rem 0.4rem;
            border-radius: 4px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-get {
            background: rgba(16, 185, 129, 0.15);
            color: var(--accent-success);
        }

        .badge-format {
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-muted);
        }

        /* Right Content Area */
        .main-content {
            flex-grow: 1;
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }

        /* Playground Panel */
        .playground-panel {
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
        }

        .playground-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 1rem;
        }

        .playground-title-desc h2 {
            font-size: 1.35rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }

        .playground-title-desc p {
            font-size: 0.92rem;
            color: var(--text-muted);
        }

        .request-url-bar {
            display: flex;
            gap: 0.75rem;
            background: rgba(15, 23, 42, 0.4);
            border: 1px solid var(--card-border);
            border-radius: 10px;
            padding: 0.5rem;
            align-items: center;
        }

        .method-tag {
            font-family: 'Fira Code', monospace;
            font-weight: 700;
            font-size: 0.85rem;
            color: var(--accent-success);
            padding-left: 0.5rem;
        }

        .request-url-input {
            flex-grow: 1;
            background: transparent;
            border: none;
            color: var(--text-main);
            font-family: 'Fira Code', monospace;
            font-size: 0.85rem;
            outline: none;
        }

        /* Response Viewer */
        .response-viewer {
            background: #0b0f19;
            border-radius: 12px;
            border: 1px solid var(--card-border);
            display: flex;
            flex-direction: column;
            height: 380px;
            overflow: hidden;
        }

        .response-header-bar {
            background: rgba(255, 255, 255, 0.02);
            border-bottom: 1px solid var(--card-border);
            padding: 0.65rem 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        .response-status {
            display: flex;
            align-items: center;
            gap: 0.4rem;
            font-weight: 600;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }

        .status-dot.idle { background: var(--text-muted); }
        .status-dot.loading { background: var(--primary); animation: pulse 1s infinite alternate; }
        .status-dot.success { background: var(--accent-success); }
        .status-dot.error { background: var(--accent-error); }

        @keyframes pulse {
            0% { opacity: 0.3; }
            100% { opacity: 1; }
        }

        .response-body {
            flex-grow: 1;
            overflow: auto;
            position: relative;
        }

        .code-pre {
            width: 100%;
            height: 100%;
            padding: 1rem;
            margin: 0;
            font-family: 'Fira Code', monospace;
            font-size: 0.82rem;
            color: #38bdf8;
            overflow: auto;
            white-space: pre;
        }

        .placeholder-text {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: var(--text-muted);
            font-size: 0.9rem;
            text-align: center;
            pointer-events: none;
        }

        .spinner {
            display: none;
            width: 30px;
            height: 30px;
            border: 3px solid rgba(0, 242, 254, 0.1);
            border-radius: 50%;
            border-top-color: var(--primary);
            animation: spin 1s ease-in-out infinite;
            position: absolute;
            top: 50%;
            left: 50%;
            margin-top: -15px;
            margin-left: -15px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Code Snippet Tabs */
        .snippets-card h3 {
            font-size: 1.1rem;
            margin-bottom: 1rem;
            font-weight: 600;
        }

        .tab-headers {
            display: flex;
            border-bottom: 1px solid var(--card-border);
            margin-bottom: 1rem;
            gap: 1.5rem;
        }

        .tab-header {
            padding: 0.5rem 0.2rem 0.75rem 0.2rem;
            color: var(--text-muted);
            font-size: 0.9rem;
            font-weight: 500;
            cursor: pointer;
            position: relative;
            transition: color 0.2s ease;
        }

        .tab-header:hover {
            color: var(--text-main);
        }

        .tab-header.active {
            color: var(--primary);
            font-weight: 600;
        }

        .tab-header.active::after {
            content: '';
            position: absolute;
            bottom: -1px;
            left: 0;
            width: 100%;
            height: 2px;
            background: var(--primary);
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        .snippet-box {
            position: relative;
            border-radius: 8px;
            overflow: hidden;
            background: #090d16;
            border: 1px solid var(--card-border);
        }

        .snippet-box pre {
            padding: 1.25rem;
            font-family: 'Fira Code', monospace;
            font-size: 0.82rem;
            color: #cbd5e1;
            overflow-x: auto;
            margin: 0;
        }

        .btn-copy {
            position: absolute;
            top: 0.5rem;
            right: 0.5rem;
            padding: 0.35rem 0.6rem;
            font-size: 0.72rem;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
            color: var(--text-muted);
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .btn-copy:hover {
            background: rgba(255, 255, 255, 0.1);
            color: var(--text-main);
        }

        footer {
            text-align: center;
            padding: 2.5rem;
            color: var(--text-muted);
            font-size: 0.85rem;
            border-top: 1px solid var(--card-border);
            background: rgba(15, 23, 42, 0.4);
            margin-top: 4rem;
        }

        footer a {
            color: var(--secondary);
            text-decoration: none;
        }

        footer a:hover {
            text-decoration: underline;
        }

        @media (max-width: 1024px) {
            .container {
                flex-direction: column;
            }
            .sidebar {
                width: 100%;
            }
        }
    </style>
</head>
<body>

    <header>
        <div class="header-container">
            <div class="logo-section">
                <img src="https://kauevestena.github.io/oswm_codebase/assets/homepage/project_logo_100px.png" alt="OSWM Logo">
                <h1>OpenSidewalkMap API <span style="font-weight: 300; opacity: 0.8; color: var(--text-main)">| [CITY_NAME]</span></h1>
            </div>
            <div class="nav-buttons">
                <a href="../../../index.html" class="btn btn-secondary">Node Home</a>
                <a href="../../../map.html" class="btn btn-primary">Open Webmap</a>
            </div>
        </div>
    </header>

    <div class="container">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="glass-panel info-card">
                <h2>Serverless API Details</h2>
                <p>OSWM exposes processed city datasets as static files hosted on GitHub Pages. Any standard HTTP client can access these files directly.</p>
                <div class="base-url-box" id="base-url-display"></div>
            </div>

            <div class="glass-panel" style="flex-grow: 1;">
                <h2 style="font-size: 1.1rem; margin-bottom: 1rem; font-weight: 600;">API Endpoints</h2>
                <div class="endpoint-selector-group" id="endpoint-list-container">
                    <!-- Dynamic endpoints will load here -->
                </div>
            </div>
        </div>

        <!-- Main Panel -->
        <div class="main-content">
            <!-- Playground -->
            <div class="glass-panel playground-panel">
                <div class="playground-header">
                    <div class="playground-title-desc">
                        <h2 id="pl-title">Select an Endpoint</h2>
                        <p id="pl-desc">Select an API endpoint from the sidebar list to inspect properties, read code examples, and perform playground requests.</p>
                    </div>
                    <div>
                        <span class="badge badge-format" id="pl-format-badge">JSON</span>
                    </div>
                </div>

                <div class="request-url-bar">
                    <span class="method-tag">GET</span>
                    <input type="text" class="request-url-input" id="request-url-input" readonly>
                    <button class="btn btn-secondary" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;" onclick="copyRequestUrl()">Copy URL</button>
                </div>

                <div style="display: flex; gap: 1rem;">
                    <button class="btn btn-primary" id="btn-try" onclick="executePlaygroundRequest()">Try It Out</button>
                    <button class="btn btn-secondary" id="btn-dl" onclick="downloadEndpointFile()">Download File</button>
                </div>

                <!-- Response Viewer -->
                <div class="response-viewer">
                    <div class="response-header-bar">
                        <span>Response Body</span>
                        <div class="response-status">
                            <span class="status-dot idle" id="status-dot"></span>
                            <span id="status-text">No request sent</span>
                        </div>
                    </div>
                    <div class="response-body">
                        <div class="spinner" id="spinner"></div>
                        <div class="placeholder-text" id="placeholder-text">Click "Try It Out" to send a request to the serverless endpoint.</div>
                        <pre class="code-pre" id="response-pre" style="display: none;"></pre>
                    </div>
                </div>
            </div>

            <!-- Code snippets -->
            <div class="glass-panel snippets-card">
                <h3>Request Snippet Examples</h3>
                <div class="tab-headers">
                    <div class="tab-header active" onclick="switchSnippetTab('tab-js')">JavaScript</div>
                    <div class="tab-header" onclick="switchSnippetTab('tab-python')">Python</div>
                    <div class="tab-header" onclick="switchSnippetTab('tab-gdal')">GDAL/OGR</div>
                    <div class="tab-header" onclick="switchSnippetTab('tab-curl')">cURL</div>
                </div>

                <!-- JS Tab -->
                <div class="tab-content active" id="tab-js">
                    <div class="snippet-box">
                        <button class="btn-copy" onclick="copySnippet('code-js')">Copy</button>
                        <pre id="code-js">fetch('https://...')
  .then(response => response.json())
  .then(data => console.log(data));</pre>
                    </div>
                </div>

                <!-- Python Tab -->
                <div class="tab-content" id="tab-python">
                    <div class="snippet-box">
                        <button class="btn-copy" onclick="copySnippet('code-py')">Copy</button>
                        <pre id="code-py">import requests

url = "https://..."
response = requests.get(url)
data = response.json()
print(data)</pre>
                    </div>
                </div>

                <!-- GDAL Tab -->
                <div class="tab-content" id="tab-gdal">
                    <div class="snippet-box">
                        <button class="btn-copy" onclick="copySnippet('code-gdal')">Copy</button>
                        <pre id="code-gdal">ogrinfo -ro -al "/vsicurl/https://..."</pre>
                    </div>
                </div>

                <!-- cURL Tab -->
                <div class="tab-content" id="tab-curl">
                    <div class="snippet-box">
                        <button class="btn-copy" onclick="copySnippet('code-curl')">Copy</button>
                        <pre id="code-curl">curl -L -X GET "https://..."</pre>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <footer>
        <p>OpenSidewalkMap Node [CITY_NAME]. Developed by <a href="https://github.com/kauevestena" target="_blank">Kauê Vestena</a>.</p>
        <p style="margin-top: 0.5rem; font-size: 0.75rem; opacity: 0.7;">Powered by static serverless architectures.</p>
    </footer>

    <script>
        // API Base configuration
        const USERNAME = "[USERNAME]";
        const REPO_NAME = "[REPO_NAME]";
        const baseUrl = "[node_homepage_url]";
        
        document.getElementById('base-url-display').textContent = baseUrl;

        // Endpoints configuration parsed from Python
        const endpoints = [endpoints_js];

        let selectedEndpoint = null;

        // Render endpoints listing grouped by categories
        function renderEndpoints() {
            const container = document.getElementById('endpoint-list-container');
            container.innerHTML = '';

            // Group by category
            const categories = {};
            endpoints.forEach(ep => {
                if (!categories[ep.category]) {
                    categories[ep.category] = [];
                }
                categories[ep.category].push(ep);
            });

            // Create DOM elements
            for (const catName in categories) {
                const catBlock = document.createElement('div');
                catBlock.className = 'category-block';
                
                const h3 = document.createElement('h3');
                h3.textContent = catName;
                catBlock.appendChild(h3);

                const listDiv = document.createElement('div');
                listDiv.className = 'endpoint-list';

                categories[catName].forEach(ep => {
                    const item = document.createElement('div');
                    item.className = 'endpoint-item';
                    item.onclick = () => selectEndpoint(ep, item);

                    const pathSpan = document.createElement('span');
                    pathSpan.className = 'path';
                    pathSpan.textContent = '/' + ep.path;

                    const metaRow = document.createElement('div');
                    metaRow.className = 'meta-row';

                    const method = document.createElement('span');
                    method.className = 'badge badge-get';
                    method.textContent = 'GET';

                    const format = document.createElement('span');
                    format.className = 'badge badge-format';
                    format.textContent = ep.format;

                    metaRow.appendChild(method);
                    metaRow.appendChild(format);
                    item.appendChild(pathSpan);
                    item.appendChild(metaRow);

                    listDiv.appendChild(item);
                });

                catBlock.appendChild(listDiv);
                container.appendChild(catBlock);
            }
        }

        // Handle Endpoint Selection
        function selectEndpoint(ep, element) {
            // Remove active classes
            document.querySelectorAll('.endpoint-item').forEach(el => el.classList.remove('active'));
            
            // Set active class
            element.classList.add('active');
            selectedEndpoint = ep;

            // Update details
            document.getElementById('pl-title').textContent = '/' + ep.path;
            document.getElementById('pl-desc').textContent = ep.description;
            document.getElementById('pl-format-badge').textContent = ep.format;

            const fullUrl = baseUrl + ep.path;
            document.getElementById('request-url-input').value = fullUrl;

            // Reset playground response window
            resetPlayground();

            // Toggle try/download buttons based on playability
            const btnTry = document.getElementById('btn-try');
            if (ep.playground) {
                btnTry.disabled = false;
                btnTry.style.opacity = '1';
                btnTry.style.cursor = 'pointer';
            } else {
                btnTry.disabled = true;
                btnTry.style.opacity = '0.5';
                btnTry.style.cursor = 'not-allowed';
            }

            // Update code snippets
            updateSnippets(fullUrl, ep.format);
        }

        function resetPlayground() {
            document.getElementById('response-pre').style.display = 'none';
            document.getElementById('placeholder-text').style.display = 'block';
            document.getElementById('placeholder-text').textContent = 'Click "Try It Out" to send a request to the serverless endpoint.';
            document.getElementById('spinner').style.display = 'none';
            
            const dot = document.getElementById('status-dot');
            dot.className = 'status-dot idle';
            document.getElementById('status-text').textContent = 'No request sent';
        }

        // Execute playground AJAX request
        async function executePlaygroundRequest() {
            if (!selectedEndpoint) return;

            const requestUrl = document.getElementById('request-url-input').value;
            
            // Adjust URL to relative path if running locally to avoid CORS / missing files issues
            let fetchUrl = requestUrl;
            const isLocal = window.location.protocol === 'file:' || 
                            window.location.hostname === 'localhost' || 
                            window.location.hostname === '127.0.0.1';

            if (isLocal && requestUrl.startsWith(baseUrl)) {
                // API page is located inside hub/acquisition/API/index.html
                // So relative paths to data files are three directories up
                fetchUrl = '../../../' + selectedEndpoint.path;
            }

            // Update states
            document.getElementById('placeholder-text').style.display = 'none';
            document.getElementById('response-pre').style.display = 'none';
            document.getElementById('spinner').style.display = 'block';
            
            const dot = document.getElementById('status-dot');
            dot.className = 'status-dot loading';
            document.getElementById('status-text').textContent = 'Fetching data...';

            try {
                const response = await fetch(fetchUrl);
                document.getElementById('spinner').style.display = 'none';
                
                if (response.ok) {
                    dot.className = 'status-dot success';
                    document.getElementById('status-text').textContent = response.status + ' ' + response.statusText;
                    
                    const contentType = response.headers.get('content-type');
                    
                    let dataText = '';
                    if (selectedEndpoint.format === 'JSON' || selectedEndpoint.format === 'GeoJSON') {
                        const json = await response.json();
                        dataText = JSON.stringify(json, null, 2);
                    } else {
                        dataText = await response.text();
                    }

                    const pre = document.getElementById('response-pre');
                    pre.style.display = 'block';
                    pre.textContent = dataText;
                } else {
                    dot.className = 'status-dot error';
                    document.getElementById('status-text').textContent = response.status + ' ' + response.statusText;
                    
                    const pre = document.getElementById('response-pre');
                    pre.style.display = 'block';
                    pre.textContent = 'Error details: Request returned a non-200 status code.\\n\\nURL Attempted: ' + fetchUrl + '\\nHTTP Status: ' + response.status + ' - ' + response.statusText;
                }
            } catch (err) {
                document.getElementById('spinner').style.display = 'none';
                dot.className = 'status-dot error';
                document.getElementById('status-text').textContent = 'Network Error';
                
                const pre = document.getElementById('response-pre');
                pre.style.display = 'block';
                pre.textContent = 'Fetch Failed: ' + err.message + '\\n\\nThis could be due to a CORS policy restriction or because the file does not exist locally yet. If running locally, make sure to generate the data folder contents.';
            }
        }

        function downloadEndpointFile() {
            if (!selectedEndpoint) return;
            const requestUrl = document.getElementById('request-url-input').value;
            window.open(requestUrl, '_blank');
        }

        function copyRequestUrl() {
            const input = document.getElementById('request-url-input');
            if (input.value) {
                navigator.clipboard.writeText(input.value);
                alert('Copied request URL to clipboard!');
            }
        }

        function updateSnippets(url, format) {
            // JS
            let jsCode = 'fetch(\\'' + url + '\\')\\n  .then(response => response.json())\\n  .then(data => console.log(data));';
            if (format === 'PMTiles') {
                jsCode = '// Read vector tiles efficiently in JS\\nimport { PMTiles } from \\'pmtiles\\';\\n\\nconst tilesUrl = \\'' + url + '\\';\\nconst p = new PMTiles(tilesUrl);\\n// Add to maplibre or leaflet...';
            } else if (format === 'GeoParquet') {
                jsCode = '// Reading GeoParquet in JS requires specialized libraries like @loaders.gl/parquet\\n// See: https://loaders.gl/docs/specifications/category-gis';
            }
            document.getElementById('code-js').textContent = jsCode;

            // Python
            let pyCode = 'import requests\\n\\nurl = "' + url + '"\\nresponse = requests.get(url)\\ndata = response.json()\\nprint(data)';
            if (format === 'GeoParquet') {
                pyCode = 'import geopandas as gpd\\n\\n# Open GeoParquet directly via HTTP/s URL\\nurl = "' + url + '"\\ngdf = gpd.read_parquet(url)\\nprint(gdf.head())';
            } else if (format === 'GeoJSON') {
                pyCode = 'import geopandas as gpd\\n\\n# Open GeoJSON directly via HTTP/s URL\\nurl = "' + url + '"\\ngdf = gpd.read_file(url)\\nprint(gdf.head())';
            } else if (format === 'PMTiles') {
                pyCode = 'from pmtiles.reader import Reader\\nimport urllib.request\\n\\n# Read pmtiles headers\\nurl = "' + url + '"\\n# Open stream and read...';
            }
            document.getElementById('code-py').textContent = pyCode;

            // GDAL
            let gdalCode = 'ogrinfo -ro -al "/vsicurl/' + url + '"';
            if (format === 'PMTiles') {
                gdalCode = '# GDAL support for PMTiles starting from version 3.8.0\\nogrinfo -ro -al "/vsipmtiles/vsicurl/' + url + '"';
            }
            document.getElementById('code-gdal').textContent = gdalCode;

            // cURL
            const curlCode = 'curl -L -X GET "' + url + '"';
            document.getElementById('code-curl').textContent = curlCode;
        }

        function switchSnippetTab(tabId) {
            document.querySelectorAll('.tab-header').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));

            const activeTabHeader = Array.from(document.querySelectorAll('.tab-header')).find(el => el.getAttribute('onclick').includes(tabId));
            if (activeTabHeader) activeTabHeader.classList.add('active');

            const tabContent = document.getElementById(tabId);
            if (tabContent) tabContent.classList.add('active');
        }

        function copySnippet(elementId) {
            const code = document.getElementById(elementId).textContent;
            navigator.clipboard.writeText(code);
            alert('Code snippet copied to clipboard!');
        }

        // Initialize Page
        renderEndpoints();
        // Select first endpoint by default
        setTimeout(() => {
            const firstItem = document.querySelector('.endpoint-item');
            if (firstItem) {
                firstItem.click();
            }
        }, 100);
    </script>
</body>
</html>
"""
    
    # Process the replacements
    processed_html = (html_template
                      .replace("[CITY_NAME]", CITY_NAME)
                      .replace("[USERNAME]", USERNAME)
                      .replace("[REPO_NAME]", REPO_NAME)
                      .replace("[node_homepage_url]", node_homepage_url)
                      .replace("[endpoints_js]", endpoints_js))

    # Save the output file
    api_html_path = os.path.join(api_folder, "index.html")
    ensure_parent_folder(api_html_path)
    
    with open(api_html_path, "w", encoding="utf-8") as f:
        f.write(processed_html)
        
    print(f"API documentation page written to {api_html_path}")

if __name__ == "__main__":
    generate_data_index()
    generate_api_html()
    print("API resources generation completed successfully.")
