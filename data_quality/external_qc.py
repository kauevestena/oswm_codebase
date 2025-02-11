from dq_funcs import *
from quality_dicts import *
from functions import *

# register providers and the functions:
PROVIDERS = {
    "Osmose": gen_content_osmose,
    "OSMI": gen_content_OSMI,
}


main_content = ""

for provider in PROVIDERS:
    main_content += f"""

    <!--- {provider} content-->
    {PROVIDERS[provider]()}

    """

topbar = write_dq_topbar(2)


external_qc_page = f"""

<!DOCTYPE html>

<!-- thx, w3schools, this page was made following their tutorial!! -->

<html lang="en">
<head>

<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
   
   
{styles_dq}

{js_functions_dq}	

<title>OSWM DQ: Ext. Providers</title>

<link rel="icon" type="image/x-icon" href="https://kauevestena.github.io/oswm_codebase/assets/homepage/favicon_homepage.png">

</head>

<body>

{topbar}

<h2 style="text-align: center;">OpenSidewalkMap DQ: External Providers</h2>

<p> Page in progress... </p>

<p style="font-size: smaller"> This page holds DQ detections or visualizations from third-party providers, click to expand!</p>


{main_content}

<h6> Do you know/have any DQ tool that can be integrated here? please write and issue at <a href="{codebase_issues_url}">repository "issues" section</h6>

</body>
</html> 

"""


str_to_file(external_qc_page, qc_externalpage_path)
