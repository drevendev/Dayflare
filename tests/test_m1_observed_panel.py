"""The observed identity atlas must stay distinct from M0 views and synthetic M1."""
import copy
import json
from pathlib import Path
import re
import unittest

from tools.m1_observed_panel import ObservedIdentityError, validate_bytes, load

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/identities-m1-20261024.json"
HTML = ROOT / "site/identities-m1-20261024.html"


class ObservedIdentityAtlasTests(unittest.TestCase):
    def setUp(self):
        self.panel = load(SOURCE)

    def rejects(self, message):
        raw=(json.dumps(self.panel,ensure_ascii=False)+"\n").encode("utf-8")
        with self.assertRaisesRegex(ObservedIdentityError,message):
            validate_bytes(raw)

    def test_balanced_original_20_observations_not_popularity(self):
        self.assertEqual(len(self.panel["pages"]),20)
        self.assertEqual({p["project"] for p in self.panel["pages"]},
                         {"en.wikipedia","ru.wikipedia"})
        self.assertEqual(self.panel["pageviews"],"NOT_COLLECTED_FOR_THIS_PANEL")
        self.assertEqual(self.panel["authenticity"],"retained_source_internal_agreement_only")

    def test_two_ambiguous_editions_are_not_equated(self):
        for topic in ("cinema","football"):
            self.assertEqual(len({p["observed_qid"] for p in self.panel["pages"]
                                  if p["topic_id"]==topic}),2)
        self.assertEqual(self.panel["cross_edition_mapping"],"AMBIGUOUS_NOT_RESOLVED")

    def test_reject_invalid_numeric_id_and_bool(self):
        self.panel["pages"][0]["page_id"]=True
        self.rejects("numeric page ID")

    def test_reject_duplicate_ids(self):
        self.panel["pages"][1]["page_id"]=self.panel["pages"][0]["page_id"]
        self.rejects("duplicate local identity")

    def test_reject_duplicate_editorial_tags_within_edition(self):
        self.panel["pages"][1]["topic_id"]=self.panel["pages"][0]["topic_id"]
        self.rejects("duplicate editorial tag")

    def test_reject_missing_observation(self):
        self.panel["pages"].pop()
        self.rejects("expected 20 selected")

    def test_reject_fabricated_popularity_value(self):
        self.panel["pages"][0]["views"]=0
        self.rejects("unreviewed page fields")

    def test_reject_extra_origin_authenticity_claim(self):
        self.panel["authenticity"]="authenticated_wikimedia"
        self.rejects("unsupported origin")

    def test_reject_unreviewed_source_hash(self):
        self.panel["source_bundle_zip_sha256"]="0"*64
        self.rejects("unreviewed retained source")

    def test_reject_future_source_timestamp(self):
        self.panel["pages"][0]["requested_utc"]="2026-10-24T20:59:59Z"
        self.rejects("after retrieved time")

    def test_reject_noncanonical_or_duplicate_json(self):
        with self.assertRaisesRegex(ObservedIdentityError,"duplicate JSON"):
            validate_bytes(b'{"a":1,"a":2}')
        with self.assertRaisesRegex(ObservedIdentityError,"oversized"):
            validate_bytes(b" "*65537)

    def test_exact_static_html_includes_every_numeric_id(self):
        html=HTML.read_text(encoding="utf-8")
        actual=set(re.findall(r'data-page-ref="(en\.wikipedia|ru\.wikipedia):([0-9]+)"',html))
        expected={(p["project"],str(p["page_id"])) for p in self.panel["pages"]}
        self.assertEqual(actual,expected)
        for p in self.panel["pages"]:
            self.assertIn("curid="+str(p["page_id"]),html)
            self.assertIn(p["raw_response_sha256"],html)
        self.assertIn("Different observed QIDs",html)
        self.assertIn("No historical move/redirect",html)
        self.assertIn(self.panel["source_bundle_zip_sha256"],html)
        self.assertNotIn("synthetic demonstration",html.lower())

    def test_release_contains_distinct_historical_and_identity_datasets(self):
        from tools.build_static_release import bundle_files
        files=bundle_files()
        self.assertIn("identities-m1-20261024.html",files)
        self.assertIn("identities-m1-20261024.json",files)
        self.assertEqual(files["identities-m1-20261024.json"],SOURCE.read_bytes())
        receipt=json.loads(files["release-manifest.json"])
        self.assertEqual(receipt["daily_observations"],210)
        self.assertEqual(receipt["auxiliary_identity_dataset"]["observed_ids"],20)
        self.assertEqual(receipt["auxiliary_identity_dataset"]["pageviews"],"not_collected")


if __name__ == "__main__":
    unittest.main()
