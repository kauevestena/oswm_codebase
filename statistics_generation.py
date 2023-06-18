from statistics_specs import *
# reading data:


for category in paths_dict['data']:

    # creating additional fields

    if geom_type_dict[category] == 'LineString':
        create_length_field(gdfs_dict[category])
        create_weblink_field(gdfs_dict[category])
    elif geom_type_dict[category] == 'Point':
        create_weblink_field(gdfs_dict[category],'Point')

    gdfs_dict[category]['Year of Survey'] = gdfs_dict[category]['survey:date'].apply(get_year_surveydate)


    create_folder_if_not_exists(os.path.join('statistics',category))

    # updating info:
    updating_dicts[category]['month_year'] = updating_dicts[category]['rev_month'].map("{:02d}".format) + '_' + updating_dicts[category]['rev_year'].astype(str)

    updating_dicts[category]['year_month'] =  updating_dicts[category]['rev_year'].astype(str) + "_" + updating_dicts[category]['rev_month'].map("{:02d}".format)


    updating_dicts[category].sort_values('year_month',inplace=True)


first_chart = create_barchartV2(gdfs_dict['sidewalks'],'surface','Sidewalks Surface Type')


first_chart.save('tests/sample_chart2.html')




# to record data aging:
record_datetime('Statistical Charts','data/last_updated.json')
# generate the "report" of the updating info
gen_updating_infotable_page('../data/data_updating.html','../data/last_updated.json')