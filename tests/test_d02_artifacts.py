"""Controlled synthetic tests, not actual Wikimedia evidence."""
import copy
from datetime import date, timedelta
import hashlib
import json
import unittest
from io import StringIO
from pathlib import Path
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from types import ModuleType
import sys
from urllib.parse import quote

from tools.verify_d02_artifacts import EvidenceError, validate_artifacts, main

BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
START = "20260811"
END = "20260914"
REQUESTS = [
    {"project": "en.wikipedia.org", "article": "Artificial_intelligence", "subject": "science/technology"},
    {"project": "en.wikipedia.org", "article": "The_Master_and_Margarita", "subject": "culture/literature"},
    {"project": "en.wikipedia.org", "article": "Chess", "subject": "games/sport"},
    {"project": "ru.wikipedia.org", "article": "Искусственный_интеллект", "subject": "science/technology"},
    {"project": "ru.wikipedia.org", "article": "Мастер_и_Маргарита", "subject": "culture/literature"},
    {"project": "ru.wikipedia.org", "article": "Шахматы", "subject": "games/sport"},
]


def sample_data(*, zero=False, omitted=False):
    sample, receipts, metrics = [], [], []
    for idx, spec in enumerate(REQUESTS):
        rows=[]
        for i in range(35):
            missing = omitted and idx == 2 and i == 10
            views = 0 if zero or missing else (i+1)*10
            rows.append({"date": (date(2026,8,11)+timedelta(days=i)).isoformat(),"views":views,
                "project":spec["project"].removesuffix(".org"), "article":spec["article"],
                "access":"all-access","agent":"user","granularity":"daily",
                "value_state":"documented_omitted_zero" if missing else "observed",
                "fill_reason":"wikimedia_time_series_omitted_zero" if missing else None})
        sample.append({"request":spec,"items":rows})
        weekly=[sum(row["views"] for row in rows[o:o+7]) for o in range(0,35,7)]
        older=sorted(weekly[:4]);baseline=(older[1]+older[2])/2; delta=weekly[-1]-baseline
        metric={"weekly_totals_oldest_to_current":weekly,"V":weekly[4],"H1":weekly[3],
                "H2":weekly[2],"H3":weekly[1],"H4":weekly[0],"B":baseline,"delta":delta,
                "relative_lift":None if baseline==0 else delta/baseline}
        metrics.append({"request":spec,"metrics":metric})
        missing_dates=[rows[10]["date"]] if omitted and idx==2 else []
        receipts.append({"project":spec["project"],"article_requested":spec["article"],"subject_area":spec["subject"],
            "endpoint":f'{BASE}/{spec["project"]}/all-access/user/{quote(spec["article"],safe="")}/daily/{START}/{END}',
            "parameters":{"access":"all-access","agent":"user","granularity":"daily","start":START,"end":END},
            "expected_response":{"project":spec["project"].removesuffix(".org"),"article":spec["article"],
                "access":"all-access","agent":"user","granularity":"daily"},
            "request_started_at":"2026-10-03T16:00:00Z","retrieved_at":"2026-10-03T16:00:01Z",
            "http_status":200,"response_bytes":700,"response_sha256":"a"*64,
            "payload_valid":True,"semantic_valid":True,"normalized_complete":True,
            "semantic_errors":[],"unresolved_days":[],"expected_days":35,"item_count_normalized":35,
            "item_count_raw":34 if missing_dates else 35,"missing_days_raw":missing_dates,
            "omitted_zero_days":missing_dates,"error":None,"parse_error":None})
    manifest={"schema_version":1,"probe":"D02","method_version":"v0-empirical-35d",
        "run_started_at":"2026-10-03T16:00:00Z","run_finished_at":"2026-10-03T16:00:10Z",
        "observation_window":{"start":START,"end":END,"expected_days":35},"thresholds_frozen":False,
        "request_count":6,"receipts":receipts,"series_metrics":metrics,"success":True,
        "window_semantics": {"window_days":7,"V":"most recent complete 7-day total",
          "H1_H4":"four immediately preceding complete 7-day totals, newest to oldest",
          "B":"median(H1,H2,H3,H4)","delta":"V-B",
          "relative_lift":"(V-B)/B, undefined when B=0"}}
    return sample,manifest


