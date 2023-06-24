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

generated_list_dict = {}
charts_titles = {}

# generating the charts by using the specifications
with open(os.path.join(statistics_basepath,'failed_gen.txt'),'w+') as error_report:
    for category in charts_specs:
        generated_list_dict[category] = []
        for chart_spec in charts_specs[category]:
            try:
                spec = charts_specs[category][chart_spec]
                outpath = os.path.join(statistics_basepath,category,chart_spec+'.html')

                # remove_if_exists(outpath)

                print('generating ',outpath)
                chart_obj = spec['function'](*spec['params'])
                chart_obj.save(outpath)

                generated_list_dict[category].append(outpath)
                charts_titles[outpath] = spec['title']
            except Exception as e:
                print('failed ',chart_spec,' writing to report file at "statistics folder"')
                error_report.write(chart_spec+'\n')

# the topbar for each category 
topbar = f"""
    
    <div class="topnav" id="stTopnav">
        <a href="{node_homepage_url}" class="active">Home</a>
    """


for category in generated_list_dict:
    category_homepage = get_url(generated_list_dict[category][0])

    topbar += f'<a href="{category_homepage}">{category.capitalize()} Charts</a>\n'


topbar += """
   <a href="javascript:void(0);" class="icon" onclick="responsiveTopNav()">
     <i class="fa fa-bars"></i>
   </a>
 </div>
 
 """

sidebar_begin = '<div class="sidebar">\n'

category_bars = {}

full_url_dict = {}

for category in generated_list_dict:
    # url_list = [get_url(rel_path) for rel_path in generated_list_dict[category]]

    for rel_path in generated_list_dict[category]:
        full_url_dict[rel_path] = get_url(rel_path)

    category_bars[category] = topbar + sidebar_begin

    for rel_path in full_url_dict:
        category_bars[category] += f'  <a href="{full_url_dict[rel_path]}">{charts_titles[rel_path]}</a>\n'


    category_bars[category] += '</div>\n\n'

# iterating again to modify pages only once:
for category in generated_list_dict:
    for i,rel_path in enumerate(generated_list_dict[category]):
        fileObj = fileAsStrHandler(rel_path)

        for insertpoint in global_insertions:
            fileObj.simple_replace(insertpoint,global_insertions[insertpoint])

        for exclusion_specs in global_exclusions:
            to_remove = find_between_strings(fileObj.content,*exclusion_specs['points'],include_linebreaks=exclusion_specs['multiline'])
            for removable in to_remove:
                fileObj.simple_replace(exclusion_specs['points'][0]+removable+exclusion_specs['points'][1])

        fileObj.simple_replace('<head>','<head>\n'+category_bars[category])

        fileObj.rewrite()

        if i == 0 and category == 'sidewalks':
            fileObj.write_to_another_path(os.path.join(statistics_basepath,'index.html'))


# to record data aging:
record_datetime('Statistical Charts')
# generate the "report" of the updating info
gen_updating_infotable_page(node_page_url=node_homepage_url)
