import sys

sys.path.append("oswm_codebase")
from functions import *
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


def generate_vrt_xml(layer_name: str, source_files: dict, vrt_output_path: str) -> str:
    """
    Generate an OGR VRT XML string that creates a union layer from multiple source files.

    Args:
        layer_name: Name for the union layer in the VRT
        source_files: Dict with layer names as keys and file paths as values
        vrt_output_path: The output path of the VRT file (used to calculate relative paths)

    Returns:
        Pretty-printed XML string for the VRT file
    """
    # Root element
    root = Element("OGRVRTDataSource")

    # Create a union layer to combine all sources
    union_layer = SubElement(root, "OGRVRTUnionLayer", name=layer_name)

    # Calculate the directory of the VRT file for relative path calculation
    vrt_dir = os.path.dirname(vrt_output_path)

    for src_layer_name, src_filepath in source_files.items():
        # Create an OGRVRTLayer for each source file
        vrt_layer = SubElement(union_layer, "OGRVRTLayer", name=src_layer_name)

        # Calculate relative path from VRT location to source file
        relative_path = os.path.relpath(src_filepath, vrt_dir)

        # Add SrcDataSource with relativeToVRT attribute
        src_datasource = SubElement(vrt_layer, "SrcDataSource", relativeToVRT="1")
        src_datasource.text = relative_path

        # SrcLayer - for parquet files, the layer name is typically the filename without extension
        src_layer = SubElement(vrt_layer, "SrcLayer")
        src_layer.text = os.path.splitext(os.path.basename(src_filepath))[0]

    # Convert to string with pretty printing
    rough_string = tostring(root, encoding="unicode")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="    ")


def generate_simple_vrt_xml(
    layer_name: str, source_files: dict, vrt_output_path: str
) -> str:
    """
    Generate an OGR VRT XML string with separate layers (no union).

    Args:
        layer_name: Base name for the VRT (used in comments/documentation)
        source_files: Dict with layer names as keys and file paths as values
        vrt_output_path: The output path of the VRT file (used to calculate relative paths)

    Returns:
        Pretty-printed XML string for the VRT file
    """
    # Root element
    root = Element("OGRVRTDataSource")

    # Calculate the directory of the VRT file for relative path calculation
    vrt_dir = os.path.dirname(vrt_output_path)

    for src_layer_name, src_filepath in source_files.items():
        # Create an OGRVRTLayer for each source file
        vrt_layer = SubElement(root, "OGRVRTLayer", name=src_layer_name)

        # Calculate relative path from VRT location to source file
        relative_path = os.path.relpath(src_filepath, vrt_dir)

        # Add SrcDataSource with relativeToVRT attribute
        src_datasource = SubElement(vrt_layer, "SrcDataSource", relativeToVRT="1")
        src_datasource.text = relative_path

        # SrcLayer - for parquet files, the layer name is typically the filename without extension
        src_layer = SubElement(vrt_layer, "SrcLayer")
        src_layer.text = os.path.splitext(os.path.basename(src_filepath))[0]

    # Convert to string with pretty printing
    rough_string = tostring(root, encoding="unicode")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="    ")


def write_vrt_file(vrt_content: str, output_path: str):
    """Write VRT XML content to a file."""
    ensure_parent_folder(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(vrt_content)
    print(f"VRT file written to: {output_path}")


# ensure the vrt folder exists:
create_folder_if_not_exists(vrts_folderpath)

# targets are the files listed in the "paths_dict", just the "data" and "data_raw":
targets = {
    "data": paths_dict["data"],
    "data_raw": paths_dict["data_raw"],
    "tiles": {
        layername: os.path.join(tiles_folderpath, layername + ".pmtiles")
        for layername in paths_dict["map_layers"]
    },
}


for targetname in targets:
    outpath = os.path.join(vrts_folderpath, f"{targetname}.vrt")
    source_files_dict = targets[targetname]

    # Generate VRT with separate layers (each source as its own layer)
    # Use generate_vrt_xml() instead if you want a single union layer
    vrt_xml = generate_simple_vrt_xml(
        layer_name=targetname, source_files=source_files_dict, vrt_output_path=outpath
    )

    # Write the VRT file
    write_vrt_file(vrt_xml, outpath)

print(f"\nVRT generation complete. Files created in: {vrts_folderpath}")
