"""Synthetic candidate validation only; not a Wikimedia data collection receipt."""
from datetime import date, datetime, timedelta, timezone
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.rolling_window_gate import WindowError, canonical, read_candidate, validate

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
END = date(2026, 10, 20)
START = END - timedelta(days=34)


def example():
    series = []
    for project, id_, title in [("en.wikipedia", 128, "Example_English"),
                                ("ru.wikipedia", 129, "Тестовая_страница")]:
        series.append({
            "project": project, "page_id": id_, "title": title,
            "access": "all-access", "agent": "user",
            "source": {
                "endpoint": (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
                             f"{project}.org/all-access/user/" +
                             ("Example_English" if id_ == 128 else "%D0%A2%D0%B5%D1%81%D1%82%D0%BE%D0%B2%D0%B0%D1%8F_%D1%81%D1%82%D1%80%D0%B0%D0%BD%D0%B8%D1%86%D0%B0")
                             + "/daily/20260916/20261020"),
                "requested_at": "2026-10-23T11:00:00Z",
                "http_status": 200, "body_sha256": "a" * 64, "response_bytes": 1234,
            },
            "daily": [{"date": (START + timedelta(days=i)).isoformat(),
                       "views": i * 2, "value_state": "observed"} for i in range(35)],
        })
    return {"schema_version": "dayflare.rolling-candidate.v1",
            "dataset_id": "run-20261023", "method_version": "v0-empirical-35d",
            "retrieved_at": "2026-10-23T11:01:00Z", "provider_lag_days": 2,
            "observation_end": "2026-10-20", "series": series}


class RollingGateTests(unittest.TestCase):
    def setUp(self):
        self.doc = example()

    def reject(self, message):
        with self.assertRaises(WindowError) as exc:
            validate(self.doc, now=NOW)
        self.assertIn(message, str(exc.exception))

    def test_complete_35_day_two_editions_zero_is_observed(self):
        report = validate(self.doc, now=NOW)
        self.assertEqual(report["complete_series"], 2)
        self.assertEqual(report["observations"], 70)
        self.assertEqual(report["observation_start"], "2026-09-16")
        self.assertEqual(report["provenance_status"], "self_reported_not_independently_verified")
        self.assertEqual(report["publication_status"], "NOT_STAGED_NOT_DEPLOYED")

    def test_deterministic_input_and_report(self):
        original = canonical(validate(self.doc, now=NOW))
        self.doc["series"].reverse()
        self.assertNotEqual(original, canonical(validate(self.doc, now=NOW)))
        self.doc["series"].reverse()
        self.assertEqual(original, canonical(validate(self.doc, now=NOW)))

    def test_lag_rejects_incomplete_recent_window(self):
        self.doc["provider_lag_days"] = 3
        self.reject("provider-lag")

    def test_stale_is_not_fresh_candidate(self):
        self.doc["observation_end"] = "2026-07-01"
        self.reject("too old")

    def test_missing_duplicate_and_shuffled_days_fail(self):
        for change in ("missing", "duplicate", "swap"):
            with self.subTest(change=change):
                self.doc = example()
                days = self.doc["series"][0]["daily"]
                if change == "missing": days.pop()
                if change == "duplicate": days[1]["date"] = days[0]["date"]
                if change == "swap": days[1], days[2] = days[2], days[1]
                self.reject("history" if change == "missing" else "day")

    def test_unobserved_is_not_zero(self):
        self.doc["series"][0]["daily"][4]["value_state"] = "missing"
        self.reject("not zero")

    def test_infinite_bool_negative_counts_rejected(self):
        for value in (True, -1, 2**53, 2.3):
            with self.subTest(value=value):
                self.doc = example()
                self.doc["series"][0]["daily"][0]["views"] = value
                self.reject("view count")

    def test_title_only_join_and_duplicate_local_ref_rejected(self):
        self.doc["series"][1]["project"] = "en.wikipedia"
        self.doc["series"][1]["page_id"] = 128
        self.reject("duplicate stable")

    def test_endpoint_filters_and_sources_must_match(self):
        for alteration in ("wrong-host", "wrong-agent", "wrong-window", "non-200", "hash"):
            with self.subTest(alteration=alteration):
                self.doc = example()
                s = self.doc["series"][0]
                if alteration == "wrong-host": s["source"]["endpoint"] = s["source"]["endpoint"].replace("wikimedia.org", "example.org")
                if alteration == "wrong-agent": s["agent"] = "all-agents"
                if alteration == "wrong-window": s["source"]["endpoint"] += "0"
                if alteration == "non-200": s["source"]["http_status"] = 503
                if alteration == "hash": s["source"]["body_sha256"] = "INVALID"
                self.reject({"wrong-host":"endpoint", "wrong-agent":"filters", "wrong-window":"endpoint", "non-200":"unsuccessful", "hash":"hash"}[alteration])

    def test_retrieval_chronology_fail_closed(self):
        self.doc["retrieved_at"] = "2026-10-19T11:00:00Z"
        self.reject("retrieval")
        self.doc = example()
        self.doc["series"][0]["source"]["requested_at"] = "2026-10-23T12:00:00Z"
        self.reject("chronology")

    def test_duplicate_json_key_nan_and_oversize_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candidate.json"
            for raw, expected in ((b'{"a":1,"a":2}', "duplicate"),
                                  (b'{"a":NaN}', "non-finite"),
                                  (b' ' * (2 * 1024 * 1024 + 1), "exceeds")):
                path.write_bytes(raw)
                with self.assertRaisesRegex(WindowError, expected):
                    read_candidate(path)

    def test_unknown_fields_and_boolean_provider_lag_rejected(self):
        self.doc["surprise"] = "unvetted"
        self.reject("fields")
        self.doc = example()
        self.doc["provider_lag_days"] = True
        self.reject("lag")


if __name__ == "__main__":
    unittest.main()
