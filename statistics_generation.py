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


# generating the charts by using the specifications
with open(os.path.join(statistics_basepath,'failed_gen.txt'),'w+') as error_report:
    for category in charts_specs:
        for chart_spec in charts_specs[category]:
            try:
                spec = charts_specs[category][chart_spec]
                outpath = os.path.join(statistics_basepath,category,chart_spec+'.html')
                print('generating ',outpath)
                chart_obj = spec['function'](*spec['params'])
                chart_obj.save(outpath)
            except:
                print('failed ',chart_spec,' writing to report file at "statistics folder"')
                error_report.write(chart_spec+'\n')




# # to record data aging:
# record_datetime('Statistical Charts','data/last_updated.json')
# # generate the "report" of the updating info
# gen_updating_infotable_page('../data/data_updating.html','../data/last_updated.json')