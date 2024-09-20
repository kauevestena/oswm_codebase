from constants import *

css_class_ref = "media_image responsive"
inner_div_class_ref = "media__body"
outer_div_class_ref = "media"
img_css_class_ref = "media_image responsive"
assets_base_path = f"{codebase_homepage}assets/"
assets_homepage_path = f"{codebase_homepage}assets/homepage/"
assets_map_symbols_path = f"{codebase_homepage}assets/map_symbols/"

modules_metadata = {
    "webmap": {
        "url": f"{node_homepage_url}map.html",
        "img_src": f"{assets_homepage_path}oswm_webmap_img.png",
        "text": "Webmap",
    },
    "routing": {
        "url": "https://kauevestena.github.io/opensidewalkmap_beta/routing.html",
        "img_src": f"{assets_homepage_path}oswm_route_img.png",
        "text": "Optimized Routing",
    },
    "dashboard": {
        "url": f"{node_homepage_url}statistics/index.html",
        "img_src": f"{assets_homepage_path}oswm_statistics_img.png",
        "text": "Dashboard",
    },
    "data_quality": {
        "url": f"{node_homepage_url}quality_check/oswm_qc_main.html",
        "img_src": f"{assets_homepage_path}oswm_quality_check_img.png",
        "text": "Data Quality Tool",
    },
}

modules_as_str = ""

for modulename in modules_metadata:
    # mapping for short sake:
    url = modules_metadata[modulename]["url"]
    img_src = modules_metadata[modulename]["img_src"]
    text = modules_metadata[modulename]["text"]

    modules_as_str += f"""
    
    <div class="{outer_div_class_ref}">


    <a href="{url}">
        
        <img title="OSWM {modulename}" 
        src="{img_src}" 
        alt="OSWM {modulename} image" class="{img_css_class_ref}">
    
        <!-- THX: https://jsfiddle.net/Venugopal/e0u4sow1/1/ -->

        <div class="{inner_div_class_ref}">

            <h1>{text}</h1>

        </div>

    </a> 

    </div>
    <p></p>
        
    """
