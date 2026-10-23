"""Offline gzip/identity transport controls; never proof of provider retrieval."""
from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.m1_collect import (
    HTTPResult, CollectionFailure, _fetch_once, collect, collect_to_new_directory,
    decode_http_body, wiki_endpoint,
)
from tools.m1_bundle_verify import verify_bundle, make_manifest_for_complete
from tools.m1_identity_panel import PanelError, canonical_bytes, load_panel
from tools.m1_source_verify import MAX_BODY


class Response:
    status = 200
    def __init__(self, body, encoding="gzip", length=None):
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        self.headers["Content-Encoding"] = encoding
        self.headers["Content-Length"] = str(len(body) if length is None else length)
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit): return self.body[:limit]


class GzipTests(unittest.TestCase):
    def setUp(self):
        self.raw = canonical_bytes({"batchcomplete": True, "query": {"pages": [{"pageid": 101,
            "ns": 0, "title": "Synthetic example " + ("A" * 80), "pageprops": {"wikibase_item": "Q101"}}]}})
        self.wire = gzip.compress(self.raw, mtime=0)
        self.seed = {"schema_version": "dayflare.identity-seeds.v1", "panel_id": "synthetic.gzip",
            "selected_at": "2026-10-21", "pages": [{"page_ref": {"project": "en.wikipedia", "page_id": 101},
                "topic_id": "synthetic.example", "subject": "science", "relation": "ambiguous"}]}
        self.now = lambda: datetime(2026, 10, 22, tzinfo=timezone.utc)

    def result(self, encoding="gzip"):
        body = self.wire if encoding == "gzip" else self.raw
        return HTTPResult(200, self.raw, len(body), hashlib.sha256(body).hexdigest(), encoding)

    def fetch_response(self, response):
        calls = []
        class Opener:
            def open(self, request, timeout):
                calls.append(request)
                return response
        with patch("tools.m1_collect.build_opener", return_value=Opener()):
            value = _fetch_once(wiki_endpoint("en.wikipedia", 101))
        self.assertEqual(calls[0].get_header("Accept-encoding"), "gzip")
        return value

    def test_gzip_records_received_and_decoded_representations(self):
        result = self.fetch_response(Response(self.wire))
        self.assertEqual(result.body, self.raw)
        self.assertEqual(result.wire_bytes, len(self.wire))
        self.assertEqual(result.wire_sha256, hashlib.sha256(self.wire).hexdigest())
        self.assertEqual(result.content_encoding, "gzip")

    def test_identity_fallback_has_identical_wire_and_entity(self):
        result = self.fetch_response(Response(self.raw, encoding="identity"))
        self.assertEqual(result, self.result("identity"))

    def test_gzip_length_is_wire_length_not_decoded_length(self):
        self.assertLess(len(self.wire), len(self.raw))
        self.assertEqual(self.fetch_response(Response(self.wire)).body, self.raw)
        with self.assertRaises(CollectionFailure):
            self.fetch_response(Response(self.wire, length=len(self.raw)))

    def test_crc_truncation_and_additional_members_fail_closed(self):
        corrupt = bytearray(self.wire)
        corrupt[-8] ^= 1
        for wire in (self.wire[:-1], bytes(corrupt), self.wire + b"junk", self.wire + self.wire):
            with self.subTest(wire=wire[-10:]):
                with self.assertRaises(CollectionFailure):
                    decode_http_body(wire, "gzip")

    def test_inflation_limit_accepts_boundary_and_rejects_excess(self):
        for size in (MAX_BODY, MAX_BODY + 1, 10 * MAX_BODY):
            with self.subTest(size=size):
                wire = gzip.compress(b"x" * size, mtime=0)
                if size == MAX_BODY:
                    self.assertEqual(len(decode_http_body(wire, "gzip")), size)
                else:
                    with self.assertRaises(CollectionFailure):
                        decode_http_body(wire, "gzip")

    def test_empty_wire_empty_entity_and_unknown_encodings_are_rejected(self):
        for wire, encoding in ((b"", "identity"), (gzip.compress(b""), "gzip"),
                               (self.raw, "br"), (self.wire, "gzip, gzip")):
            with self.subTest(encoding=encoding):
                with self.assertRaises(CollectionFailure):
                    decode_http_body(wire, encoding)

    def test_collection_v2_separates_three_byte_totals(self):
        _, report, bodies = collect(self.seed, fetch=lambda _: self.result(), now=self.now)
        self.assertEqual(report["schema_version"], "dayflare.identity-collection.v2")
        self.assertEqual(report["body_representation"], "decoded-json-entity")
        self.assertEqual(report["transferred_bytes"], len(self.wire))
        self.assertEqual(report["decoded_bytes"], len(self.raw))
        self.assertEqual(report["retained_bytes"], sum(map(len, bodies.values())))
        self.assertEqual(report["attempts"][0]["body_sha256"], hashlib.sha256(self.raw).hexdigest())

    def test_complete_compressed_bundle_passes_independent_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed.json"
            seed.write_bytes(canonical_bytes(self.seed))
            out = root / "out"
            collect_to_new_directory(seed, out, fetch=lambda _: self.result(), now=self.now)
            self.assertEqual(verify_bundle(out)["verified_pages"], 1)
            self.assertEqual((out / "raw/en.wikipedia.101.json").read_bytes(), self.raw)

    def test_rehashed_wire_entity_and_version_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed.json"
            seed.write_bytes(canonical_bytes(self.seed))
            out = root / "out"
            collect_to_new_directory(seed, out, fetch=lambda _: self.result(), now=self.now)
            original = json.loads((out / "collection-report.json").read_text())
            variants = []
            bad = deepcopy(original); bad["decoded_bytes"] += 1; variants.append(bad)
            bad = deepcopy(original); bad["transferred_bytes"] += 1; variants.append(bad)
            bad = deepcopy(original); bad["body_representation"] = "wire"; variants.append(bad)
            bad = deepcopy(original); bad["schema_version"] = "dayflare.identity-collection.v1"; variants.append(bad)
            bad = deepcopy(original); bad["attempts"][0]["content_encoding"] = "identity"; variants.append(bad)
            for bad in variants:
                (out / "collection-report.json").write_bytes(canonical_bytes(bad))
                panel = load_panel(out / "panel.json")
                (out / "bundle-manifest.json").write_bytes(canonical_bytes(make_manifest_for_complete(out, panel)))
                with self.assertRaises(PanelError): verify_bundle(out)

    def test_wire_and_entity_collection_budgets_are_independent(self):
        for budget in (len(self.wire)-1, len(self.raw)-1):
            with patch("tools.m1_collect.MAX_TOTAL", budget):
                with self.assertRaises(CollectionFailure):
                    collect(self.seed, fetch=lambda _: self.result(), now=self.now)

    def test_invalid_identity_representation_metadata_is_rejected(self):
        bad = HTTPResult(200, self.raw, len(self.raw), "0" * 64, "identity")
        with self.assertRaisesRegex(PanelError, "wire/entity mismatch"):
            collect(self.seed, fetch=lambda _: bad, now=self.now)

    def test_corrupt_compressed_fetch_never_publishes_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed.json"
            seed.write_bytes(canonical_bytes(self.seed))
            out = root / "new"
            def fetch(_):
                return self.fetch_response(Response(self.wire[:-3]))
            with self.assertRaises(CollectionFailure):
                collect_to_new_directory(seed, out, fetch=fetch, now=self.now)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
