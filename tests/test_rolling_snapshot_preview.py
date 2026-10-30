"""Synthetic-only offline preview coverage; never evidence of live Wikimedia retrieval."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import shutil
import tempfile
import unittest

from tools.rolling_pageview_source import (
    FetchResult, SourceError, canonical, collect_to_new_directory, sha,
    stage_verified_bundle,
)
from tools.rolling_snapshot_preview import (
    export_staged_current_preview, export_verified_preview, main, render_html, _lift,
    _weekly_bars,
)
from tools.stage_rolling_version import StageError, stage

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
        self.assertIn('id="atlas-filters" aria-label="Filter selected titles" hidden', html)
        self.assertIn('id="atlas-query" type="search"', html)
        self.assertIn('id="atlas-order"', html)
        self.assertIn('#atlas-filters label{display:grid;gap:.25rem;font-weight:650;min-width:0}', html)
        self.assertIn('#atlas-filters select{width:100%;min-width:0}', html)
        self.assertIn('<option value="increase">Largest weekly increase (requests)</option>', html)
        self.assertIn('data-delta2="245"', html)  # +122.5 requests, doubled exactly
        self.assertIn('data-delta2="0"', html)
        self.assertIn('BigInt(a.dataset.delta2)', html)
        self.assertIn('compareBody.appendChild(rowBySeries.get(card.dataset.series))', html)
        self.assertIn('params.getAll("af_sort").length > 1', html)
        self.assertIn('url.searchParams.set("af_sort", order.value)', html)
        self.assertIn('Array.from(compareBody.querySelectorAll("tr"))', html)
        self.assertIn('id="atlas-results" role="status" aria-live="polite"', html)
        self.assertIn('All 2 selected titles shown.', html)
        self.assertIn('id="compare-table"', html)
        self.assertIn('id="compare-results"', html)
        self.assertIn('All 2 selected title histories compared.', html)
        self.assertIn('id="compare-empty" hidden', html)
        self.assertIn('id="compare-csv" hidden>Download visible weekly CSV</button>', html)
        self.assertIn('id="compare-csv-status" role="status" aria-live="polite"', html)
        self.assertIn('data-week-start="2026-09-17" data-week-end="2026-09-23"', html)
        self.assertIn('data-week-start="2026-10-15" data-week-end="2026-10-21"', html)
        self.assertIn('csvButton.disabled = shown === 0', html)
        self.assertIn('"dataset_sha256", "method_version", "observation_end_utc"', html)
        self.assertIn('last_week_minus_four_week_median_requests', html)
        self.assertIn('data-series="detail-en-wikipedia-1234" data-title=', html)
        self.assertIn('<tr data-series="detail-ru-wikipedia-5678">', html)
        self.assertIn('row.hidden = !visible.has(row.dataset.series)', html)
        self.assertIn('data-title="Chess &amp; &lt;svg onload=&#x27;bad()&#x27;&gt;"', html)
        self.assertIn('data-edition="ru.wikipedia" data-subject="culture"', html)
        self.assertIn('<option value="culture">Culture</option>', html)
        self.assertIn('No matching titles in this selected archive.', html)
        self.assertIn('form.hidden = false', html)
        self.assertIn('id="atlas-filter-link" class="filter-link" href="#overview" hidden', html)
        self.assertIn('id="atlas-filter-warning" class="filter-warning" role="alert" hidden', html)
        self.assertIn('"af_dataset", "af_query", "af_edition", "af_subject"', html)
        self.assertIn('snapshot.dataset.dataset', html)
        self.assertIn('params.getAll(key).length !== 1', html)
        self.assertIn('card.hidden = !match', html)
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
        self.assertIn('<script>', html)
        self.assertNotIn('<script src=', html)
        self.assertEqual(set(p.name for p in (self.root / "preview").iterdir()),
                         {"index.html", "preview-manifest.json"})

    def test_weekly_bars_have_zero_origin_and_exact_accessible_values(self):
        self.export("weekly-bars")
        html = (self.root / "weekly-bars" / "index.html").read_text()
        self.assertEqual(html.count('class="week-bars" role="img"'), 2)
        self.assertIn(
            'aria-label="Weekly requests, oldest to newest: '
            'week 1 28; week 2 77; week 3 126; week 4 175; week 5 224"',
            html)
        self.assertIn(
            'aria-label="Weekly requests, oldest to newest: '
            'week 1 0; week 2 0; week 3 0; week 4 0; week 5 0"',
            html)
        self.assertIn('style="height:13%"', html)  # Week 1: 28 / 224
        self.assertIn('style="height:100%"', html)
        self.assertIn('style="height:0%"', html)
        self.assertIn('bars start at zero', html)
        self.assertIn('each title has its own scale', html)
        self.assertIn('href="#compare">Exact weekly values</a>', html)
        self.assertEqual(_weekly_bars([0, 0, 0, 0, 0]).count('height:0%'), 5)
        with self.assertRaisesRegex(ValueError, "five nonnegative"):
            _weekly_bars([1, -1, 2, 3, 4])
        with self.assertRaisesRegex(ValueError, "five nonnegative"):
            _weekly_bars([1, 2, 3, 4])
        self.assertIn('<script>', html)
        self.assertNotIn('<script src=', html)

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


    def reported_transport_stage(self):
        # Simulated, not authenticated Wikimedia transport: only the receipt
        # contract and local version binding are under test here.
        bundle = self.root / "simulated-runtime-reported-source"
        collect_to_new_directory(self.seedfile, bundle, now=lambda: NOW,
                                 fetch=fake, sleep=lambda _: None, injected=False)
        stage_root = self.root / "staged"
        staged = stage_verified_bundle(bundle, stage_root, now=NOW)
        return bundle, stage_root, staged

    def test_current_source_stage_exports_identical_atlas_after_original_bundle_removed(self):
        bundle, stage_root, staged = self.reported_transport_stage()
        direct = export_verified_preview(bundle, self.root / "direct", now=NOW)
        shutil.rmtree(bundle)
        from_stage = export_staged_current_preview(stage_root, self.root / "from-stage")
        self.assertEqual(from_stage, direct)
        self.assertEqual(from_stage["candidate_sha256"],
                         staged["local_stage"]["version_sha256"])
        self.assertEqual(from_stage["provenance_status"],
                         "runtime_reported_transport_not_independently_authenticated")
        self.assertEqual((self.root / "direct" / "index.html").read_bytes(),
                         (self.root / "from-stage" / "index.html").read_bytes())
        html = (self.root / "from-stage" / "index.html").read_text()
        self.assertIn('LOCAL EVIDENCE — UPSTREAM ORIGIN NOT INDEPENDENTLY VERIFIED', html)
        self.assertIn('href="#detail-en-wikipedia-1234"', html)
        self.assertNotIn('SYNTHETIC TEST DATA — NOT WIKIPEDIA EVIDENCE', html)
        # Also exercise the public command-line mode, not just the helper.
        self.assertEqual(main(["--from-stage", str(stage_root), str(self.root / "cli")]), 0)
        self.assertEqual((self.root / "cli" / "index.html").read_bytes(),
                         (self.root / "direct" / "index.html").read_bytes())

    def test_corrupted_current_source_never_replaces_previous_preview(self):
        _, stage_root, staged = self.reported_transport_stage()
        self_export = self.root / "last-good-preview"
        export_staged_current_preview(stage_root, self_export)
        old_html = (self_export / "index.html").read_bytes()
        old_manifest = (self_export / "preview-manifest.json").read_bytes()
        old_pointer = (stage_root / "current.json").read_bytes()
        retained = (stage_root / "versions" /
                    staged["local_stage"]["version_sha256"] /
                    "source" / "raw" / "en.wikipedia.1234.json")
        retained.write_bytes(retained.read_bytes() + b" ")
        with self.assertRaisesRegex(StageError, "retained-body verification"):
            export_staged_current_preview(stage_root, self.root / "bad-preview")
        self.assertFalse((self.root / "bad-preview").exists())
        self.assertEqual((self_export / "index.html").read_bytes(), old_html)
        self.assertEqual((self_export / "preview-manifest.json").read_bytes(), old_manifest)
        self.assertEqual((stage_root / "current.json").read_bytes(), old_pointer)

    def test_stage_export_rejects_missing_pointer_and_candidate_only_v1(self):
        empty = self.root / "empty-stage"
        (empty / "versions").mkdir(parents=True)
        with self.assertRaisesRegex(StageError, "no current staged version"):
            export_staged_current_preview(empty, self.root / "missing-preview")
        self.assertFalse((self.root / "missing-preview").exists())

        candidate_only = self.root / "candidate-only"
        stage(json.loads((self.source / "candidate.json").read_bytes()),
              candidate_only, now=NOW)
        with self.assertRaisesRegex(StageError, "candidate-only v1"):
            export_staged_current_preview(candidate_only, self.root / "v1-preview")
        self.assertFalse((self.root / "v1-preview").exists())



if __name__ == "__main__":
    unittest.main()
