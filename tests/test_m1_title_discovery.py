"""Offline discovery contract: no Wikimedia network access."""
import json
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest import TestCase, main

from tools.m1_title_discovery import (
    SCHEMA, DiscoveryError, canonical, discover, endpoint, fetch_once, parse,
    validate_curated, verify,
)


def selection():
    return {"schema_version": SCHEMA, "panel_id": "m1-reviewed-candidates",
            "selected_at": "2026-10-24", "pages": [
                {"project": "en.wikipedia", "title": "Chess", "topic_id": "chess",
                 "subject": "games", "relation": "ambiguous"},
                {"project": "ru.wikipedia", "title": "Шахматы", "topic_id": "chess",
                 "subject": "games", "relation": "ambiguous"}]}


def response(page_id, title, qid="Q718"):
    return canonical({"batchcomplete": True,
                      "query": {"pages": [{"ns": 0, "pageid": page_id,
                                           "title": title, "pageprops": {"wikibase_item": qid}}]}})


def fixed_clock():
    return datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


@contextmanager
def local_http_server(handler):
    """Loopback-only; exercises urllib HTTP semantics without provider traffic."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    runner = Thread(target=server.serve_forever, daemon=True)
    runner.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()
        runner.join(timeout=2)


class SilentHTTP(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass


class TitleDiscoveryTests(TestCase):
    def test_compatible_seeds_and_provenance_replay(self):
        doc = selection()
        bodies = {endpoint(row["project"], row["title"]): response(index + 1, row["title"])
                  for index, row in enumerate(doc["pages"])}
        seed, report, raw = discover(doc, fetch=lambda url: bodies[url],
                                     clock=fixed_clock, sleep=lambda _: None)
        self.assertEqual(seed["schema_version"], "dayflare.identity-seeds.v1")
        self.assertEqual(len(seed["pages"]), 2)
        self.assertEqual(report["status"],
                         "LOCAL_ONLY_CANDIDATE_IDS_REQUIRE_INDEPENDENT_ID_REQUERY")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw").mkdir()
            for name, body in raw.items():
                (root / "raw" / name).write_bytes(body)
            (root / "identity-seeds.json").write_bytes(canonical(seed))
            (root / "discovery-report.json").write_bytes(canonical(report))
            curated = root / "selection.json"
            curated.write_bytes(canonical(doc))
            # Keep the independent input outside the strict retained-bundle root.
            bundle = root / "bundle"
            bundle.mkdir()
            for item in ("identity-seeds.json", "discovery-report.json"):
                (root / item).replace(bundle / item)
            (root / "raw").replace(bundle / "raw")
            self.assertEqual(verify(curated, bundle)["candidate_count"], 2)
            (bundle / "raw" / "00.json").write_bytes(b'{"batchcomplete":true}')
            with self.assertRaises(DiscoveryError):
                verify(curated, bundle)
            (bundle / "raw" / "00.json").write_bytes(raw["00.json"])
            (bundle / "extra.txt").write_text("undeclared")
            with self.assertRaises(DiscoveryError):
                verify(curated, bundle)

    def test_invalid_candidate_has_no_network_side_effect(self):
        doc = selection()
        doc["pages"][0]["project"] = "attacker.example"
        with self.assertRaises(DiscoveryError):
            discover(doc, fetch=lambda _: self.fail("network used"),
                     clock=fixed_clock)

    def test_redirect_excluded_not_counted_as_zero(self):
        doc = selection()
        def source(url):
            if "en.wikipedia" in url:
                return canonical({"batchcomplete": True, "query": {
                    "redirects": [{"from": "Chess", "to": "Other"}],
                    "pages": [{"ns": 0, "pageid": 4, "title": "Chess"}]}})
            return response(33, "Шахматы")
        seed, report, _ = discover(doc, fetch=source, clock=fixed_clock,
                                   sleep=lambda _: None)
        self.assertEqual(len(seed["pages"]), 1)
        self.assertEqual(report["excluded_count"], 1)

    def test_invalid_boolean_id_duplicate_keys_and_continuation(self):
        for raw in (response(True, "Chess"),
                    b'{"batchcomplete":true,"query":{},"query":{}}',
                    b'{"batchcomplete":true,"query":{"pages":[]},"continue":{}}',
                    b'{"batchcomplete":true,"query":{"pages":[]},"x":NaN}'):
            with self.assertRaises(DiscoveryError):
                parse(raw, "Chess")

    def test_missing_and_title_mismatch_are_unavailable(self):
        self.assertIsNone(parse(canonical({"batchcomplete": True, "query": {
            "pages": [{"missing": True}]}}), "Chess")[0])
        self.assertIsNone(parse(response(12, "Checkers"), "Chess")[0])

    def test_reverse_utc_receipts_rejected(self):
        instants = iter((fixed_clock(), fixed_clock() - timedelta(seconds=1)))
        with self.assertRaises(DiscoveryError):
            discover(selection(), fetch=lambda _: response(1, "Chess"),
                     clock=lambda: next(instants), sleep=lambda _: None)

    def test_cross_subject_sample_is_unverified_and_balanced(self):
        doc = json.loads(Path("examples/m1_curated_cross_subject_enru.json").read_text())
        rows = validate_curated(doc, fixed_clock().date())
        self.assertEqual(len(rows), 20)
        self.assertEqual({x["project"] for x in rows}, {"en.wikipedia", "ru.wikipedia"})
        self.assertEqual({x["subject"] for x in rows},
                         {"culture", "books", "games", "science", "sport"})
        self.assertTrue(all(x["relation"] == "ambiguous" for x in rows))


    def test_transport_rejects_cross_origin_http_redirect(self):
        class Target(SilentHTTP):
            hits = 0

            def do_GET(self):
                type(self).hits += 1
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        with local_http_server(Target) as target:
            class Redirect(SilentHTTP):
                def do_GET(self):
                    self.send_response(302)
                    self.send_header("Location", target)
                    self.end_headers()

            with local_http_server(Redirect) as original:
                with self.assertRaises(DiscoveryError):
                    fetch_once(original)
        self.assertEqual(Target.hits, 0)

    def test_transport_rejects_short_200_even_if_json_is_valid(self):
        raw = b'{"batchcomplete":true,"query":{"pages":[]}}'

        class Truncated(SilentHTTP):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw) + 5))
                self.end_headers()
                self.wfile.write(raw)
                self.wfile.flush()
                self.close_connection = True

        with local_http_server(Truncated) as url:
            with self.assertRaises(DiscoveryError):
                fetch_once(url)

    def test_transport_accepts_complete_declared_json_body(self):
        raw = b'{"batchcomplete":true,"query":{"pages":[]}}'

        class Complete(SilentHTTP):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        with local_http_server(Complete) as url:
            self.assertEqual(fetch_once(url), raw)


if __name__ == "__main__":
    main()
