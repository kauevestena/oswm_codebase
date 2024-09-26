
python oswm_codebase/getting_data.py || echo "getting_data.py failed"; \
# this structure assures independence on successful completion of the previous step

python oswm_codebase/filtering_adapting_data.py || echo "filtering_adapting_data.py failed"; \

python oswm_codebase/generation/vec_tiles_gen.py || echo "vec_tiles_gen.py failed"; \

python oswm_codebase/webmap/create_webmap_new.py || echo "create_webmap_new.py failed"; \

python oswm_codebase/data_quality/tag_values_checking.py || echo "tag_values_checking.py failed"; \

python oswm_codebase/data_quality/quality_check_compiling.py || echo "quality_check_compiling.py failed"; \

python oswm_codebase/dashboard/statistics_generation.py || echo "statistics_generation.py failed"