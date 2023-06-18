from statistics_funcs import *

# reading data:

gdfs_dict = {}

for category in paths_dict['data']:
    gdfs_dict[category] = gpd.read_file(paths_dict['data'][category])

    if geom_type_dict[category] == 'LineString':
        create_length_field(gdfs_dict[category])

    create_folder_if_not_exists(os.path.join('statistics',category))


first_chart = create_barchartV2(gdfs_dict['sidewalks'],'surface','Sidewalks Surface Type')

print(first_chart.to_json())

first_chart.save('tests/sample_chart.json')
first_chart.save('tests/sample_chart.html')