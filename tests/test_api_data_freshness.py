import json

from datahub.API.data_freshness import data_generation_html


def test_processing_timestamp_survives_later_page_or_pipeline_build(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "Data Pre-Processing": "2026-11-10T12:30:00Z",
        "Pipeline Success": "2026-11-11T13:00:00Z",
    }))
    result = data_generation_html(registry)
    assert 'Data generated: <time datetime="2026-11-10T12:30:00Z">' in result
    assert "2026-11-10 12:30:00 UTC" in result


def test_legacy_processing_timestamp_uses_node_timezone(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"Data Pre-Processing": "10/11/2026 09:30:00"}))
    assert "2026-11-10T12:30:00Z" in data_generation_html(registry, "America/Sao_Paulo")


def test_acquisition_fallback_is_labelled_accurately(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"Data Fetching": "2026-11-10T12:00:00Z"}))
    assert "Data acquired:" in data_generation_html(registry)


def test_unavailable_records_do_not_invent_a_generation_date(tmp_path):
    registry = tmp_path / "registry.json"
    assert data_generation_html(registry) == "Data generated: Not available"
    for content in ('broken', '[]', '{"Data Pre-Processing": "invalid"}'):
        registry.write_text(content)
        assert data_generation_html(registry) == "Data generated: Not available"
