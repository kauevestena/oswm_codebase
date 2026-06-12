import sys

# Ensure the parent `datahub` directory is on sys.path so `dh_lib` can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dh_lib import *


# keywords that are going to be used to search for projects in the supported platforms:
SEARCH_KEYWORDS = [
    "oswm",
    "OpenSidewalkMap",
    "sidewalk",
    "pedestrian",
    "walk",
    "accessibility",
    "kerb",
    "tactile paving",
    "crossing",
    "footway",
    "footpath",
    "stairway",
]

# services supported for project acquisition (names and website links, meaning instances):
SUPPORTED_SERVICES = {
    "Tasking Manager": [
        "https://tasks.hotosm.org/",
        "https://tasks.teachosm.org/",
        "https://tasks.mapwith.ai/",
    ],
    # "Pic4Review": ["https://pic4review.pavie.info/#/"], # pic4review is almost discontinued these days
    "MapRoulette": ["https://maproulette.org/"],
}


# bounding box shall come from "BOUNDING_BOX" in config.py


# now implementing the query functions for each platform:


def query_maproulette(instance_url, bbox, queryworld):
    # sample query URL:
    # https://maproulette.org/browse/challenges?challengeSearch=-49.4312724%2C-25.2695963%2C-49.1112724%2C-25.5895963&location=intersectingMapBounds&query=sidewalk

    query_url = (
        instance_url
        + "/browse/challenges?challengeSearch="
        + f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}"
        + "&location=intersectingMapBounds"
        + f"&query={queryworld}"
    )
    return query_url


def query_maproulette_API(instance_url, bbox, queryword):
    # sample successfull API call:
    # https://maproulette.org/api/v2/challenges/extendedFind?bb=2.224122,48.8155755,2.4697602,48.902156&cLocal=0&cStatus=3,4,0,-1&ce=true&cg=false&cs=sidewalk&limit=50&order=DESC&page=0&pe=true&sort=popularity
    # fundamental parameters are bounding box (bb) and search keyword (cs)
    api_url = (
        instance_url
        + "/api/v2/challenges/extendedFind?"
        + f"bb={bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}"
        + "&cLocal=0&cStatus=3,4,0,-1&ce=true&cg=false"
        + f"&cs={queryword}"
        + "&limit=50&order=DESC&page=0&pe=true&sort=popularity"
    )
    return api_url


def query_to_json(api_call_url):
    response = requests.get(api_call_url)
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        print(f"API call failed with status code: {response.status_code}")
        return None
