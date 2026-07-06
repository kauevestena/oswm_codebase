import os
import sys
import geopandas as gpd
import pandas as pd

# Add repository root and oswm_codebase directory to sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

oswm_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if oswm_dir not in sys.path:
    sys.path.insert(0, oswm_dir)

from constants import (
    sidewalks_path,
    crossings_path,
    other_footways_path,
    routing_demo_path,
    routing_folderpath
)

def main():
    print("Generating routing demo data...")
    
    # Check if processed files exist
    for path, name in [
        (sidewalks_path, "sidewalks"),
        (crossings_path, "crossings"),
        (other_footways_path, "other_footways")
    ]:
        if not os.path.exists(path):
            print(f"Error: Processed file {name} not found at {path}")
            sys.exit(1)
            
    # Load processed datasets
    s_gdf = gpd.read_parquet(sidewalks_path)
    c_gdf = gpd.read_parquet(crossings_path)
    of_gdf = gpd.read_parquet(other_footways_path)
    
    # Filter to only keep LineStrings (and explode MultiLineStrings if any exist)
    gdfs_to_concat = []
    for gdf, name in [(s_gdf, "sidewalks"), (c_gdf, "crossings"), (of_gdf, "other_footways")]:
        # Filter out empty geometries and keep only LineString or MultiLineString
        valid_gdf = gdf[gdf.geometry.notnull() & (~gdf.geometry.is_empty)]
        
        # Keep only LineStrings and MultiLineStrings
        line_gdf = valid_gdf[valid_gdf.geometry.type.isin(["LineString", "MultiLineString"])]
        
        # Explode MultiLineStrings to individual LineStrings
        if not line_gdf.empty:
            exploded = line_gdf.explode(index_parts=False)
            exploded = exploded[exploded.geometry.type == "LineString"]
            gdfs_to_concat.append(exploded[["id", "geometry"]])
            print(f"  Processed {name}: kept {len(exploded)} LineString features.")
            
    if not gdfs_to_concat:
        print("Error: No LineString features found in processed datasets.")
        sys.exit(1)
        
    # Concatenate all datasets
    combined_gdf = gpd.GeoDataFrame(pd.concat(gdfs_to_concat, ignore_index=True), crs=s_gdf.crs)
    
    # Ensure ID is integer
    combined_gdf["id"] = combined_gdf["id"].astype(int)
    
    # Create parent folder if not exists
    os.makedirs(routing_folderpath, exist_ok=True)
    
    # Save as GeoJSON
    combined_gdf.to_file(routing_demo_path, driver="GeoJSON")
    print(f"Routing demo data successfully generated at {routing_demo_path} ({len(combined_gdf)} features).")

if __name__ == "__main__":
    main()
