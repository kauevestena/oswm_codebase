from statistics_funcs import *

gdfs_dict = {}
updating_dicts = {}


for category in paths_dict['data']:
    gdfs_dict[category] = gpd.read_file(paths_dict['data'][category])

    updating_dicts[category] = pd.read_json(paths_dict['versioning'][category])


charts_specs = {
    'sidewalks': {
        'sidewalks_smoothness_x_surface': {
            'function': double_scatter_bar,
            'params': (
                gdfs_dict[
                    'sidewalks'
                ],
                'Surface x Smoothness (sidewalks)',
                'surface',
                'smoothness',
                None,
                'count()',
                'surface',
                'smoothness',
                'length(km)',
                24,
                [
                    'element_type',
                    'id'
                ]
            ),
            'title': 'Surface x Smoothness',
        },
        'sidewalks_surface': {
            'function': create_barchartV2,
            'params': (
                gdfs_dict[
                    'sidewalks'
                ],
                'surface',
                'Sidewalks Surface Type',
                ' type',
                24
            ),
            'title': 'Surface Type',
        },
        'sidewalks_smoothness': {
            'function': create_barchartV2,
            'params': (
                gdfs_dict[
                    'sidewalks'
                ],
                'smoothness',
                'Sidewalks Smoothness Condition',
                ' type',
                24
            ),
            'title': 'Smoothness Condition',
        },
        'sidewalks_tactile_paving': {
            'function': create_barchartV2,
            'params': (
                gdfs_dict[
                    'sidewalks'
                ],
                'tactile_paving',
                'Sidewalks Tactile Paving Presence',
                ' type',
                24
            ),
            'title': 'Tactile Paving P.',
        },
        'sidewalks_width': {
            'function': create_barchartV2,
            'params': (
                gdfs_dict[
                    'sidewalks'
                ],
                'tactile_paving',
                'Sidewalks Width Values',
                ' type',
                24
            ),
            'title': 'Width Values',
        },
        'sidewalks_incline': {
            'function': create_barchartV2,
            'params': (
                gdfs_dict[
                    'sidewalks'
                ],
                'incline',
                'Sidewalks Incline Values',
                ' type',
                24
            ),
            'title': 'Incline Values',
        },
        'sidewalks_survey_year': {
            'function': create_barchart,
            'params': (
                gdfs_dict[
                    'sidewalks'
                ],
                'Year of Survey',
                'Year of Survey Image (sidewalks)',
            ),
            'title': 'Year of Survey Image',
        },
        'sidewalks_yr_moth_update': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'sidewalks'
                ],
                'year_month',
                'Year and Month Of Update (Sidewalks)',
                ' type',
                24,
                'count',
                '-x',
            ),
            'title': 'Year and Month Of Update',
        },
        'sidewalks_number_revisions': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'sidewalks'
                ],
                'n_revs',
                'Year and Month Of Update (Sidewalks)',
                ' type',
                24,
                'count',
                '-x',
            ),
            'title': 'Number Of Revisions',
        },
    },
    'crossings': {
        'crossing_types': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'crossings'
                ],
                'crossing',
                'Crossing Type',
            ),
            'title': 'Crossing Type',
        },
        'crossing_surface': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'crossings'
                ],
                'surface',
                'Crossing Surface',
            ),
            'title': 'Crossing Surface',
        },
        'crossings_smoothness_x_surface': {
            'function': double_scatter_bar,
            'params': (
                gdfs_dict[
                    'crossings'
                ],
                'Surface x Smoothness (crossings)',
                'surface',
                'smoothness',
                None,
                'count()',
                'surface',
                'smoothness',
                'crossing',
                24,
                [
                    'element_type',
                    'id'
                ]
            ),
            'title': 'Surface x Smoothness',
        },
        'crossings_survey_year': {
            'function': create_barchart,
            'params': (
                gdfs_dict[
                    'crossings'
                ],
                'Year of Survey',
                'Year of Survey Image (crossings)',
            ),
            'title': 'Year of Survey Image',
        },
        'crossings_yr_moth_update': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'crossings'
                ],
                'year_month',
                'Year and Month Of Update (Crossings)',
                ' type',
                24,
                'count',
                '-x',
            ),
            'title': 'Year and Month Of Update',
        },
        'crossings_number_revisions': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'crossings'
                ],
                'n_revs',
                'Year and Month Of Update (crossings)',
                ' type',
                24,
                'count',
                '-x',
            ),
            'title': 'Number Of Revisions',
        },
    },
    'kerbs': {
        'crossings_smoothness_x_surface': {
            'function': double_scatter_bar,
            'params': (
                gdfs_dict[
                    'kerbs'
                ],
                'Kerb x Tactile Paving x Wheelchair Acess.',
                'kerb',
                'tactile_paving',
                None,
                'count()',
                'kerb',
                'tactile_paving',
                'wheelchair',
                24,
                [
                    'element_type',
                    'id'
                ]
            ),
            'title': 'Surface x Smoothness',
        },
        'kerb_types': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'kerbs'
                ],
                'kerbs',
                'Kerb Type',
            ),
            'title': 'Kerb Type',
        },
        'kerb_tactile_paving': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'kerbs'
                ],
                'tactile_paving',
                'Kerb Tactile Paving Presence',
            ),
            'title': 'Tactile Paving Presence',
        },
        'kerb_wheelchair_access': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'kerbs'
                ],
                'wheelchair',
                'Kerb Wheelchair Acessibility',
            ),
            'title': 'Wheelchair Acessibility',
        },
        'kerbs_survey_year': {
            'function': create_barchart,
            'params': (
                gdfs_dict[
                    'kerbs'
                ],
                'Year of Survey',
                'Year of Survey Image (kerbs)',
            ),
            'title': 'Year of Survey Image',
        },
        'kerbs_yr_moth_update': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'kerbs'
                ],
                'year_month',
                'Year and Month Of Update (Kerbs)',
                ' type',
                24,
                'count',
                '-x',
            ),
            'title': 'Year and Month Of Update',
        },
        'kerbs_number_revisions': {
            'function': create_barchart,
            'params': (
                updating_dicts[
                    'kerbs'
                ],
                'n_revs',
                'Year and Month Of Update (Kerbs)',
                ' type',
                24,
                'count',
                '-x',
            ),
            'title': 'Number Of Revisions',
        },
    },
}

global_insertions = {
    '<head>' : """

    <head>
    
     <link rel="stylesheet" href="../../oswm_codebase/assets/styles/stats_styles.css">
    <script src="../../oswm_codebase/assets/webscripts/stats_funcs.js"></script>
    
    """,
}

global_exclusions = [
    {
        'points' : ['<style>','</style>'],
        'multiline' : True
    }
]