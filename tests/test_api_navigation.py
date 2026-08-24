from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_api_navigation_targets_node_root():
    source = (ROOT / "datahub" / "API" / "generate_api.py").read_text(
        encoding="utf-8"
    )

    assert 'href="../../index.html" class="btn btn-secondary">Node Home<' in source
    assert 'href="../../map.html" class="btn btn-primary">Open Webmap<' in source
    assert "../../../index.html" not in source
    assert "../../../map.html" not in source