def encode(sample, receipt):
    raw=json.dumps(sample,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf8")
    receipt=copy.deepcopy(receipt)
    receipt["normalized_sample_sha256"]=hashlib.sha256(raw).hexdigest()
    return raw+b"\n",json.dumps(receipt,ensure_ascii=False).encode("utf8")


def check(sample, receipt):
    sample_bytes,receipt_bytes=encode(sample,receipt)
    return validate_artifacts(sample_bytes,receipt_bytes,requests=REQUESTS,start=START,end=END,base_url=BASE)


class IntegrityTests(unittest.TestCase):
    def test_good_historical_bounded_sample(self):
        s,r=sample_data()
        result=check(s,r)
        self.assertEqual(result["observations"],210)
        self.assertEqual(result["series"],6)
    def test_documented_zero_normalization(self):
        s,r=sample_data(omitted=True)
        self.assertTrue(check(s,r)["valid"])
    def test_zero_baseline_has_null_lift(self):
        s,r=sample_data(zero=True)
        self.assertTrue(check(s,r)["valid"])
    def test_mutated_sample_without_digest_update(self):
        s,r=sample_data()
        sb,rb=encode(s,r)
        damaged=sb.replace(b'"views":10',b'"views":11',1)
        with self.assertRaisesRegex(EvidenceError,"checksum"):
            validate_artifacts(damaged,rb,requests=REQUESTS,start=START,end=END,base_url=BASE)
    def test_mismatched_metrics_even_with_updated_digest(self):
        s,r=sample_data()
        r["series_metrics"][0]["metrics"]["delta"]+=10
        with self.assertRaisesRegex(EvidenceError,"differs from recomputation"):
            check(s,r)
    def test_missing_day(self):
        s,r=sample_data()
        s[1]["items"].pop()
        with self.assertRaisesRegex(EvidenceError,"incomplete daily"):
            check(s,r)
    def test_unsafe_views_even_with_updated_digest(self):
        s,r=sample_data()
        s[1]["items"][0]["views"]=2**53
        with self.assertRaisesRegex(EvidenceError,"inexact view count"):
            check(s,r)
    def test_wrong_filters(self):
        s,r=sample_data()
        r["receipts"][3]["parameters"]["agent"]="all-agents"
        with self.assertRaisesRegex(EvidenceError,"incompatible filters"):
            check(s,r)
    def test_false_success(self):
        s,r=sample_data()
        r["success"]=False
        with self.assertRaisesRegex(EvidenceError,"did not succeed"):
            check(s,r)
    def test_omitted_zero_with_nonzero_views(self):
        s,r=sample_data(omitted=True)
        s[2]["items"][10]["views"]=3
        with self.assertRaisesRegex(EvidenceError,"invalid zero normalization"):
            check(s,r)
    def test_incomplete_body_flag(self):
        s,r=sample_data()
        r["receipts"][0]["response_body_complete"]=False
        with self.assertRaisesRegex(EvidenceError,"incomplete HTTP response"):
            check(s,r)
    def test_noncanonical_sample(self):
        s,r=sample_data()
        sb,rb=encode(s,r)
        with self.assertRaisesRegex(EvidenceError,"not the collector's canonical"):
            validate_artifacts(sb+b"\n",rb,requests=REQUESTS,start=START,end=END,base_url=BASE)
    def test_duplicate_json_object_keys(self):
        s,r=sample_data()
        sb,rb=encode(s,r)
        corrupted=rb.replace(b'"probe": "D02"',b'"probe": "D02", "probe": "D02"')
        with self.assertRaisesRegex(EvidenceError,"duplicate JSON key"):
            validate_artifacts(sb,corrupted,requests=REQUESTS,start=START,end=END,base_url=BASE)
    def test_malformed_receipt_timestamp(self):
        s,r=sample_data()
        r["receipts"][0]["request_started_at"]="yesterday"
        with self.assertRaisesRegex(EvidenceError,"invalid timestamp"):
            check(s,r)
    def test_reordered_history(self):
        s,r=sample_data()
        s[2]["items"][0],s[2]["items"][1]=s[2]["items"][1],s[2]["items"][0]
        with self.assertRaisesRegex(EvidenceError,"reordered date"):
            check(s,r)
    def test_weekly_integer_overflow(self):
        s,r=sample_data()
        for x in s[0]["items"][:7]: x["views"]=2**53-1
        with self.assertRaisesRegex(EvidenceError,"inexact weekly total"):
            check(s,r)
    def test_wrong_article(self):
        s,r=sample_data()
        s[0]["items"][5]["article"]="Other"
        with self.assertRaisesRegex(EvidenceError,"page identity mismatch"):
            check(s,r)

    def test_method_window_semantics_cannot_silently_change(self):
        s,r=sample_data()
        r["window_semantics"]["window_days"]=5
        with self.assertRaisesRegex(EvidenceError,"method window semantics"):
            check(s,r)

    def test_truncated_upstream_body_even_with_good_sample_hash(self):
        s,r=sample_data()
        r["receipts"][0]["response_truncated"]=True
        with self.assertRaisesRegex(EvidenceError,"truncated HTTP response"):
            check(s,r)

    def test_relative_lift_must_match_recomputed_float(self):
        s,r=sample_data()
        r["series_metrics"][0]["metrics"]["relative_lift"] += 1e-10
        with self.assertRaisesRegex(EvidenceError,"relative lift mismatch"):
            check(s,r)

    def test_cli_success_and_rejects_failure_without_overwriting_inputs(self):
        s,r=sample_data()
        sb,rb=encode(s,r)
        d01,d02=ModuleType("tools.d01_probe"),ModuleType("tools.d02_probe")
        d01.REQUESTS=REQUESTS; d01.BASE=BASE
        d02.START=START; d02.END=END
        with tempfile.TemporaryDirectory() as td, patch.dict(sys.modules,{"tools.d01_probe":d01,"tools.d02_probe":d02}):
            sp,rp=Path(td)/"sample.json",Path(td)/"receipt.json"
            sp.write_bytes(sb);rp.write_bytes(rb)
            with redirect_stdout(StringIO()) as stdout:
                self.assertEqual(main(["--sample",str(sp),"--receipt",str(rp)]),0)
            self.assertIn('"observations": 210',stdout.getvalue())
            bad=copy.deepcopy(r);bad["success"]=False
            _,bad_bytes=encode(s,bad)
            rp.write_bytes(bad_bytes)
            with redirect_stderr(StringIO()) as stderr:
                self.assertEqual(main(["--sample",str(sp),"--receipt",str(rp)]),2)
            self.assertIn("D02_ARTIFACT_INVALID",stderr.getvalue())
            self.assertEqual(sp.read_bytes(),sb)
            self.assertEqual(rp.read_bytes(),bad_bytes)


if __name__=="__main__":
    unittest.main()
