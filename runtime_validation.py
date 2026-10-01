#!/usr/bin/env python3
"""Check static browser dependencies without relying on the build-engine checkout.

Checks HTML assets, CSS URLs, ES module imports and literal new URL references.
Remote resources and dynamically constructed URLs require browser smoke tests.
"""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

PUBLIC_TREES = ("oswm_runtime", "statistics", "quality_check", "hub", "data/updates")
MODULE_URL = re.compile(
    r"\b(?:import\s*\(\s*|import\s+|from\s+)[\"']((?:\./|\.\./|/)[^\"'\n]+)[\"']"
)
META_URL = re.compile(r"new\s+URL\s*\(\s*[\"']([^\"'\n]+)[\"']\s*,\s*import\.meta\.url\s*\)")
CSS_URL = re.compile(r"\burl\(\s*[\"']?([^\s\)\"']+)[\"']?\s*\)", re.I)


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: list[str] = []
        self.code: list[str] = []
        self.in_code = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "img", "iframe", "source", "video", "audio"}:
            if attrs.get("src"):
                self.urls.append(attrs["src"])
        if tag == "link" and set(attrs.get("rel", "").split()) & {"stylesheet", "icon", "modulepreload"}:
            if attrs.get("href"):
                self.urls.append(attrs["href"])
        # Navigation into the runtime is also a runtime dependency.
        if tag == "a" and any(x in attrs.get("href", "") for x in ("oswm_runtime/", "oswm_codebase/")):
            self.urls.append(attrs["href"])
        self.urls.extend(CSS_URL.findall(attrs.get("style", "")))
        if tag in {"script", "style"}:
            self.in_code = True

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.in_code = False

    def handle_data(self, data):
        if self.in_code:
            self.code.append(data)


def validate_runtime(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    files = {root / name for name in ("index.html", "map.html") if (root / name).is_file()}
    for tree in PUBLIC_TREES:
        files.update(p for p in (root / tree).rglob("*") if p.suffix in {".html", ".js", ".css"})
    errors = []
    for source in sorted(files):
        text = source.read_text(encoding="utf-8")
        urls = []
        if source.suffix == ".html":
            parser = Assets()
            parser.feed(text)
            urls.extend(parser.urls)
            text = "\n".join(parser.code)
        # Ignore comments, including documentation-only example imports.
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
        urls.extend(MODULE_URL.findall(text))
        urls.extend(META_URL.findall(text))
        urls.extend(CSS_URL.findall(text))
        for url in sorted(set(urls)):
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc or not parsed.path or any(x in url for x in ("${", "{{", "<%")):
                continue
            path = unquote(parsed.path)
            target = (root / path.lstrip("/") if path.startswith("/") else source.parent / path).resolve()
            if "oswm_codebase" in Path(path).parts:
                reason = "legacy build-engine dependency"
            elif not target.is_relative_to(root):
                reason = "dependency escapes node root"
            elif not (target.is_file() or (path.endswith("/") and target.is_dir())):
                reason = "missing local dependency"
            else:
                continue
            errors.append({"page": source.relative_to(root).as_posix(), "url": url, "reason": reason})
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    errors = validate_runtime(args.root)
    print(json.dumps({"runtime_errors": errors}, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
