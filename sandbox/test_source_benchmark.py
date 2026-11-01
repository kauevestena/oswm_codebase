"""Regression checks for measured response bytes and source-ID provenance."""
import gzip
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zlib

import requests


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / filename)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


b = module("source_benchmark_tested", "source_benchmark.py")
o = module("overture_probe_tested", "overture_probe.py")


class Raw:
    def __init__(self, encoded, fail=False):
        self.encoded, self.fail = encoded, fail

    def stream(self, amount, decode_content=False):
        assert decode_content is False
        yield self.encoded[:5]
        if self.fail:
            raise requests.ReadTimeout("partial stream")
        yield self.encoded[5:]

    def tell(self): return 0  # real chunked responses can report zero here
    def close(self): pass


def sender(encoded, encoding="identity", status=200, fail=False):
    def send(session, request, **kwargs):
        assert kwargs["stream"] is True
        response = requests.Response()
        response.status_code, response.request, response.url = status, request, request.url
        response.headers = {"Content-Encoding": encoding}
        response.raw = Raw(encoded, fail)
        return response
    return send


class MeterTests(unittest.TestCase):
    def test_chunked_gzip_counts_encoded_bytes_with_zero_tell(self):
        plain = b'{"elements":[]}'
        encoded = gzip.compress(plain)
        with patch.object(requests.Session, "send", sender(encoded, "gzip")):
            with b.Meter() as meter:
                response = requests.get("https://example.org/body")
        self.assertEqual(response.content, plain)
        self.assertEqual(meter.summary()["encoded_response_body_bytes"], len(encoded))
        self.assertEqual(meter.summary()["decoded_response_body_bytes"], len(plain))
        self.assertFalse(meter.summary()["byte_total_is_lower_bound"])

    def test_deflate_and_identity(self):
        plain = b"one two three four five"
        for body, encoding in [(plain, "identity"), (zlib.compress(plain), "deflate")]:
            with self.subTest(encoding=encoding), patch.object(requests.Session, "send", sender(body, encoding)):
                with b.Meter() as meter:
                    response = requests.get("https://example.org/body")
                self.assertEqual(response.content, plain)
                self.assertEqual(meter.summary()["encoded_response_body_bytes"], len(body))

    def test_http_failure_body_is_counted_without_recursive_retry(self):
        body = b"rate limited"
        with patch.object(requests.Session, "send", sender(body, status=429)):
            with b.Meter() as meter:
                with self.assertRaises(requests.HTTPError):
                    requests.get("https://example.org/body")
        self.assertEqual(meter.summary()["encoded_response_body_bytes"], len(body))
        self.assertEqual(meter.summary()["http_requests"], 1)

    def test_partial_timeout_is_a_lower_bound(self):
        with patch.object(requests.Session, "send", sender(b"partial body", fail=True)):
            with b.Meter() as meter:
                with self.assertRaises(requests.ReadTimeout):
                    requests.get("https://example.org/body")
        self.assertEqual(meter.summary()["encoded_response_body_bytes"], 5)
        self.assertTrue(meter.summary()["byte_total_is_lower_bound"])

    def test_identical_interpreter_retry_has_a_bound(self):
        with patch.object(requests.Session, "send", sender(b'{"elements":[]}')):
            with b.Meter() as meter:
                requests.post("https://example.org/interpreter", data={"data": "query"})
                with self.assertRaises(RuntimeError):
                    requests.post("https://example.org/interpreter", data={"data": "query"})
        self.assertEqual(meter.summary()["interpreter_requests"], 1)


class OvertureTests(unittest.TestCase):
    def test_attribute_provenance_is_not_an_entity_identity(self):
        row = {"sources": [
            {"dataset": "OpenStreetMap", "record_id": "w12@3", "property": ""},
            {"dataset": "OpenStreetMap", "record_id": "r14@8", "property": "/routes"},
            {"dataset": "OpenStreetMap", "record_id": "n15@1", "property": "/geometry"},
            {"dataset": "Other", "record_id": "w16@3", "property": ""},
        ]}
        self.assertEqual(o.source_ids(row), {"way:12", "node:15"})

    def test_range_reader_reuses_prefetched_bytes(self):
        class Transport:
            def __init__(self): self.calls = []
            def get(self, url, start, end):
                self.calls.append((start, end))
                return b"0123456789"[start:end]
        transport = Transport()
        raw = o.RangeFile(transport, "https://example.org/data", 10)
        raw.prefetch(2, 8)
        raw.seek(3)
        self.assertEqual(raw.read(3), b"345")
        self.assertEqual(transport.calls, [(2, 8)])


if __name__ == "__main__": unittest.main()
