"""
  setup the variables for your city/territory:

  all of them are mandatory!!
"""

# Full city name, it may contain special characters, spaces...
# It can be also the name of a neighborhood if is such a big city or you just want a node
# Sometimes being more specific can help, so if you for example want the city of Salvador (Brazil)
# you can use 'Salvador, Brazil', since 'Salvador' probably would return "El Salvador", the country
CITY_NAME = 'Curitiba'

# simple name, spaces must be replaced by underscores, no special characters, all in lowercase
CITY_SHORTNAME = 'curitiba'

# username, for adresses
USERNAME = 'kauevestena'

# repository name, for many weblink references:
REPO_NAME = 'opensidewalkmap_beta'

# BOUNDING BOXES
# A good tool to find them is: bboxfinder.com
# # entire city: 
BOUNDING_BOX = (
    -25.6450101000000004, # SOUTHERNMOST LATITUDE
    -49.3891399999999976, # WESTERNMOST  LONGITUDE
    -25.3467008999999983, # NORTHERNMOST LATITUDE
    -49.1843181999999999  # EASTERNMOST  LONGITUDE
    )


### MORE DELICATE ONES: (leave unchanged by default)

# TAGS FOR ADDITIONAL FOOTWAYS
# you can check the reason behind those default ones at: https://kauevestena.github.io/opensidewalkmap/information/other_footways.html

# depending on local rules, the other types of footways can differ, so you migh tune the options
OTHER_FOOTWAY_RULES = {'highway':['steps','living_street','pedestrian','track','path'],'foot':['yes','designated','permissive'],'footway': ['alley','path','yes']}

# since we download all features containing the tags of the previous rule-set, if there's another tag hierarchically above, we should exclude those features:
OTHER_FOOTWAY_EXCLUSION_RULES = {'highway': ['trunk','motorway','primary','trunk_link','motorway_link','primary_link']}