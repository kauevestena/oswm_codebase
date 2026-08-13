"""Format-aware actions and example filters for the static OSWM API page."""

import math


_CAPABILITIES_BY_FORMAT = {
    "JSON": {
        "action": "preview-json",
        "action_label": "Preview JSON",
        "snippets": ("javascript", "python", "curl"),
    },
    "GeoJSON": {
        "action": "preview-json",
        "action_label": "Preview GeoJSON",
        "snippets": ("javascript", "python", "gdal", "curl"),
    },
    "GeoParquet": {
        "action": "copy-spatial-extract",
        "action_label": "Copy 1 km Extract",
        "snippets": ("python", "gdal", "curl"),
    },
    "PMTiles": {
        "action": "inspect-pmtiles",
        "action_label": "Inspect Archive",
        "snippets": ("javascript", "gdal", "curl"),
    },
    "XML/VRT": {
        "action": "preview-text",
        "action_label": "Preview VRT",
        "snippets": ("gdal", "curl"),
    },
    "CSV": {
        "action": "preview-text",
        "action_label": "Preview CSV",
        "snippets": ("javascript", "python", "curl"),
    },
    "PNG": {
        "action": "open-resource",
        "action_label": "View Image",
        "snippets": ("curl",),
    },
    "OSWM Binary Graph": {
        "action": "download-resource",
        "action_label": "Download Graph",
        "snippets": ("javascript", "python", "curl"),
    },
    "File": {
        "action": "download-resource",
        "action_label": "Download File",
        "snippets": ("curl",),
    },
}


def resource_format(filename):
    """Return the API display format for a resource filename."""
    lower_name = filename.lower()
    if lower_name.endswith(".geojson"):
        return "GeoJSON"
    if lower_name.endswith(".json"):
        return "JSON"
    if lower_name.endswith(".parquet"):
        return "GeoParquet"
    if lower_name.endswith(".pmtiles"):
        return "PMTiles"
    if lower_name.endswith(".oswmg"):
        return "OSWM Binary Graph"
    if lower_name.endswith(".vrt"):
        return "XML/VRT"
    if lower_name.endswith(".png"):
        return "PNG"
    if lower_name.endswith(".csv"):
        return "CSV"
    return "File"


def attribute_filter_for_path(path):
    """Choose an illustrative filter that matches common OSWM layer schemas."""
    lower_path = path.lower()
    if any(token in lower_path for token in ("sidewalk", "footway", "stairway")):
        return "surface = 'asphalt'"
    if "crossing" in lower_path:
        return "crossing IS NOT NULL"
    if "kerb" in lower_path:
        return "kerb IS NOT NULL"
    return "id IS NOT NULL"


def capabilities_for_resource(format_name, path=""):
    """Return a JSON-serializable capability descriptor for one resource."""
    template = _CAPABILITIES_BY_FORMAT.get(
        format_name, _CAPABILITIES_BY_FORMAT["File"]
    )
    capabilities = {
        "action": template["action"],
        "action_label": template["action_label"],
        "snippets": list(template["snippets"]),
    }
    if format_name in {"GeoJSON", "GeoParquet"}:
        capabilities["attribute_filter"] = attribute_filter_for_path(path)
    return capabilities


def square_bbox(center_lat, center_lon, size_m=1000):
    """Return a CRS84 square bbox centered on a point.

    ``size_m`` is the approximate full width and height, so the default extends
    about 500 metres in each direction from the configured centre.
    """
    values = (center_lat, center_lon, size_m)
    if not all(isinstance(value, (int, float)) for value in values):
        raise TypeError("centre coordinates and bbox size must be numeric")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("centre coordinates and bbox size must be finite")
    if not -90 <= center_lat <= 90 or not -180 <= center_lon <= 180:
        raise ValueError("centre coordinates are outside valid latitude/longitude ranges")
    if size_m <= 0:
        raise ValueError("bbox size must be greater than zero")

    metres_per_degree = 111_320.0
    longitude_scale = math.cos(math.radians(center_lat))
    if abs(longitude_scale) < 1e-8:
        raise ValueError("cannot calculate a longitude span at the poles")

    half_size_m = size_m / 2.0
    latitude_delta = half_size_m / metres_per_degree
    longitude_delta = half_size_m / (metres_per_degree * longitude_scale)
    return (
        round(center_lon - longitude_delta, 6),
        round(center_lat - latitude_delta, 6),
        round(center_lon + longitude_delta, 6),
        round(center_lat + latitude_delta, 6),
    )
