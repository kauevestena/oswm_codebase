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

js_functions = f"""
<script>
    {file_as_string('oswm_codebase/assets/js_functions/topbar.js')}
    
</script>
"""

styles = f"""
<style>
    {file_as_string('oswm_codebase/assets/styles/topnav_styles.css')}
    {file_as_string('oswm_codebase/assets/styles/accordion.css')}
</style>
"""

external_qc_page = f"""

<!DOCTYPE html>

<!-- thx, w3schools, this page was made following their tutorial!! -->

<html lang="en">
<head>

<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
   
   
{styles}

{js_functions}	

<title>OSWM DQ: Ext. Providers</title>

<link rel="icon" type="image/x-icon" href="https://kauevestena.github.io/oswm_codebase/assets/homepage/favicon_homepage.png">

</head>

<body>

{topbar}

<h1>OpenSidewalkMap DQ: External Providers</h1>

<p> Page in progress... </p>

{main_content}

</body>
</html> 

"""


str_to_file(external_qc_page, qc_externalpage_path)
