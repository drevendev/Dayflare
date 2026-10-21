"""Real loopback HTTP framing regressions; payloads are synthetic, not Wikimedia evidence."""
from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from tools import d02_probe
from tools.d01_probe import REQUESTS
from test_d02_main_integration import items_for


@contextmanager
def server_for(mode, status=200):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            spec = REQUESTS[self.server.calls % len(REQUESTS)]
            self.server.calls += 1
            raw = json.dumps({"items": items_for(spec)}, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            if mode == "short":
                self.send_header("Content-Length", str(len(raw) + 100))
            elif mode == "invalid_length":
                self.send_header("Content-Length", "not-a-length")
            elif mode == "conflicting_lengths":
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Content-Length", str(len(raw) + 100))
            elif mode == "complete":
                self.send_header("Content-Length", str(len(raw)))
            elif mode in {"chunked", "incomplete_chunked"}:
                self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            if mode in {"chunked", "incomplete_chunked"}:
                self.wfile.write(f"{len(raw):X}\r\n".encode() + raw + b"\r\n")
                if mode == "chunked":
                    self.wfile.write(b"0\r\n\r\n")
            else:
                self.wfile.write(raw)
            self.close_connection = True

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.calls = 0
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class D02HTTPTransportTests(unittest.TestCase):
    def run_collector(self, mode, status=200):
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as directory, server_for(mode, status) as (base, server):
            try:
                os.chdir(directory)
                with patch.object(d02_probe, "BASE", base), redirect_stdout(io.StringIO()):
                    code = d02_probe.main()
                receipt = json.loads(Path("artifacts/d02/receipt.json").read_text(encoding="utf-8"))
                sample = json.loads(Path("artifacts/d02/sample.json").read_text(encoding="utf-8"))
                self.assertEqual(server.calls, len(REQUESTS))
                return code, receipt, sample
            finally:
                os.chdir(old)

    def assert_unavailable(self, mode, status, error):
        code, receipt, sample = self.run_collector(mode, status)
        self.assertEqual(code, 2)
        self.assertFalse(receipt["success"])
        for row in receipt["receipts"]:
            self.assertEqual(row["http_status"], status)
            self.assertFalse(row["response_body_complete"])
            self.assertIsNone(row["response_sha256"])
            self.assertIn(error, row["error"])
            self.assertEqual(len(row["unresolved_days"]), 35)
            self.assertEqual(row["omitted_zero_days"], [])
        self.assertTrue(all(row["items"] == [] for row in sample))
        self.assertTrue(all(row["metrics"] is None for row in receipt["series_metrics"]))

    def test_short_success_body_is_not_publishable_even_if_json_is_complete(self):
        self.assert_unavailable("short", 200, "IncompleteRead")

    def test_short_error_body_is_not_hashed_as_complete(self):
        self.assert_unavailable("short", 503, "IncompleteRead")

    def test_invalid_content_length_fails_closed(self):
        self.assert_unavailable("invalid_length", 200, "Content-Length")

    def test_conflicting_content_lengths_fail_closed(self):
        self.assert_unavailable("conflicting_lengths", 200, "Content-Length")

    def test_missing_chunk_terminator_fails_closed(self):
        self.assert_unavailable("incomplete_chunked", 200, "IncompleteRead")

    def test_complete_content_length_still_works(self):
        self.assert_complete("complete")

    def test_complete_chunked_body_still_works(self):
        self.assert_complete("chunked")

    def test_close_delimited_body_without_content_length_still_works(self):
        self.assert_complete("close_delimited")

    def assert_complete(self, mode):
        code, receipt, sample = self.run_collector(mode)
        self.assertEqual(code, 0)
        self.assertTrue(receipt["success"])
        self.assertEqual(sum(len(row["items"]) for row in sample), 210)
        self.assertTrue(all(row["response_body_complete"] for row in receipt["receipts"]))
        self.assertTrue(all(row["response_sha256"] for row in receipt["receipts"]))


if __name__ == "__main__":
    unittest.main()
