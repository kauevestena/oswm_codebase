from pathlib import Path
import re
import runpy
import sys
from types import ModuleType
from unittest.mock import patch

from homepage_links import INDEX_MAP_URL, repair_homepage_links

ROOT = Path(__file__).resolve().parents[1]


def test_central_and_local_destinations_are_separate():
    for owner in ('kauevestena', 'opensidewalkmap', 'another-node-owner'):
        html = f'''<a href="https://{owner}.github.io/opensidewalkmap/">Index map</a>
<a href='https://{owner}.github.io/opensidewalkmap_beta/data/updates/index.html'>Updates</a>
<img src="https://kauevestena.github.io/oswm_codebase/assets/background.jpg">
<a href="https://external.example/opensidewalkmap/">External</a>'''
        result = repair_homepage_links(html)
        assert f'href="{INDEX_MAP_URL}"' in result
        assert "href='data/updates/index.html'" in result
        assert 'src="https://kauevestena.github.io/oswm_codebase/assets/background.jpg"' in result
        assert 'href="https://external.example/opensidewalkmap/"' in result
        assert repair_homepage_links(result) == result


def test_query_fragment_and_local_links_are_preserved():
    html = '<a HREF = "https://opensidewalkmap.github.io/opensidewalkmap?city=oslo#map">Map</a>'
    assert INDEX_MAP_URL + '?city=oslo#map' in repair_homepage_links(html)
    local = '<a href="data/updates/index.html">Updates</a><a href="map.html">Map</a>'
    assert repair_homepage_links(local) == local


def test_setup_patcher_never_rewrites_unrelated_github_hosts(tmp_path):
    homepage = tmp_path / 'index.html'
    readme = tmp_path / 'README.md'
    homepage.write_text('''<a href="https://kauevestena.github.io/opensidewalkmap/">Map</a>
<a href="https://kauevestena.github.io/opensidewalkmap_beta/data/updates/index.html">Updates</a>
<a href="https://someone.github.io/documentation/">Documentation</a>
<!--CITYNAME INSERTION-->Curitiba<!--CITYNAME INSERTION-->
<!--MODULES INSERTION POINT-->old<!--MODULES INSERTION POINT-->''')
    readme.write_text('<CITYNAME>Curitiba<CITYNAME>')
    class Handler:
        def __init__(self, path):
            self.path = path
            self.content = path.read_text()
        def simple_replace(self, old, new): self.content = self.content.replace(old, new)
        def rewrite(self): self.path.write_text(self.content)
    functions = ModuleType('functions')
    functions.fileAsStrHandler = Handler
    functions.node_home_path = homepage
    functions.readme_path = readme
    functions.USERNAME = 'opensidewalkmap'
    functions.REPO_NAME = 'milan'
    functions.CITY_NAME = 'Milan'
    functions.find_between_strings = lambda content, start, end, **kwargs: re.findall(
        re.escape(start) + '(.*?)' + re.escape(end), content, flags=re.S)
    modules = ModuleType('modules_info')
    modules.modules_as_str = '<p>Modules</p>'
    with patch.dict(sys.modules, functions=functions, modules_info=modules):
        runpy.run_path(str(ROOT / 'patch_readme_homepage.py'))
    result = homepage.read_text()
    assert INDEX_MAP_URL in result
    assert 'href="data/updates/index.html"' in result
    assert 'https://someone.github.io/documentation/' in result
    assert '<!--CITYNAME INSERTION-->Milan<!--CITYNAME INSERTION-->' in result
    assert '<p>Modules</p>' in result
    assert '<CITYNAME>Milan<CITYNAME>' == readme.read_text()
