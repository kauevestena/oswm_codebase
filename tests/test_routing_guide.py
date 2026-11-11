from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json

from routing.generate_profile_guide import generate
from routing.generate_oswmg_guide import generate as generate_format_guide, worked_example
from routing.profile_rules import ROUTING_PROFILES
from routing.profile_validation import profile_ruleset_hash
from runtime_assets import publish_runtime


ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            assert attrs["id"] not in self.ids, "duplicate HTML id"
            self.ids.add(attrs["id"])
        if tag == "a":
            self.hrefs.append(attrs.get("href", ""))


def test_published_guide_matches_current_policy_and_links():
    content = generate()
    assert (ROOT / "routing/profile_guide.html").read_text(encoding="utf-8") == content
    assert profile_ruleset_hash(ROUTING_PROFILES) in content
    parsed = Links()
    parsed.feed(content)
    for profile_id in ROUTING_PROFILES:
        assert f"profile-{profile_id}" in parsed.ids
    for href in parsed.hrefs:
        if href.startswith("#"):
            assert href[1:] in parsed.ids
    assert "isochrones" in parsed.ids
    assert "routing_demo.html" in parsed.hrefs
    assert "oswmg_guide.html" in parsed.hrefs


def test_format_guide_matches_writer_and_has_working_local_links():
    content = generate_format_guide()
    assert (ROOT / "routing/oswmg_guide.html").read_text(encoding="utf-8") == content
    parsed = Links()
    parsed.feed(content)
    assert "profile_guide.html" in parsed.hrefs
    for href in parsed.hrefs:
        if href.startswith("#"):
            assert href[1:] in parsed.ids
    example = worked_example()
    header = example["header"]
    assert example["arrays"]["adjacency_offsets"] == [0, 1, 3, 4]
    assert example["arrays"]["targets"] == [1, 0, 2, 1]
    assert example["arrays"]["weights"][-1] == float("inf")
    size = (header["header_bytes"] + 16 * header["node_count"]
            + 4 * (header["node_count"] + 1) + 4 * header["directed_edge_count"]
            + 4 * header["profile_count"] * header["directed_edge_count"]
            + 8 * header["segment_count"] + 4 * (header["grid_cols"] * header["grid_rows"] + 1)
            + 4 * header["cell_membership_count"])
    assert example["audit"]["byte_size"] == size


def test_runtime_publication_includes_the_guide(tmp_path):
    publish_runtime(tmp_path, ROOT)
    guide = tmp_path / "oswm_runtime/routing/profile_guide.html"
    assert guide.read_text(encoding="utf-8") == generate()
    assert (tmp_path / "oswm_runtime/routing/oswmg_guide.html").read_text(encoding="utf-8") == generate_format_guide()
    page = Links()
    page.feed((tmp_path / "oswm_runtime/routing/routing_demo.html").read_text(encoding="utf-8"))
    assert any(href.startswith("profile_guide.html") for href in page.hrefs)


def test_recorded_benchmark_identifies_code_and_pinned_dependencies():
    report = json.loads((ROOT / "routing/benchmark_results.json").read_text())
    lock = json.loads((ROOT / "package-lock.json").read_text())
    for filename, key in (
        ("routing/routing_worker.js", "worker_sha256"),
        ("benchmarks/routing_benchmark.mjs", "benchmark_script_sha256"),
    ):
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == report[key]
    for package, version in report["versions"].items():
        assert lock["packages"][f"node_modules/{package}"]["version"] == version
    ngraph = next(engine for engine in report["engines"] if engine["engine"] == "ngraph.path")
    assert all(row["routing_mismatches"] == 0 for row in ngraph["profiles"])
