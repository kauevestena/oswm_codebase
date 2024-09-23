python oswm_codebase/patch_readme_homepage.py || echo "patch_readme_homepage.py failed"; \

python oswm_codebase/other/wipers/wipe_changed_stuff.py || echo "wipe_changed_stuff.py failed"; \

python oswm_codebase/special_updates.py || echo "special_updates.py failed"