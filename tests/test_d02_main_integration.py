"""Offline synthetic transport tests; these are not Wikimedia retrieval evidence."""
import hashlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from contextlib import redirect_stdout
from datetime import date, timedelta
from unittest.mock import patch

from tools import d02_probe
from tools.d01_probe import REQUESTS, expected_response_project


class FakeResponse:
    def __init__(self, payload: dict):
        self.status = 200
        self.headers = {"Content-Type": "application/json", "ETag": '"fixture"'}
        self._raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        return self._raw if size < 0 else self._raw[:size]


def items_for(spec, *, omit_index=None, wrong_article=False):
    start = date(2026, 8, 11)
    out = []
    for i in range(35):
        if i == omit_index:
            continue
        day = start + timedelta(days=i)
        out.append(
            {
                "project": expected_response_project(spec["project"]),
                "article": "WRONG" if wrong_article and i == 0 else spec["article"],
                "access": "all-access",
                "agent": "user",
                "granularity": "daily",
                "timestamp": day.strftime("%Y%m%d00"),
                "views": (i + 1) * 10,
            }
        )
    return out


class D02MainIntegrationTests(unittest.TestCase):
    def _run(self, urlopen):
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as td, patch.object(d02_probe.urllib.request, "urlopen", side_effect=urlopen), patch.object(
            d02_probe, "iso_now", side_effect=[f"2026-10-03T16:00:{i:02d}Z" for i in range(14)]
        ):
            os.chdir(td)
            try:
                with redirect_stdout(io.StringIO()):
                    rc = d02_probe.main()
                receipt = json.loads(Path("artifacts/d02/receipt.json").read_text(encoding="utf-8"))
                sample_bytes = Path("artifacts/d02/sample.json").read_bytes()
                self.assertTrue(sample_bytes.endswith(b"\n"))
                self.assertEqual(receipt["normalized_sample_sha256"], hashlib.sha256(sample_bytes[:-1]).hexdigest())
                sample = json.loads(sample_bytes)
                return rc, receipt, sample
            finally:
                os.chdir(old)

    def test_main_emits_complete_metrics_and_normalizes_documented_omitted_zero(self):
        calls = 0
        seen_requests = []

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec = REQUESTS[calls]
            omit = 10 if calls == 2 else None
            seen_requests.append((req.full_url, timeout, req.get_header("User-agent"), req.get_header("Accept")))
            calls += 1
            return FakeResponse({"items": items_for(spec, omit_index=omit)})

        rc, receipt, sample = self._run(fake_urlopen)
        self.assertEqual(rc, 0)
        self.assertTrue(receipt["success"])
        self.assertEqual(receipt["request_count"], 6)
        self.assertEqual(len(seen_requests), 6)
        self.assertTrue(all(timeout == 30 for _, timeout, _, _ in seen_requests))
        self.assertTrue(all(user_agent == d02_probe.USER_AGENT for _, _, user_agent, _ in seen_requests))
        self.assertTrue(all(accept == "application/json" for _, _, _, accept in seen_requests))
        self.assertTrue(all(url.endswith(f"/daily/{d02_probe.START}/{d02_probe.END}") for url, *_ in seen_requests))
        self.assertEqual(len(receipt["series_metrics"]), 6)
        self.assertTrue(all(row["metrics"] is not None for row in receipt["series_metrics"]))
        self.assertEqual(receipt["receipts"][2]["omitted_zero_days"], ["2026-08-21"])
        zero = [row for row in sample[2]["items"] if row["date"] == "2026-08-21"][0]
        self.assertEqual(zero["views"], 0)
        self.assertEqual(zero["value_state"], "documented_omitted_zero")
        self.assertEqual(zero["fill_reason"], "wikimedia_time_series_omitted_zero")
        self.assertFalse(receipt["thresholds_frozen"])

    def test_main_fails_closed_on_semantic_identity_mismatch(self):
        calls = 0

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec = REQUESTS[calls]
            wrong = calls == 3
            calls += 1
            return FakeResponse({"items": items_for(spec, wrong_article=wrong)})

        rc, receipt, sample = self._run(fake_urlopen)
        self.assertEqual(rc, 2)
        self.assertFalse(receipt["success"])
        bad = receipt["receipts"][3]
        self.assertFalse(bad["semantic_valid"])
        self.assertEqual(bad["item_count_normalized"], 0)
        self.assertEqual(len(bad["unresolved_days"]), 35)
        self.assertIsNone(receipt["series_metrics"][3]["metrics"])
        self.assertEqual(sample[3]["items"], [])

    def test_main_fails_closed_on_http_error_without_zero_filling(self):
        calls = 0

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec = REQUESTS[calls]
            if calls == 4:
                calls += 1
                raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", {}, io.BytesIO(b"busy"))
            calls += 1
            return FakeResponse({"items": items_for(spec)})

        rc, receipt, sample = self._run(fake_urlopen)
        self.assertEqual(rc, 2)
        self.assertFalse(receipt["success"])
        bad = receipt["receipts"][4]
        self.assertEqual(bad["http_status"], 503)
        self.assertIn("HTTPError", bad["error"])
        self.assertEqual(bad["omitted_zero_days"], [])
        self.assertEqual(len(bad["unresolved_days"]), 35)
        self.assertIsNone(receipt["series_metrics"][4]["metrics"])
        self.assertEqual(sample[4]["items"], [])

    def test_complete_response_with_unrepresentable_views_preserves_failure_receipt(self):
        calls = 0

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec = REQUESTS[calls]
            items = items_for(spec)
            if calls == 2:
                items[3]["views"] = 1 << 53
            calls += 1
            return FakeResponse({"items": items})

        rc, receipt, sample = self._run(fake_urlopen)
        self.assertEqual(rc, 2)
        self.assertFalse(receipt["success"])
        bad = receipt["receipts"][2]
        self.assertEqual(bad["http_status"], 200)
        self.assertTrue(bad["semantic_valid"])
        self.assertTrue(bad["normalized_complete"])
        self.assertFalse(bad["response_truncated"])
        self.assertIsNotNone(bad["response_sha256"])
        self.assertIn("MetricError", bad["error"])
        self.assertIn("JavaScript-safe", bad["error"])
        self.assertIsNone(receipt["series_metrics"][2]["metrics"])
        self.assertEqual(sample[2]["items"][3]["views"], 1 << 53)
        self.assertIsNotNone(receipt["series_metrics"][1]["metrics"])

    def test_complete_response_with_weekly_overflow_preserves_failure_receipt(self):
        calls = 0

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec = REQUESTS[calls]
            items = items_for(spec)
            if calls == 1:
                items[0]["views"] = 1 << 52
                items[1]["views"] = 1 << 52
            calls += 1
            return FakeResponse({"items": items})

        rc, receipt, sample = self._run(fake_urlopen)
        self.assertEqual(rc, 2)
        self.assertFalse(receipt["success"])
        self.assertIn("weekly Pageviews total", receipt["receipts"][1]["error"])
        self.assertIsNone(receipt["series_metrics"][1]["metrics"])
        self.assertEqual(sample[1]["items"][0]["views"], 1 << 52)

    def test_precision_loss_in_derived_median_fails_closed_with_receipt(self):
        calls = 0
        maximum=(1 << 53)-1

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec=REQUESTS[calls]
            items=items_for(spec)
            if calls == 3:
                for row in items:
                    row["views"]=0
                for week,total in enumerate([maximum-1,maximum-1,maximum,maximum,maximum]):
                    items[week*7]["views"]=total
            calls += 1
            return FakeResponse({"items":items})

        rc,receipt,sample=self._run(fake_urlopen)
        self.assertEqual(rc,2)
        self.assertFalse(receipt["success"])
        bad=receipt["receipts"][3]
        self.assertTrue(bad["semantic_valid"])
        self.assertTrue(bad["normalized_complete"])
        self.assertIsNotNone(bad["response_sha256"])
        self.assertIn("median baseline loses JavaScript numeric precision",bad["error"])
        self.assertIsNone(receipt["series_metrics"][3]["metrics"])
        self.assertEqual(sample[3]["items"][0]["views"],maximum-1)
        self.assertIsNotNone(receipt["series_metrics"][2]["metrics"])

    def test_success_response_over_budget_fails_closed_without_partial_hash(self):
        calls = 0

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec = REQUESTS[calls]
            calls += 1
            payload = {"items": items_for(spec)}
            if calls == 1:
                payload["unexpected_padding"] = "x" * (d02_probe.MAX_RESPONSE_BYTES + 100)
            return FakeResponse(payload)

        rc, receipt, sample = self._run(fake_urlopen)
        self.assertEqual(rc, 2)
        self.assertFalse(receipt["success"])
        oversized = receipt["receipts"][0]
        self.assertEqual(oversized["http_status"], 200)
        self.assertTrue(oversized["response_truncated"])
        self.assertEqual(oversized["response_bytes"], d02_probe.MAX_RESPONSE_BYTES + 1)
        self.assertIsNone(oversized["response_sha256"])
        self.assertIn("ResponseTooLarge", oversized["error"])
        self.assertFalse(oversized["payload_valid"])
        self.assertEqual(len(oversized["unresolved_days"]), 35)
        self.assertIsNone(receipt["series_metrics"][0]["metrics"])
        self.assertEqual(sample[0]["items"], [])
        self.assertFalse(any(row["response_truncated"] for row in receipt["receipts"][1:]))

    def test_http_error_body_is_also_bounded(self):
        calls = 0

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec = REQUESTS[calls]
            calls += 1
            if calls == 1:
                raise urllib.error.HTTPError(
                    req.full_url, 503, "Unavailable", {},
                    io.BytesIO(b"x" * (d02_probe.MAX_RESPONSE_BYTES + 100)),
                )
            return FakeResponse({"items": items_for(spec)})

        rc, receipt, sample = self._run(fake_urlopen)
        self.assertEqual(rc, 2)
        oversized = receipt["receipts"][0]
        self.assertEqual(oversized["http_status"], 503)
        self.assertTrue(oversized["response_truncated"])
        self.assertIsNone(oversized["response_sha256"])
        self.assertIn("HTTPError", oversized["error"])
        self.assertIn("ResponseTooLarge", oversized["error"])
        self.assertEqual(oversized["omitted_zero_days"], [])
        self.assertEqual(len(oversized["unresolved_days"]), 35)
        self.assertEqual(sample[0]["items"], [])


    def test_error_body_timeout_preserves_status_and_failure_receipt(self):
        class InterruptedBody(io.BytesIO):
            def read(self, size=-1):
                raise TimeoutError("synthetic interrupted error body")

        calls = 0
        body = InterruptedBody(b"partial")

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec = REQUESTS[calls]
            calls += 1
            if calls == 1:
                raise urllib.error.HTTPError(req.full_url, 503, "Unavailable", {}, body)
            return FakeResponse({"items": items_for(spec)})

        rc, receipt, sample = self._run(fake_urlopen)
        self.assertEqual(rc, 2)
        self.assertFalse(receipt["success"])
        bad = receipt["receipts"][0]
        self.assertEqual(bad["http_status"], 503)
        self.assertIn("HTTPError", bad["error"])
        self.assertIn("TimeoutError", bad["error"])
        self.assertIsNone(bad["response_sha256"])
        self.assertFalse(bad["response_body_complete"])
        self.assertFalse(bad["response_truncated"])
        self.assertEqual(sample[0]["items"], [])
        self.assertEqual(len(bad["unresolved_days"]), 35)
        self.assertEqual(calls, 6)
        self.assertTrue(body.closed)

    def test_transport_failure_is_not_a_hashed_empty_response(self):
        calls = 0

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec = REQUESTS[calls]
            calls += 1
            if calls == 1:
                raise urllib.error.URLError("synthetic unavailable transport")
            return FakeResponse({"items": items_for(spec)})

        rc, receipt, sample = self._run(fake_urlopen)
        self.assertEqual(rc, 2)
        bad = receipt["receipts"][0]
        self.assertIsNone(bad["http_status"])
        self.assertIsNone(bad["response_sha256"])
        self.assertFalse(bad["response_body_complete"])
        self.assertEqual(bad["response_bytes"], 0)
        self.assertEqual(sample[0]["items"], [])
        self.assertIsNotNone(receipt["receipts"][1]["response_sha256"])
        self.assertTrue(receipt["receipts"][1]["response_body_complete"])

    def test_complete_empty_error_response_has_real_empty_body_hash(self):
        calls = 0
        body = io.BytesIO(b"")

        def fake_urlopen(req, timeout):
            nonlocal calls
            spec = REQUESTS[calls]
            calls += 1
            if calls == 1:
                raise urllib.error.HTTPError(req.full_url, 503, "Unavailable", {}, body)
            return FakeResponse({"items": items_for(spec)})

        rc, receipt, sample = self._run(fake_urlopen)
        self.assertEqual(rc, 2)
        bad = receipt["receipts"][0]
        self.assertEqual(bad["http_status"], 503)
        self.assertTrue(bad["response_body_complete"])
        self.assertEqual(bad["response_sha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(sample[0]["items"], [])
        self.assertTrue(body.closed)


if __name__ == "__main__":
    unittest.main()
