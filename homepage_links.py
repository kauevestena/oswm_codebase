"""Keep central project navigation separate from node-local navigation."""

import re
from urllib.parse import urlsplit

INDEX_MAP_URL = "https://kauevestena.github.io/opensidewalkmap/"
_HREF = re.compile(r"(?P<prefix>\bhref\s*=\s*)(?P<quote>[\"'])(?P<url>.*?)(?P=quote)", re.I)


def repair_homepage_links(html: str) -> str:
    """Repair legacy GitHub Pages links without rewriting unrelated hosts/assets."""
    def replace(match):
        url = urlsplit(match["url"])
        host = (url.hostname or "").lower()
        if not host.endswith(".github.io"):
            return match[0]
        if url.path.rstrip("/") == "/opensidewalkmap":
            target = INDEX_MAP_URL
        elif url.path.endswith("/data/updates/index.html"):
            target = "data/updates/index.html"
        else:
            return match[0]
        if url.query:
            target += "?" + url.query
        if url.fragment:
            target += "#" + url.fragment
        return match["prefix"] + match["quote"] + target + match["quote"]

    return _HREF.sub(replace, html)
