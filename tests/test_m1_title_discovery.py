"""Offline discovery contract: no Wikimedia network access."""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase, main

from tools.m1_title_discovery import (
    SCHEMA, DiscoveryError, canonical, discover, endpoint, parse,
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


if __name__ == "__main__":
    main()
