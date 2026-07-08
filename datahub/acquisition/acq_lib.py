import os
import sys
import requests

# Ensure the parent `datahub` directory is on sys.path so `dh_lib` can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dh_lib import boundaries_geojson_path


# keywords that are going to be used to search for projects in the supported platforms:
SEARCH_KEYWORDS = [
    "oswm",
    "OpenSidewalkMap",
    "accessibility",
    "pedestrian",
    "sidewalk",
    "walk",
    "kerb",
    "tactile paving",
    "crossing",
    "footway",
    "footpath",
    "stairway",
    # Portuguese translations (for localized project metadata)
    "acessibilidade",

]

# remeber that projects shall be filtered geographically considering the node bounding box (data/boundaries/polygon.geojson), and if possible the polygon itself, beware of CRS

# services supported for project acquisition (names and website links, meaning instances):
SUPPORTED_SERVICES = {
    "Tasking Manager": [
        "https://tasks.hotosm.org/",
        "https://tasks.teachosm.org/",
        "https://tasks.mapwith.ai/",
    ],
    "Pic4Review": ["https://pic4review.pavie.info/#/"], # pic4review is almost discontinued these days
    "MapRoulette": ["https://maproulette.org/"],
}

# Mapping of website instances to their respective backend API base URLs
SERVICE_API_ENDPOINTS = {
    "https://tasks.hotosm.org/": "https://tasking-manager-tm4-production-api.hotosm.org/api/v2/",
    "https://tasks.teachosm.org/": "https://tasks.teachosm.org/backend/api/v2/",
    "https://tasks.mapwith.ai/": "https://tasks.mapwith.ai/api/v2/",
    "https://maproulette.org/": "https://maproulette.org/api/v2/",
    "https://pic4review.pavie.info/#/": "https://pic4review.pavie.info/api/"
}


# bounding box shall come from "BOUNDING_BOX" in config.py


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def get_bbox_from_boundary():
    """
    Load the study-area bounding box from the boundary GeoJSON file.
    Returns a tuple (south, west, north, east) matching the BOUNDING_BOX convention,
    or falls back to BOUNDING_BOX from config.py if the file is unavailable.
    """
    try:
        import geopandas as gpd
        gdf = gpd.read_file(boundaries_geojson_path)
        minx, miny, maxx, maxy = gdf.total_bounds
        # Return as (south_lat, west_lon, north_lat, east_lon)
        return (miny, minx, maxy, maxx)
    except Exception:
        try:
            from config import BOUNDING_BOX
            return BOUNDING_BOX
        except ImportError:
            print("[acquisition] WARNING: Could not load bounding box from boundary file or config.py")
            return None


def get_boundary_polygon():
    """
    Load the study-area polygon geometry for post-filtering.
    Returns a shapely geometry, or None if unavailable.
    """
    try:
        import geopandas as gpd
        gdf = gpd.read_file(boundaries_geojson_path)
        return gdf.geometry.unary_union
    except Exception:
        return None


