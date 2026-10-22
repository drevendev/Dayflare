"""Synthetic collector controls. Never contacts Wikimedia or asserts live retrieval."""
from __future__ import annotations

from datetime import datetime, timezone
from http.client import IncompleteRead
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from email.message import Message

from tools.m1_collect import (
    COLLECTION_SCHEMA, CollectionFailure, SEED_SCHEMA, collect,
    collect_to_new_directory, validate_seed, wiki_endpoint, _fetch_once, _NoRedirect, USER_AGENT,
    _rename_directory_no_replace,
)
from tools.m1_identity_panel import PanelError, canonical_bytes
from tools.m1_source_verify import verify_sources


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.seed = {"schema_version": SEED_SCHEMA, "panel_id": "probe.identity.20261021",
            "selected_at": "2026-10-21", "pages": [
                {"page_ref": {"project": "ru.wikipedia", "page_id": 801},
                 "topic_id": "t.science", "subject": "science", "relation": "ambiguous"},
                {"page_ref": {"project": "en.wikipedia", "page_id": 17},
                 "topic_id": "t.science", "subject": "science", "relation": "ambiguous"},
            ]}
        self.now = lambda: datetime(2026, 10, 21, 9, 0, 0, tzinfo=timezone.utc)
        self.called = []
        self.sleep = []

    def body(self, url, *, title=None, qid=None, pid=None, missing=False):
        if "ru.wikipedia" in url:
            page_id, title, qid = 801, title or "Наука", "Q336" if qid is None else qid
        else:
            page_id, title, qid = 17, title or "Science", "Q336" if qid is None else qid
        page = {"pageid": page_id if pid is None else pid, "ns": 0, "title": title}
        if qid:
            page["pageprops"] = {"wikibase_item": qid}
        if missing:
            page["missing"] = True
        return canonical_bytes({"batchcomplete": True, "query": {"pages": [page]}})

    def transport(self, url):
        self.called.append(url)
        return (200, self.body(url))

    def collect(self):
        return collect(self.seed, fetch=self.transport, now=self.now,
                       sleep=self.sleep.append)

    def test_two_edition_source_receipts_and_reproducible_output(self):
        panel, report, raw = self.collect()
        self.assertEqual(report["schema_version"], COLLECTION_SCHEMA)
        self.assertEqual(report["retained_count"], 2)
        self.assertEqual(report["unavailable_count"], 0)
        self.assertEqual(report["requests_attempted"], 2)
        self.assertEqual(report["retained_bytes"], sum(len(data) for data in raw.values()))
        self.assertEqual(report["transferred_bytes"], report["retained_bytes"])
        self.assertEqual(report["intended_by_edition_subject"], {"en.wikipedia":{"science":1}, "ru.wikipedia":{"science":1}})
        self.assertEqual(report["obtained_by_edition_subject"], report["intended_by_edition_subject"])
        self.assertEqual(self.sleep, [2.0])
        self.assertEqual(set(raw), {"en.wikipedia.17.json", "ru.wikipedia.801.json"})
        self.assertEqual([p["page_ref"]["project"] for p in panel["pages"]],
                         ["en.wikipedia", "ru.wikipedia"])
        self.assertTrue(all(p["continuity"] == "ambiguous" for p in panel["pages"]))
        self.assertTrue(all(p["source"]["http_status"] == 200 for p in panel["pages"]))
        self.assertTrue(all(p["wikidata"]["state"] == "observed" for p in panel["pages"]))
        self.assertTrue(all("pageviews" not in p for p in panel["pages"]))
        self.seed["pages"].reverse()
        second = self.collect()
        self.assertEqual(canonical_bytes(panel), canonical_bytes(second[0]))
        self.assertEqual(canonical_bytes(report), canonical_bytes(second[1]))

    def test_slow_action_api_response_waits_five_seconds_before_next_call(self):
        # Wikimedia Robot policy: if an Action API request takes >1 s to
        # serve, wait 5 s before another request, not just the usual 2 s.
        with patch("tools.m1_collect.time.monotonic", side_effect=[10.0, 11.5, 20.0, 20.2]):
            panel, report, _ = self.collect()
        self.assertEqual(len(panel["pages"]), 2)
        self.assertEqual(report["requests_attempted"], 2)
        self.assertEqual(self.sleep, [5.0])

    def test_one_second_action_api_response_keeps_default_spacing(self):
        with patch("tools.m1_collect.time.monotonic", side_effect=[10.0, 11.0, 20.0, 20.5]):
            self.collect()
        self.assertEqual(self.sleep, [2.0])

    def test_slow_invalid_identity_still_waits_before_next_candidate(self):
        def fetch(url):
            self.called.append(url)
            return (200, self.body(url, missing=True) if "en.wikipedia" in url else self.body(url))
        with patch("tools.m1_collect.time.monotonic", side_effect=[10.0, 12.0, 20.0, 20.5]):
            _, report, _ = collect(self.seed, fetch=fetch, now=self.now,
                                   sleep=self.sleep.append)
        self.assertEqual(self.sleep, [5.0])
        self.assertEqual(report["unavailable_count"], 1)
        self.assertEqual(report["retained_count"], 1)

    def test_invalid_monotonic_timing_aborts_before_next_request(self):
        for ticks in ([10.0, 9.9], [10.0, float("nan")]):
            with self.subTest(ticks=ticks):
                self.called.clear()
                self.sleep.clear()
                with patch("tools.m1_collect.time.monotonic", side_effect=ticks):
                    with self.assertRaisesRegex(CollectionFailure, "invalid monotonic request duration"):
                        self.collect()
                self.assertEqual(len(self.called), 1)
                self.assertEqual(self.sleep, [])

    def test_retrieval_before_curated_selection_is_rejected_before_fetch(self):
        earlier = lambda: datetime(2026, 10, 20, 23, 59, tzinfo=timezone.utc)
        with self.assertRaisesRegex(PanelError, "retrieval predates curated selection"):
            collect(self.seed, fetch=self.transport, now=earlier, sleep=lambda _: None)
        self.assertEqual(self.called, [], "invalid provenance must not trigger network requests")

    def test_atomic_retained_bundle_verified_by_existing_module(self):
        seed_file = self.root / "seeds.json"
        seed_file.write_bytes(canonical_bytes(self.seed))
        out = self.root / "unique-run"
        receipt = collect_to_new_directory(seed_file, out, fetch=self.transport,
                                           now=self.now, sleep=self.sleep.append)
        self.assertEqual(receipt["retained_count"], 2)
        self.assertEqual(verify_sources(out / "panel.json", out / "raw")["verified_page_count"], 2)
        self.assertEqual(json.loads((out / "internal-consistency.json").read_text())["verified_page_count"], 2)
        with self.assertRaises(CollectionFailure):
            collect_to_new_directory(seed_file, out, fetch=self.transport,
                                     now=self.now, sleep=self.sleep.append)
        self.assertEqual(len(self.called), 2, "existing publication must not trigger requests")

    def test_atomic_no_replace_refuses_even_empty_existing_directory(self):
        if __import__("sys").platform != "linux":
            self.skipTest("Linux renameat2-specific no-replace regression")
        src, target = self.root / "complete", self.root / "published"
        src.mkdir()
        (src / "manifest").write_text("valid bundle")
        target.mkdir()  # plain os.rename() silently replaces this on Linux
        with self.assertRaises(FileExistsError):
            _rename_directory_no_replace(src, target)
        self.assertTrue(src.joinpath("manifest").is_file())
        self.assertEqual(list(target.iterdir()), [])

    def test_publication_race_keeps_competing_empty_destination(self):
        if __import__("sys").platform != "linux":
            self.skipTest("Linux renameat2-specific no-replace regression")
        seed_file = self.root / "seed-race.json"
        seed_file.write_bytes(canonical_bytes(self.seed))
        dest = self.root / "collision"
        def race(source, target):
            target.mkdir()  # injected after the initial exists() preflight
            return _rename_directory_no_replace(source, target)
        with patch("tools.m1_collect._rename_directory_no_replace", side_effect=race):
            with self.assertRaises(FileExistsError):
                collect_to_new_directory(seed_file, dest, fetch=self.transport,
                    now=self.now, sleep=self.sleep.append)
        self.assertTrue(dest.is_dir())
        self.assertEqual(list(dest.iterdir()), [])
        self.assertFalse((dest / "bundle-manifest.json").exists())
        self.assertEqual(len(self.called), 2)

    def test_missing_source_is_unavailable_not_zero(self):
        def fetch(url):
            return 200, self.body(url, missing=True) if "ru." in url else self.body(url)
        panel, report, bodies = collect(self.seed, fetch=fetch, now=self.now, sleep=lambda s:None)
        self.assertEqual(len(panel["pages"]), 1)
        self.assertEqual(report["unavailable_count"], 1)
        self.assertEqual(report["attempts"][-1]["reason"], "invalid_or_missing_identity")
        self.assertNotIn("ru.wikipedia.801.json", bodies)
        self.assertEqual(report["retained_bytes"], sum(len(data) for data in bodies.values()))
        self.assertEqual(report["transferred_bytes"], report["retained_bytes"] + len(self.body("https://ru.wikipedia.org/w/api.php", missing=True)))
        self.assertGreater(report["transferred_bytes"], report["retained_bytes"])

    def test_404_is_provider_error_not_missing_page(self):
        def fetch(url):
            return (404, b"") if "ru." in url else (200, self.body(url))
        with self.assertRaisesRegex(CollectionFailure, "HTTP 404"):
            collect(self.seed, fetch=fetch, now=self.now, sleep=lambda s:None)

    def test_all_bad_identifiers_never_yield_publication(self):
        seed_path = self.root / "empty.json"
        seed_path.write_bytes(canonical_bytes(self.seed))
        with self.assertRaisesRegex(CollectionFailure, "no valid identities"):
            collect_to_new_directory(seed_path, self.root / "out",
                fetch=lambda url:(200,self.body(url,missing=True)),
                now=self.now, sleep=lambda s:None)
        self.assertFalse((self.root / "out").exists())

    def test_bad_upstream_qid_remains_unavailable(self):
        def fetch(url):
            return (200,self.body(url,qid="not-a-QID")) if "ru." in url else (200,self.body(url))
        panel, report, _ = collect(self.seed, fetch=fetch, now=self.now, sleep=lambda s:None)
        self.assertEqual(report["unavailable_count"], 1)
        self.assertEqual(report["obtained_by_edition_subject"], {"en.wikipedia":{"science":1}})
        self.assertEqual(len(panel["pages"]),1)

    def test_real_transport_prepares_identified_bounded_request(self):
        class Response:
            status=200
            def __init__(self):
                self.headers = Message()
                self.headers.add_header("Content-Type", "application/json")
            def __enter__(self): return self
            def __exit__(self,*a): return False
            def read(self,n):
                self.limit = n
                return b'{}'
        class Opener:
            def open(self, req, timeout):
                self.req, self.timeout = req,timeout
                self.resp = Response()
                return self.resp
        opener=Opener()
        with patch("tools.m1_collect.build_opener",return_value=opener) as patched:
            self.assertEqual(_fetch_once(wiki_endpoint("en.wikipedia",17)).body, b'{}')
        self.assertTrue(any(h is _NoRedirect or isinstance(h,_NoRedirect) for h in patched.call_args.args))
        self.assertEqual(opener.req.get_header("User-agent"), USER_AGENT)
        self.assertEqual(opener.req.get_method(),"GET")
        self.assertEqual(opener.timeout, 10)
        self.assertEqual(opener.resp.limit,1024*1024+1)

    def test_premature_http_eof_is_not_a_publishable_source_receipt(self):
        # Some HTTP clients return a short final body rather than raising.
        # A successful 200 and checksum of that fragment must not be accepted.
        class Response:
            status = 200
            def __init__(self, content_length, delivered):
                self.headers = Message()
                self.headers.add_header("Content-Type", "application/json")
                if content_length is not None:
                    self.headers.add_header("Content-Length", content_length)
                self.delivered = delivered
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return self.delivered[:limit]
        class Opener:
            def __init__(self, response): self.response = response
            def open(self, request, timeout): return self.response

        url = wiki_endpoint("en.wikipedia", 17)
        for declared, delivered in [("8", b"{}"), ("1", b"{}")]:
            with self.subTest(declared=declared):
                with patch("tools.m1_collect.build_opener", return_value=Opener(Response(declared, delivered))):
                    with self.assertRaisesRegex(CollectionFailure, "HTTP body vs Content-Length"):
                        _fetch_once(url)
        with patch("tools.m1_collect.build_opener", return_value=Opener(Response("2", b"{}"))):
            self.assertEqual(_fetch_once(url).body, b"{}")
        # Transfer without Content-Length is allowed; the JSON/schema verifier
        # is still responsible for proving a complete, valid Wikimedia response.
        with patch("tools.m1_collect.build_opener", return_value=Opener(Response(None, b"{}"))):
            self.assertEqual(_fetch_once(url).body, b"{}")

    def test_urllib_raises_incomplete_read_without_publication(self):
        class Response:
            status = 200
            def __init__(self):
                self.headers = Message()
                self.headers.add_header("Content-Type", "application/json")
                self.headers.add_header("Content-Length", "5")
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): raise IncompleteRead(b"{}", 3)
        class Opener:
            def open(self, request, timeout): return Response()
        with patch("tools.m1_collect.build_opener", return_value=Opener()):
            with self.assertRaisesRegex(CollectionFailure, "incomplete upstream HTTP body"):
                _fetch_once(wiki_endpoint("en.wikipedia", 17))

    def test_malformed_content_lengths_fail_closed(self):
        class Response:
            status = 200
            def __init__(self, length):
                self.headers = Message()
                self.headers.add_header("Content-Type", "application/json")
                self.headers.add_header("Content-Length", length)
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return b"{}"
        class Opener:
            def __init__(self, value): self.value = value
            def open(self, request, timeout): return Response(self.value)
        url = wiki_endpoint("en.wikipedia", 17)
        for length in ["-1", "+2", "2.0", "02", "", " ", "garbage", "1" * 90]:
            with self.subTest(length=length):
                with patch("tools.m1_collect.build_opener", return_value=Opener(length)):
                    with self.assertRaisesRegex(CollectionFailure, "Content-Length"):
                        _fetch_once(url)
        with patch("tools.m1_collect.build_opener", return_value=Opener("0")):
            with self.assertRaisesRegex(CollectionFailure, "Content-Length"):
                _fetch_once(url)
        with patch("tools.m1_collect.build_opener", return_value=Opener(str(1024*1024+1))):
            with self.assertRaisesRegex(CollectionFailure, "Content-Length"):
                _fetch_once(url)

    def test_no_http_redirect_following(self):
        self.assertIsNone(_NoRedirect().redirect_request(None,None,302,"Moved",{},"http://evil.test"))

    def test_fail_closed_429_preserves_previous_and_writes_nothing(self):
        seed_path = self.root / "seeds.json"
        seed_path.write_bytes(canonical_bytes(self.seed))
        out = self.root / "not-published"
        calls = []
        def limited(url):
            calls.append(url)
            return 429, b""
        with self.assertRaisesRegex(CollectionFailure, "429"):
            collect_to_new_directory(seed_path, out, fetch=limited,
                                     now=self.now, sleep=lambda s:None)
        self.assertEqual(len(calls), 1)
        self.assertFalse(out.exists())
        self.assertFalse(list(self.root.glob(".dayflare-identity-*")))

    def test_503_never_retries_or_publishes(self):
        with self.assertRaisesRegex(CollectionFailure, "503"):
            collect(self.seed, fetch=lambda url:(503,b""), now=self.now, sleep=lambda s:None)

    def test_network_failure_never_publishes(self):
        def failed(url): raise TimeoutError()
        with self.assertRaisesRegex(CollectionFailure, "network failure"):
            collect(self.seed, fetch=failed, now=self.now, sleep=lambda s:None)

    def test_mismatched_project_pageid_is_excluded(self):
        def fetch(url):
            return 200, self.body(url, pid=999) if "ru." in url else self.body(url)
        panel, report, _ = collect(self.seed, fetch=fetch, now=self.now, sleep=lambda s:None)
        self.assertEqual(len(panel["pages"]), 1)
        self.assertEqual(report["unavailable_count"], 1)

    def test_duplicate_body_keys_are_rejected(self):
        def fetch(url):
            return 200, self.body(url).replace(b'"pageid":17', b'"pageid":17,"pageid":17') if "en." in url else self.body(url)
        panel, report, _ = collect(self.seed, fetch=fetch, now=self.now, sleep=lambda s:None)
        self.assertEqual(len(panel["pages"]), 1)
        self.assertEqual(report["unavailable_count"], 1)

    def test_seed_limits_and_duplicate_ids(self):
        with self.assertRaisesRegex(PanelError, "duplicate identity"):
            validate_seed({**self.seed, "pages": self.seed["pages"] + [self.seed["pages"][0]]})
        with self.assertRaisesRegex(PanelError, "requires 1..30"):
            validate_seed({**self.seed, "pages": []})
        with self.assertRaisesRegex(PanelError, "requires 1..30"):
            validate_seed({**self.seed, "pages": self.seed["pages"] * 20})
        with self.assertRaisesRegex(PanelError, "unsupported edition"):
            validate_seed({**self.seed, "pages": [{**self.seed["pages"][0], "page_ref": {"project": "de.wikipedia", "page_id": 801}}]})

    def test_seed_json_duplicate_keys_fail_before_requests(self):
        seed_path = self.root / "dup.json"
        seed_path.write_text('{"schema_version": "' + SEED_SCHEMA + '", "schema_version":"bogus"}')
        with self.assertRaisesRegex(PanelError, "duplicate JSON"):
            collect_to_new_directory(seed_path, self.root / "out", fetch=self.transport)
        self.assertEqual(self.called, [])

    def test_source_endpoint_fixed_and_unforgeable_from_seed(self):
        url = wiki_endpoint("en.wikipedia", 17)
        self.assertTrue(url.startswith("https://en.wikipedia.org/w/api.php?"))
        self.assertIn("pageids=17", url)
        self.assertNotIn("redirects", url)
        with self.assertRaises(PanelError):
            wiki_endpoint("example.com", 17)
        with self.assertRaises(PanelError):
            wiki_endpoint("en.wikipedia", -1)

    def test_over_budget_response_aborts_without_published_partial(self):
        seed_path = self.root / "s.json"
        seed_path.write_bytes(canonical_bytes(self.seed))
        with self.assertRaisesRegex(CollectionFailure, "oversized or empty"):
            collect_to_new_directory(seed_path, self.root / "out",
                                     fetch=lambda u:(200,b"x"*(1024*1024+1)),
                                     now=self.now,sleep=lambda s:None)
        self.assertFalse((self.root / "out").exists())


if __name__ == "__main__":
    unittest.main()
