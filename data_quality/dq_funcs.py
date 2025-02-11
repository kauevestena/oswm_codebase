import sys

sys.path.append("oswm_codebase")

from functions import *
import csv

qc_mainpage_path = "quality_check/oswm_qc_main.html"
qc_externalpage_path = "quality_check/oswm_qc_external.html"

occurrence_per_feature = {k: {} for k in geom_type_dict.keys()}


def add_to_occurrences(category, id):
    if id in occurrence_per_feature[category]:
        occurrence_per_feature[category][id] += 1
    else:
        occurrence_per_feature[category][id] = 1


def gen_content_OSMI():
    inner_content = f"""
    TBD
    """
    content = details_item("OSMI", inner_content)

    return content


def gen_content_osmose():
    inner_content = f"""
    TBD
    """

    content = details_item("Osmose", inner_content)

    return content


def details_item(title, content):
    return f"""
    <details>
        <summary>{title}</summary>
        <div class="content">
            {content}
        </div>
    </details>
    """


def write_dq_topbar(active_index=1):

    active_handler = 'class="active"'

    entries_list = [
        f'<a href="{node_homepage_url}">Go to Node Home</a>',
        f'<a href="{node_homepage_url}{qc_mainpage_path}">OSWM DQ Main</a>',
        f'<a href="{node_homepage_url}{qc_externalpage_path}">External Providers</a>',
    ]

    entries = ""

    for index, entry in enumerate(entries_list):
        if index == active_index:
            entries += entry.replace("<a", f"<a {active_handler}") + "\n"
        else:
            entries += entry + "\n"

    topbar = f"""
    
    <div class="topnav" id="myTopnav">
        {entries}
        <a href="javascript:void(0);" class="icon" onclick="topnav()">
            <i class="fa fa-bars"></i>
         </a>
        
    </div>
    """

    return topbar