def query_to_json(api_call_url, timeout=30):
    """
    Perform a GET request to the given URL and return the parsed JSON response.
    Returns None on failure (with a printed warning).
    """
    try:
        response = requests.get(api_call_url, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            print(f"[acquisition] API call failed with status code: {response.status_code} for URL: {api_call_url}")
            return None
    except requests.exceptions.Timeout:
        print(f"[acquisition] Request timed out for URL: {api_call_url}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"[acquisition] Connection error for URL: {api_call_url}")
        return None
    except Exception as e:
        print(f"[acquisition] Unexpected error querying {api_call_url}: {e}")
        return None


# ---------------------------------------------------------------------------
# MapRoulette query functions
# ---------------------------------------------------------------------------


def query_maproulette(instance_url, bbox, queryword):
    """Build a browser-friendly MapRoulette search URL."""
    # sample query URL:
    # https://maproulette.org/browse/challenges?challengeSearch=-49.4312724%2C-25.2695963%2C-49.1112724%2C-25.5895963&location=intersectingMapBounds&query=sidewalk

    query_url = (
        instance_url.rstrip("/")
        + "/browse/challenges?challengeSearch="
        + f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}"
        + "&location=intersectingMapBounds"
        + f"&query={queryword}"
    )
    return query_url


def query_maproulette_API(instance_url, bbox, queryword):
    """Build a MapRoulette API URL for challenge search within a bounding box."""
    # sample successfull API call:
    # https://maproulette.org/api/v2/challenges/extendedFind?bb=2.224122,48.8155755,2.4697602,48.902156&cLocal=0&cStatus=3,4,0,-1&ce=true&cg=false&cs=sidewalk&limit=50&order=DESC&page=0&pe=true&sort=popularity
    # fundamental parameters are bounding box (bb) and search keyword (cs)
    base_api = SERVICE_API_ENDPOINTS.get(instance_url, instance_url.rstrip("/") + "/api/v2/")
    api_url = (
        base_api.rstrip("/")
        + "/challenges/extendedFind?"
        + f"bb={bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}"
        + "&cLocal=0&cStatus=3,4,0,-1&ce=true&cg=false"
        + f"&cs={queryword}"
        + "&limit=50&order=DESC&page=0&pe=true&sort=popularity"
    )
    return api_url


def parse_maproulette_results(raw_results, instance_url):
    """
    Normalize MapRoulette API results into the standard project format.
    Each challenge becomes a project dict.
    """
    projects = []
    if not raw_results or not isinstance(raw_results, list):
        return projects

    for item in raw_results:
        project = {
            "id": item.get("id", ""),
            "title": item.get("name", "Untitled"),
            "service": "MapRoulette",
            "instance": instance_url,
            "url": f"{instance_url.rstrip('/')}/browse/challenges/{item.get('id', '')}",
            "status": _maproulette_status(item.get("status", -1)),
            "description": item.get("description", ""),
        }
        projects.append(project)
    return projects


def _maproulette_status(status_code):
    """Map MapRoulette numeric status to a human-readable string."""
    status_map = {
        0: "N/A",
        1: "Building",
        2: "Failed",
        3: "Ready",
        4: "Partially loaded",
        5: "Finished",
        9: "Deletable",
    }
    return status_map.get(status_code, f"Unknown ({status_code})")


# ---------------------------------------------------------------------------
# HOT Tasking Manager query functions
# ---------------------------------------------------------------------------


def query_tasking_manager(instance_url, bbox, queryword):
    """Build a browser-friendly Tasking Manager search URL."""
    # Browser URL pattern:
    # https://tasks.hotosm.org/explore?text=sidewalk&orderBy=priority&orderByType=ASC
    import urllib.parse
    query_url = (
        instance_url.rstrip("/")
        + "/explore?"
        + f"text={urllib.parse.quote(queryword)}"
        + "&orderBy=priority&orderByType=ASC"
    )
    return query_url


def query_tasking_manager_API(instance_url, bbox, queryword):
    """
    Build a Tasking Manager API URL for project search within a bounding box.
    Uses GET /api/v2/projects/ with textSearch and bbox parameters.
    """
    import urllib.parse
    # bbox parameter format: minlon,minlat,maxlon,maxlat
    bbox_str = f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}"
    base_api = SERVICE_API_ENDPOINTS.get(instance_url, instance_url.rstrip("/") + "/api/v2/")
    api_url = (
        base_api.rstrip("/")
        + "/projects/"
        + f"?textSearch={urllib.parse.quote(queryword)}"
        + f"&bbox={bbox_str}"
        + "&orderBy=priority&orderByType=ASC"
    )
    return api_url


