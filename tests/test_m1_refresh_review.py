"""Synthetic negative controls for unpublished, reviewer-facing M1 refresh receipts.

These fabricated records are never Wikimedia observations or release evidence.
"""
import copy
from datetime import date, timedelta
from hashlib import sha256
import tempfile
from pathlib import Path
import unittest

from tools.m1_publication_gate import PublicationError, canonical
from tools.m1_refresh_review import build, summarize


def fixture():
    end = date(2026, 11, 6)
    retrieval = "2026-11-09T09:00:00Z"
    start = end - timedelta(days=34)
    series = []
    receipt_sources = []
    for i in range(20):
        project = "en.wikipedia" if i < 10 else "ru.wikipedia"
        page_id = 1000 + i
        title = f"Synthetic_case_{i}"
        url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
               f"{project}.org/all-access/user/{title}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
        evidence = {"endpoint": url, "requested_at": "2026-11-09T08:00:00Z",
                    "http_status": 200, "body_sha256": "a" * 64, "response_bytes": 1000}
        series.append({"project": project, "page_id": page_id, "title": title,
                       "access": "all-access", "agent": "user", "source": evidence,
                       "daily": [{"date": (start + timedelta(days=j)).isoformat(),
                                  "views": 10 + j, "value_state": "observed"} for j in range(35)]})
        receipt_sources.append({"project": project, "page_id": page_id, **evidence})
    candidate = {"schema_version": "dayflare.rolling-candidate.v1",
                 "dataset_id": "run-synthetic-20261109", "method_version": "v0-empirical-35d",
                 "retrieved_at": retrieval, "provider_lag_days": 2,
                 "observation_end": end.isoformat(), "series": series}
    receipt = {"schema_version": "dayflare.rolling-source-receipt.v1",
               "seed_sha256": "b" * 64,
               "candidate_sha256": sha256(canonical(candidate)).hexdigest(),
               "retrieved_at": retrieval, "observation_start": start.isoformat(),
               "observation_end": end.isoformat(), "requests_attempted": 20,
               "total_wire_bytes": 20000, "total_decoded_bytes": 20000,
               "sources": receipt_sources,
               "provenance_status": "runtime_reported_transport_not_independently_authenticated",
               "publication_status": "LOCAL_EVIDENCE_ONLY_NOT_PUBLISHED"}
    current = {"schema_version": "dayflare.m1.static-snapshot.v1",
               "status": "DATED_ARCHIVE_NOT_LIVE", "dataset_id": candidate["dataset_id"],
               "method_version": candidate["method_version"],
               "observation_end": candidate["observation_end"],
               "retrieved_at": candidate["retrieved_at"],
               "candidate_sha256": receipt["candidate_sha256"],
               "html_sha256": "c" * 64, "source_receipt_sha256": sha256(canonical(receipt)).hexdigest(),
               "source_seed_sha256": receipt["seed_sha256"],
               "series": 20, "daily_observations": 700}
    previous = {**current, "dataset_id": "run-synthetic-previous",
                "observation_end": "2026-11-05", "retrieved_at": "2026-11-08T08:00:00Z",
                "candidate_sha256": "d" * 64, "source_receipt_sha256": "e" * 64}
    return previous, current, candidate, receipt


class RefreshReviewTests(unittest.TestCase):
    def test_existing_daily_workflow_retains_review_receipt_without_publishing(self):
        text = (Path(__file__).resolve().parents[1] /
                ".github/workflows/m1-curated-rolling-pageviews.yml").read_text()
        self.assertIn("python -m tools.m1_refresh_review", text)
        self.assertIn("artifacts/m1-refresh-review.json", text)
        self.assertIn("--previous", text)
        self.assertIn("REVIEW_REQUIRED_NOT_DEPLOYED", text)
        self.assertNotIn("contents: write", text)

    def test_one_new_observation_day_is_not_traffic_delta(self):
        report = summarize(*fixture())
        self.assertEqual(report["new_completed_utc_days"], 1)
        self.assertEqual(report["status"], "REVIEW_REQUIRED_NOT_DEPLOYED")
        self.assertEqual(report["series"], 20)
        self.assertEqual(report["traffic_delta"], "NOT_COMPUTED_PREVIOUS_RAW_SERIES_NOT_AVAILABLE")
        self.assertEqual(report["source_authentication"], "RUNTIME_REPORTED_NOT_INDEPENDENTLY_VERIFIED")

    def test_reject_old_or_changed_identity_basket(self):
        old, current, candidate, receipt = fixture()
        backwards = copy.deepcopy(current)
        backwards["observation_end"] = "2026-11-04"
        with self.assertRaises(PublicationError):
            summarize(old, backwards, candidate, receipt)
        changed = copy.deepcopy(current)
        changed["source_seed_sha256"] = "f" * 64
        with self.assertRaises(PublicationError):
            summarize(old, changed, candidate, receipt)

    def test_reject_mutated_observations_and_synthetic_provenance(self):
        old, current, candidate, receipt = fixture()
        candidate["series"][0]["daily"][0]["views"] += 1
        with self.assertRaises(PublicationError):
            summarize(old, current, candidate, receipt)
        old, current, candidate, receipt = fixture()
        receipt["provenance_status"] = "synthetic_injected_not_upstream_evidence"
        with self.assertRaises(PublicationError):
            summarize(old, current, candidate, receipt)

    def test_byte_integrity_and_fail_closed_destination(self):
        old, current, candidate, receipt = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in [("old", old), ("new", current),
                                ("candidate", candidate), ("receipt", receipt)]:
                (root / name).write_bytes(canonical(value))
            args = [root / name for name in ("old", "new", "candidate", "receipt", "review")]
            accepted = build(*args)
            self.assertEqual((root / "review").read_bytes(), canonical(accepted))
            with self.assertRaises(PublicationError):
                build(*args)
            (root / "review").unlink()
            (root / "receipt").write_bytes(canonical({**receipt, "requests_attempted": 19}))
            with self.assertRaises(PublicationError):
                build(*args)
            self.assertFalse((root / "review").exists())


if __name__ == "__main__":
    unittest.main()
