"""Entirely synthetic offline tests; no provider identity or traffic is asserted."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
import unittest

from tools.m1_pageview_handoff import HandoffError, canonical, make_handoff

TODAY = date(2026, 10, 24)
PROOF = {"result": "bundle_structurally_and_internally_consistent",
         "panel_id": "panel.test", "manifest_sha256": "e" * 64}


def panel():
    def page(project, pid, title, subject, day="2026-10-24", continuity="ambiguous"):
        return {"page_ref": {"project": project, "page_id": pid},
                "titles": [{"title": title, "date": day}], "source": {"requested_at": day + "T08:00:00Z"},
                "subject": subject, "continuity": continuity,
                "events": [], "redirect_to": None}
    return {"panel_id": "panel.test", "selection": {"evidence_kind": "reported_retrieval"},
            "pages": [page("ru.wikipedia", 202, "Пример", "books"),
                      page("en.wikipedia", 101, "Example", "science")]}


class HandoffTests(unittest.TestCase):
    def test_deterministic_bilingual_seed_scoped_to_titles(self):
        seed, receipt = make_handoff(panel(), PROOF, today=TODAY)
        self.assertEqual([row["project"] for row in seed["pages"]], ["en.wikipedia", "ru.wikipedia"])
        self.assertEqual(seed["provider_lag_days"], 2)
        self.assertEqual(receipt["candidate_count"], 2)
        self.assertEqual(len(receipt["uncertain_continuity"]), 2)
        self.assertIn("title_scoped", receipt["metric_scope"])
        self.assertEqual(canonical(seed), canonical(make_handoff(panel(), PROOF, today=TODAY)[0]))
        self.assertNotIn("Q", json.dumps(seed))

    def test_synthetic_and_unverified_proofs_rejected(self):
        p = panel(); p["selection"]["evidence_kind"] = "synthetic"
        with self.assertRaisesRegex(HandoffError, "synthetic"):
            make_handoff(p, PROOF, today=TODAY)
        for field in ("result", "panel_id", "manifest_sha256"):
            q = dict(PROOF); q[field] = "incorrect"
            with self.subTest(field=field), self.assertRaises(HandoffError):
                make_handoff(panel(), q, today=TODAY)

    def test_id_not_title_is_key_but_duplicate_analytics_title_is_ambiguous(self):
        p = panel(); p["pages"].append(deepcopy(p["pages"][0]))
        p["pages"][-1]["page_ref"]["page_id"] = 303
        with self.assertRaisesRegex(HandoffError, "same edition/title"):
            make_handoff(p, PROOF, today=TODAY)
        p["pages"][-1]["titles"][-1]["title"] = "Other"
        self.assertEqual(make_handoff(p, PROOF, today=TODAY)[1]["candidate_count"], 3)

    def test_stale_excluded_explicitly_without_zero_or_padding(self):
        p = panel(); old = p["pages"][0]
        old["titles"][-1]["date"] = "2026-10-21"
        old["source"]["requested_at"] = "2026-10-21T08:00:00Z"
        seed, report = make_handoff(p, PROOF, today=TODAY)
        self.assertEqual(len(seed["pages"]), 1)
        self.assertEqual(report["excluded_count"], 1)
        self.assertEqual(report["exclusions"][0]["reason"], "stale_or_future_title_observation")
        self.assertNotIn("daily", report)

    def test_redirect_and_event_excluded_without_identity_stitching(self):
        for mod in ("redirect_to", "events"):
            p = panel()
            if mod == "redirect_to": p["pages"][0][mod] = {"target_ref": {"project": "ru.wikipedia", "page_id": 7}}
            else: p["pages"][0][mod] = [{"kind": "move"}]
            seed, report = make_handoff(p, PROOF, today=TODAY)
            self.assertEqual(len(seed["pages"]), 1)
            self.assertEqual(report["exclusions"][0]["reason"], "redirect_or_identity_event_requires_historical_review")

    def test_timestamp_must_bind_observed_title_to_request_date(self):
        p = panel(); p["pages"][0]["source"]["requested_at"] = "2026-10-23T00:00:00Z"
        with self.assertRaisesRegex(HandoffError, "differs"):
            make_handoff(p, PROOF, today=TODAY)
        p = panel(); p["pages"][0]["source"]["requested_at"] = "2026-10-24T08:00:00+03:00"
        with self.assertRaisesRegex(HandoffError, "not UTC"):
            make_handoff(p, PROOF, today=TODAY)

    def test_empty_after_exclusion_or_over_budget_rejected(self):
        p = panel()
        for row in p["pages"]:
            row["titles"][-1]["date"] = "2026-10-18"
            row["source"]["requested_at"] = "2026-10-18T08:00:00Z"
        with self.assertRaisesRegex(HandoffError, "no eligible"):
            make_handoff(p, PROOF, today=TODAY)
        p = panel()
        base = p["pages"][1]
        p["pages"] = [dict(deepcopy(base), page_ref={"project": "en.wikipedia", "page_id": i},
                            titles=[{"title": f"Example_{i}", "date": "2026-10-24"}])
                       for i in range(1, 32)]
        with self.assertRaisesRegex(HandoffError, "budget"):
            make_handoff(p, PROOF, today=TODAY)

    def test_boolean_id_bad_subject_and_lag_rejected(self):
        p = panel(); p["pages"][0]["page_ref"]["page_id"] = True
        with self.assertRaises(HandoffError): make_handoff(p, PROOF, today=TODAY)
        p = panel(); p["pages"][0]["subject"] = "imaginary"
        self.assertEqual(make_handoff(p, PROOF, today=TODAY)[1]["excluded_count"], 1)
        for lag in (0, 8, True, 1.5):
            with self.subTest(lag=lag), self.assertRaises(HandoffError):
                make_handoff(panel(), PROOF, today=TODAY, lag_days=lag)


if __name__ == "__main__":
    unittest.main()
