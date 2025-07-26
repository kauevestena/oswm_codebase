CITY_NAME = "Faketown"
BOUNDING_BOX = [0, 0, 1, 1]
USERNAME = "testuser"
REPO_NAME = "test-repo"

# Global zoom levels
MIN_ZOOM = 10
MAX_ZOOM = 22

# Data processing parameters
MAX_RADIUS_CUTOFF = 50
DEFAULT_SCORE = 0.5
DEFAULT_MISSING_DAY = 9
DEFAULT_MISSING_MONTH = 8
DEFAULT_MISSING_YEAR = 2004

# Tagging rules
OTHER_FOOTWAY_RULES = {}
OTHER_FOOTWAY_EXCLUSION_RULES = {}
other_footways_subcatecories = {}

# Misspelled values correction
WRONG_MISSPELLED_VALUES = {
    "sidewalks": {
        "smoothness": {"concrete:plates": "?"},
        "surface": {
            "betão": "?",
            "Petit_Pavê": "sett",
            "porcelain tiles": "ceramic:tiles",
        },
    },
    "kerbs": {},
    "crossings": {},
    "other_footways": {},
}