def parse_tasking_manager_results(raw_results, instance_url):
    """
    Normalize Tasking Manager API results into the standard project format.
    The TM API returns results in a 'results' key with pagination.
    """
    projects = []
    if not raw_results:
        return projects

    results_list = raw_results.get("results", [])
    if not isinstance(results_list, list):
        return projects

    for item in results_list:
        project_id = item.get("projectId", item.get("id", ""))
        project = {
            "id": project_id,
            "title": item.get("name", item.get("projectInfo", {}).get("name", "Untitled")),
            "service": "Tasking Manager",
            "instance": instance_url,
            "url": f"{instance_url.rstrip('/')}/projects/{project_id}",
            "status": _tasking_manager_status(item.get("status", "")),
            "description": item.get("shortDescription", item.get("projectInfo", {}).get("shortDescription", "")),
            "country": item.get("country", []),
        }
        # If the detail endpoint data is available (aoiBBOX), include it
        aoi_bbox = item.get("aoiBBOX")
        if aoi_bbox:
            project["bbox"] = aoi_bbox
        projects.append(project)
    return projects


def _tasking_manager_status(status):
    """Map Tasking Manager status to a human-readable string."""
    status_map = {
        "DRAFT": "Draft",
        "PUBLISHED": "Published",
        "ARCHIVED": "Archived",
    }
    if isinstance(status, str):
        return status_map.get(status.upper(), status)
    return str(status)


# ---------------------------------------------------------------------------
# Pic4Review query functions (graceful stub — service nearly discontinued)
# ---------------------------------------------------------------------------


def query_pic4review(instance_url, bbox, queryword):
    """
    Pic4Review stub — the service is nearly discontinued.
    Returns None and prints a deprecation/offline warning.
    """
    print(f"[acquisition] Pic4Review: service nearly discontinued — skipping query for '{queryword}'")
    return None


def query_pic4review_API(instance_url, bbox, queryword):
    """
    Pic4Review API stub.
    Attempts a basic health-check to determine if the server is online,
    then returns None regardless (no supported search API).
    """
    return None


def check_pic4review_online(instance_url, timeout=10):
    """
    Check whether a Pic4Review instance is reachable.
    Returns True/False/'error'.
    """
    try:
        response = requests.get(instance_url.rstrip("/").replace("/#/", "/"), timeout=timeout)
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False
    except requests.exceptions.Timeout:
        return False
    except Exception:
        return False


def parse_pic4review_results(raw_results, instance_url):
    """Pic4Review stub — always returns empty list."""
    return []


# ---------------------------------------------------------------------------
# Result processing utilities
# ---------------------------------------------------------------------------


def deduplicate_results(projects):
    """
    Deduplicate projects found across multiple keyword queries.
    Uses (service, instance, id) as the unique key.
    Merges the 'matched_keywords' lists for duplicates.
    """
    seen = {}
    for project in projects:
        key = (project.get("service", ""), project.get("instance", ""), str(project.get("id", "")))
        if key in seen:
            # Merge matched keywords
            existing_kws = set(seen[key].get("matched_keywords", []))
            new_kws = set(project.get("matched_keywords", []))
            seen[key]["matched_keywords"] = sorted(existing_kws | new_kws)
        else:
            seen[key] = project.copy()
    return list(seen.values())


def filter_by_polygon(projects, polygon):
    """
    Post-filter projects whose geometry intersects with the study-area polygon.
    
    For services that return project geometry (bounding box or centroid),
    we check intersection with the node polygon. Projects without geometry
    information are kept (benefit of the doubt).
    
    Parameters
    ----------
    projects : list of dict
        Each project dict may contain a 'geometry' key with a GeoJSON-like dict,
        or 'bbox' key with [west, south, east, north].
    polygon : shapely.geometry
        The study-area polygon.
    
    Returns
    -------
    list of dict
        Filtered projects.
    """
    if polygon is None:
        return projects

    try:
        from shapely.geometry import box, shape
    except ImportError:
        print("[acquisition] shapely not available — skipping polygon filter")
        return projects

    filtered = []
    for project in projects:
        # Try to extract geometry from the project
        geom = None
        if "geometry" in project and project["geometry"]:
            try:
                geom = shape(project["geometry"])
            except Exception:
                pass
        elif "bbox" in project and project["bbox"]:
            try:
                b = project["bbox"]
                geom = box(b[0], b[1], b[2], b[3])
            except Exception:
                pass

        if geom is not None:
            if geom.intersects(polygon):
                filtered.append(project)
        else:
            # No geometry info — keep the project
            filtered.append(project)

    return filtered


