"""Deterministic offline controls: none are Wikimedia runtime evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.m1_identity_panel import PanelError, canonical_bytes, load_panel, validate_panel

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/synthetic_panel.json"


class IdentityPanelTests(unittest.TestCase):
    def setUp(self):
        self.p = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def reject(self, substring=""):
        with self.assertRaises(PanelError) as ctx:
            validate_panel(self.p)
        self.assertIn(substring, str(ctx.exception))

    def test_sample_synthetic_and_coverage(self):
        v = validate_panel(self.p)
        self.assertEqual(v["coverage"]["obtained_count"], 2)
        self.assertEqual(v["coverage"]["unresolved_count"], 1)
        self.assertEqual(v["coverage"]["provenance_verification"], "synthetic_only")
        self.assertEqual(v["coverage"]["by_edition"], {"en.wikipedia": 2})
        self.assertEqual(v["coverage"]["redirect_targets_outside_panel"], [])

    def test_deterministic_order_and_bytes(self):
        one = canonical_bytes(validate_panel(self.p))
        self.p["pages"].reverse()
        self.assertEqual(one, canonical_bytes(validate_panel(self.p)))
        self.assertEqual(one, canonical_bytes(json.loads(one)))

    def test_move_preserves_page_id_with_dated_titles(self):
        v = validate_panel(self.p)
        self.assertEqual(v["pages"][0]["page_ref"]["page_id"], 17)
        self.assertEqual(len(v["pages"][0]["titles"]), 2)
        self.assertEqual(v["pages"][0]["continuity"], "confirmed")

    def test_redirect_is_separate_identity(self):
        v = validate_panel(self.p)
        self.assertEqual(v["pages"][1]["page_ref"]["page_id"], 18)
        self.assertEqual(v["pages"][1]["redirect_to"]["target_ref"]["page_id"], 17)

    def test_redirect_cycle_is_unresolved_not_merged(self):
        self.p["pages"][0]["redirect_to"] = {
            "target_ref": {"project":"en.wikipedia", "page_id":18},
            "observed_at": "2026-10-02",
            "source_url": "https://en.wikipedia.org/wiki/Example-new",
        }
        v = validate_panel(self.p)
        cycle = v["coverage"]["same_day_redirect_cycles"]
        self.assertEqual(len(cycle), 1)
        self.assertEqual(cycle[0]["observed_at"], "2026-10-02")
        self.assertEqual([row["page_id"] for row in cycle[0]["page_refs"]], [17, 18])
        self.assertEqual(cycle[0]["status"], "unresolved_redirect_cycle")
        self.assertEqual(len(v["pages"]), 2)  # no merging or dropped identities

    def test_redirects_on_different_days_do_not_imply_same_day_cycle(self):
        self.p["pages"][0]["redirect_to"] = {
            "target_ref": {"project":"en.wikipedia", "page_id":18},
            "observed_at": "2026-10-01",
            "source_url": "https://en.wikipedia.org/wiki/Example-old",
        }
        v = validate_panel(self.p)
        self.assertEqual(v["coverage"]["same_day_redirect_cycles"], [])

    def test_panel_counts_are_observations_not_missing_as_zero(self):
        v = validate_panel(self.p)
        self.assertEqual(v["coverage"]["observed_panel_counts_by_edition_subject"],
                         {"en.wikipedia": {"science": 2}})
        self.assertNotIn("ru.wikipedia", v["coverage"]["observed_panel_counts_by_edition_subject"])

    def test_two_dangling_edges_canonical_independent_of_page_order(self):
        self.p["pages"][0]["redirect_to"] = {
            "target_ref": {"project":"en.wikipedia", "page_id":100},
            "observed_at": "2026-10-02",
            "source_url": "https://en.wikipedia.org/wiki/Example-new",
        }
        self.p["pages"][1]["redirect_to"]["target_ref"]["page_id"] = 101
        a = canonical_bytes(validate_panel(self.p))
        self.p["pages"].reverse()
        b = canonical_bytes(validate_panel(self.p))
        self.assertEqual(a, b)
        self.assertEqual(len(validate_panel(self.p)["coverage"]["redirect_targets_outside_panel"]), 2)

    def test_three_member_cycle_detected_once_after_reordering(self):
        extra = copy.deepcopy(self.p["pages"][0])
        extra["page_ref"]["page_id"] = 19
        extra["redirect_to"] = {
            "target_ref": {"project":"en.wikipedia", "page_id":18},
            "observed_at": "2026-10-02",
            "source_url": "https://en.wikipedia.org/wiki/Example-extra",
        }
        self.p["pages"][0]["redirect_to"] = {
            "target_ref": {"project":"en.wikipedia", "page_id":19},
            "observed_at": "2026-10-02",
            "source_url": "https://en.wikipedia.org/wiki/Example-new",
        }
        self.p["selection"]["intended_count"] = 3
        self.p["pages"].append(extra)
        v = validate_panel(self.p)
        self.assertEqual(len(v["coverage"]["same_day_redirect_cycles"]), 1)
        self.assertEqual([ref["page_id"] for ref in v["coverage"]["same_day_redirect_cycles"][0]["page_refs"]],
                         [17, 18, 19])
        a = canonical_bytes(v)
        self.p["pages"].reverse()
        self.assertEqual(a, canonical_bytes(validate_panel(self.p)))

    def test_missing_qid_not_an_absence_claim(self):
        v = validate_panel(self.p)
        self.assertEqual(v["pages"][1]["wikidata"]["state"], "missing")
        self.assertNotIn("views", v["coverage"])

    def test_duplicate_identity_rejected_not_title_mapped(self):
        self.p["pages"][1]["page_ref"]["page_id"] = 17
        self.reject("duplicate")

    def test_same_title_different_id_allowed(self):
        self.p["pages"][1]["titles"][0]["title"] = "Example-new"
        validate_panel(self.p)

    def test_same_qid_two_local_ids_not_silently_equivalent(self):
        self.p["pages"][0]["wikidata"] = {"state":"resolved", "observed_qid":"Q1", "resolved_qid":"Q10", "evidence_url":None}
        self.p["pages"][1]["wikidata"] = {"state":"resolved", "observed_qid":"Q10", "resolved_qid":"Q10", "evidence_url":None}
        v = validate_panel(self.p)
        self.assertEqual(v["coverage"]["non_1_to_1_local_qid_collisions"][0]["local_page_ids"], [17, 18])

    def test_delete_restore_continuity_boundary(self):
        self.p["pages"][0]["events"].append({"date":"2026-10-03", "kind":"delete", "source_url":"https://en.wikipedia.org/wiki/Special:Log/delete"})
        self.reject("deletion/restore")
        self.p["pages"][0]["continuity"] = "ambiguous"
        validate_panel(self.p)

    def test_missing_mapping_cannot_store_qid(self):
        self.p["pages"][1]["wikidata"]["observed_qid"] = "Q11"
        self.reject("missing state")

    def test_qid_redirect_preserves_both(self):
        self.p["pages"][0]["wikidata"] = {"state":"resolved", "observed_qid":"Q11", "resolved_qid":"Q12", "evidence_url":None}
        v = validate_panel(self.p)
        self.assertEqual(v["pages"][0]["wikidata"]["observed_qid"], "Q11")

    def test_cross_edition_topic_does_not_imply_equivalence(self):
        row = copy.deepcopy(self.p["pages"][1])
        row["page_ref"] = {"project":"ru.wikipedia","page_id":190}
        row["redirect_to"] = None
        row["relation"] = "broader"
        self.p["pages"].append(row)
        self.p["selection"]["intended_count"] = 3
        v = validate_panel(self.p)
        self.assertEqual(v["coverage"]["cross_edition_topic_ids"], ["topic.example"])
        self.assertEqual(v["pages"][-1]["relation"], "broader")

    def test_bool_and_nonpositive_ids_rejected(self):
        for x in (True, 0, -1, 1<<53):
            with self.subTest(x=x):
                t=copy.deepcopy(self.p)
                t["pages"][0]["page_ref"]["page_id"] = x
                with self.assertRaises(PanelError): validate_panel(t)

    def test_noncanonical_dates(self):
        self.p["pages"][0]["titles"][1]["date"] = "2026-10-1"
        self.reject("invalid date")

    def test_unordered_title_observations(self):
        self.p["pages"][0]["titles"].reverse()
        self.reject("strictly increasing")

    def test_self_redirect(self):
        self.p["pages"][0]["redirect_to"] = {"target_ref":{"project":"en.wikipedia", "page_id":17}, "observed_at":"2026-10-02", "source_url":"https://en.wikipedia.org/wiki/Example-old"}
        self.reject("self")

    def test_cross_wiki_redirect(self):
        self.p["pages"][1]["redirect_to"]["target_ref"]["project"] = "ru.wikipedia"
        self.reject("cross-wiki")

    def test_retrieved_requires_receipt(self):
        self.p["selection"]["evidence_kind"] = "reported_retrieval"
        self.p["pages"][0]["wikidata"]["evidence_url"] = "https://www.wikidata.org/wiki/Q10"
        self.reject("expected an object")
        for row in self.p["pages"]:
            row["source"] = {"endpoint":"https://wikimedia.org/example", "requested_at":"2026-10-20T10:00:00Z", "http_status":200,"body_sha256":"a"*64,"response_bytes":314}
        self.p["pages"][0]["wikidata"]["evidence_url"] = None
        self.reject("Wikidata claim requires source URL")
        self.p["pages"][0]["wikidata"]["evidence_url"] = "https://www.wikidata.org/wiki/Q10"
        v=validate_panel(self.p)
        self.assertEqual(v["coverage"]["provenance_verification"], "reported_not_upstream_verified")

    def test_bad_http_evidence_and_nonstandard_host(self):
        self.p["pages"][0]["titles"][0]["source_url"] = "http://localhost/private"
        self.reject("HTTPS")

    def test_oversized_and_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as root:
            fp=Path(root)/"panel.json"
            fp.write_bytes(b" " * (256*1024+1))
            with self.assertRaisesRegex(PanelError, "exceeds"):
                load_panel(fp)
            fp.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaisesRegex(PanelError, "duplicate"):
                load_panel(fp)

    def test_nan_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            fp=Path(root)/"panel.json"
            fp.write_text('{"foo":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(PanelError, "non-finite"):
                load_panel(fp)

    def test_malformed_types_fail_as_panel_errors(self):
        cases = [
            ("page_ref", "project", ["en.wikipedia"]),
            ("wikidata", "state", ["resolved"]),
        ]
        for first, second, value in cases:
            with self.subTest(first=first, second=second):
                doc = copy.deepcopy(self.p)
                doc["pages"][0][first][second] = value
                with self.assertRaises(PanelError):
                    validate_panel(doc)
        for field in ("subject", "relation", "continuity"):
            with self.subTest(field=field):
                doc = copy.deepcopy(self.p)
                doc["pages"][0][field] = {"bad": "value"}
                with self.assertRaises(PanelError):
                    validate_panel(doc)

    def test_bad_url_port_rejected_cleanly(self):
        self.p["pages"][0]["titles"][0]["source_url"] = "https://en.wikipedia.org:broken/wiki/Example"
        self.reject("invalid source URL")

    def test_redirect_requires_dated_evidence(self):
        del self.p["pages"][1]["redirect_to"]["observed_at"]
        self.reject("missing fields")

    def test_reported_retrieval_invalid_future_timestamp(self):
        self.p["selection"]["evidence_kind"] = "reported_retrieval"
        self.p["pages"][0]["wikidata"]["evidence_url"] = "https://www.wikidata.org/wiki/Q10"
        for row in self.p["pages"]:
            row["source"] = {"endpoint":"https://wikimedia.org/example", "requested_at":"2999-01-01T00:00:00Z", "http_status":200,"body_sha256":"a"*64,"response_bytes":314}
        self.reject("future retrieval")

    def test_valid_example_from_disk(self):
        self.assertEqual(load_panel(EXAMPLE), validate_panel(self.p))


if __name__ == "__main__":
    unittest.main()
