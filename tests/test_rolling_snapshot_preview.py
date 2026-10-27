"""Synthetic-only offline preview coverage; never evidence of live Wikimedia retrieval."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest

from tools.rolling_pageview_source import FetchResult, SourceError, canonical, collect_to_new_directory, sha
from tools.rolling_snapshot_preview import export_verified_preview, render_html, _lift

NOW = datetime(2026, 10, 24, 3, 1, 2, tzinfo=timezone.utc)
START = date(2026, 9, 17)


def seed():
    return {"schema_version": "dayflare.rolling-pageview-seeds.v1",
            "selected_at": "2026-10-20", "method_version": "v0-empirical-35d",
            "provider_lag_days": 2,
            "pages": [
                {"project": "en.wikipedia", "page_id": 1234,
                 "title": "Chess & <svg onload='bad()'>", "subject": "sport"},
                {"project": "ru.wikipedia", "page_id": 5678,
                 "title": "Шахматы", "subject": "culture"}]}


def fake(url):
    ru = "/ru.wikipedia.org/" in url
    title = "Шахматы" if ru else "Chess & <svg onload='bad()'>"
    project = "ru.wikipedia" if ru else "en.wikipedia"
    payload = canonical({"items": [
        {"project": project, "article": title, "access": "all-access",
         "agent": "user", "granularity": "daily",
         "timestamp": (START + timedelta(days=i)).strftime("%Y%m%d00"),
         "views": 0 if ru else i + 1}
        for i in range(35)]})
    return FetchResult(200, payload, len(payload), sha(payload), "identity")


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seedfile = self.root / "seed.json"
        self.seedfile.write_bytes(canonical(seed()))
        self.source = self.root / "source"
        collect_to_new_directory(self.seedfile, self.source, now=lambda: NOW,
                                 fetch=fake, sleep=lambda _: None, injected=True)

    def export(self, name):
        return export_verified_preview(self.source, self.root / name, now=NOW)

    def test_full_local_visitor_journey_and_exact_values(self):
        manifest = self.export("preview")
        self.assertEqual(manifest["publication_status"], "LOCAL_PREVIEW_NOT_PUBLISHED")
        self.assertEqual(manifest["series"], 2)
        self.assertEqual(manifest["provenance_status"], "synthetic_injected_not_upstream_evidence")
        html = (self.root / "preview" / "index.html").read_text()
        self.assertEqual(sha256(html.encode()).hexdigest(), manifest["html_sha256"])
        self.assertIn('SYNTHETIC TEST DATA — NOT WIKIPEDIA EVIDENCE', html)
        self.assertIn('2026-09-17 – 2026-10-21 UTC', html)
        self.assertIn('href="#detail-en-wikipedia-1234"', html)
        self.assertIn('id="detail-ru-wikipedia-5678"', html)
        self.assertIn('>Шахматы</h3>', html)
        self.assertNotIn("<svg onload=", html)
        self.assertIn('&lt;svg onload=&#x27;bad()&#x27;&gt;', html)
        self.assertIn('>224</td>', html)  # 29+30+31+32+33+34+35 = 224
        self.assertIn('>0</td>', html)  # explicit observed zeros, not inferred
        self.assertIn('35 exact daily', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn('prefers-reduced-motion', html)
        self.assertIn('aria-label="Scrollable weekly comparison table"', html)
        self.assertNotIn('<script', html)
        self.assertEqual(set(p.name for p in (self.root / "preview").iterdir()),
                         {"index.html", "preview-manifest.json"})

    def test_independent_exports_are_deterministic_and_no_overwrite(self):
        a = self.export("first")
        b = self.export("second")
        self.assertEqual(a, b)
        self.assertEqual((self.root/"first"/"index.html").read_bytes(),
                         (self.root/"second"/"index.html").read_bytes())
        old = (self.root/"first"/"index.html").read_bytes()
        with self.assertRaisesRegex(SourceError, "already exists"):
            self.export("first")
        self.assertEqual((self.root/"first"/"index.html").read_bytes(), old)

    def test_reject_tampered_raw_before_output(self):
        path = self.source / "raw" / "en.wikipedia.1234.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(SourceError, "hash mismatch"):
            self.export("rejected")
        self.assertFalse((self.root/"rejected").exists())

    def test_reject_tampered_candidate_and_missing_parent(self):
        path = self.source / "candidate.json"
        original = path.read_bytes()
        doc = json.loads(original)
        doc["series"][0]["daily"][0]["views"] = 999
        path.write_bytes(canonical(doc))
        with self.assertRaisesRegex(SourceError, "source|receipt|candidate"):
            self.export("rejected")
        self.assertFalse((self.root/"rejected").exists())
        path.write_bytes(original)
        with self.assertRaisesRegex(SourceError, "parent"):
            export_verified_preview(self.source, self.root / "missing" / "preview", now=NOW)

    def test_zero_baseline_is_not_invented_percent(self):
        self.assertEqual(_lift(0, 0), "Unavailable (zero baseline)")
        html = (self.root / "zero").exists()
        self.assertFalse(html)
        self.export("zero")
        self.assertIn('Unavailable (zero baseline)',
                      (self.root/"zero"/"index.html").read_text())


if __name__ == "__main__":
    unittest.main()