def fetch_project_bbox_from_detail(instance_url, project_id):
    """
    Fetch the aoiBBOX for a single Tasking Manager project from its detail endpoint.
    Returns [west, south, east, north] or None if unavailable.
    """
    base_api = SERVICE_API_ENDPOINTS.get(instance_url, instance_url.rstrip("/") + "/api/v2/")
    detail_url = base_api.rstrip("/") + f"/projects/{project_id}/"
    try:
        response = requests.get(detail_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("aoiBBOX")
    except Exception as e:
        print(f"[acquisition] Could not fetch detail for project {project_id}: {e}")
    return None


def fetch_all_tasking_manager(instance_url, bbox):
    """
    Fetch all Tasking Manager projects by paginating through the list endpoint.
    The list endpoint's bbox param is unreliable (ignored on some instances),
    so we fetch all projects and rely on downstream spatial filtering.
    Returns a list of parsed projects.
    """
    base_api = SERVICE_API_ENDPOINTS.get(instance_url, instance_url.rstrip("/") + "/api/v2/")
    
    all_projects = []
    page = 1
    while True:
        api_url = (
            base_api.rstrip("/")
            + "/projects/"
            + f"?orderBy=priority&orderByType=ASC"
            + f"&page={page}"
        )
        raw = query_to_json(api_url)
        if not raw:
            break
            
        parsed = parse_tasking_manager_results(raw, instance_url)
        all_projects.extend(parsed)
        
        pagination = raw.get("pagination", {})
        if not pagination.get("hasNext", False):
            break
            
        page += 1
        
    return all_projects

def fetch_all_maproulette(instance_url, bbox):
    """
    Fetch all MapRoulette challenges within a bounding box (ignoring keywords)
    by paginating through the API until exhausted.
    Returns a list of parsed projects.
    """
    base_api = SERVICE_API_ENDPOINTS.get(instance_url, instance_url.rstrip("/") + "/api/v2/")
    
    all_projects = []
    page = 0
    limit = 50
    while True:
        api_url = (
            base_api.rstrip("/")
            + "/challenges/extendedFind?"
            + f"bb={bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}"
            + "&cLocal=0&cStatus=3,4,0,-1&ce=true&cg=false"
            + f"&limit={limit}&order=DESC&page={page}&pe=true&sort=popularity"
        )
        raw = query_to_json(api_url)
        if not raw:
            break
            
        parsed = parse_maproulette_results(raw, instance_url)
        all_projects.extend(parsed)
        
        if len(raw) < limit:
            break
            
        page += 1
        
    return all_projects

def fetch_all_pic4review(instance_url, bbox):
    """Pic4Review stub — returns empty list."""
    print(f"[acquisition] Pic4Review: service nearly discontinued — skipping fetch")
    return []

# ---------------------------------------------------------------------------
# Service dispatcher
# ---------------------------------------------------------------------------

# Maps service names to their (query_API_fn, parse_fn) pairs
SERVICE_DISPATCH = {
    "Tasking Manager": {
        "query_api": query_tasking_manager_API,
        "query_browser": query_tasking_manager,
        "parse": parse_tasking_manager_results,
        "fetch_all": fetch_all_tasking_manager,
    },
    "MapRoulette": {
        "query_api": query_maproulette_API,
        "query_browser": query_maproulette,
        "parse": parse_maproulette_results,
        "fetch_all": fetch_all_maproulette,
    },
    "Pic4Review": {
        "query_api": query_pic4review_API,
        "query_browser": query_pic4review,
        "parse": parse_pic4review_results,
        "fetch_all": fetch_all_pic4review,
    },
}
