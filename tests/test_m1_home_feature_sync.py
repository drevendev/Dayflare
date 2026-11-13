"""Fail-closed source-derived current M1 first-screen examples (offline tests)."""
from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import tempfile
import unittest

from tools.m1_home_feature_sync import (
    END, START, render_feature, run, source_examples, synchronize,
)
from tools.m1_home_window_sync import render_window
from tools.m1_readme_sync import SyncError, digest, render as render_readme

ROOT = Path(__file__).resolve().parents[1]
REVISION = "c30b253e96a29cde1f14cc59fd08878b74997323"
END_DAY = date(2026, 11, 8)
RETRIEVED = datetime(2026, 11, 11, 6, 31, 2)


def sample_source(*, title: str = "Компьютерная игра", first_id: str = "detail-ru-wikipedia-7638") -> bytes:
    return (
        '<!doctype html><html><body><section class="spotlights" aria-labelledby="spotlight-heading">'
        '<a class="spotlight" href="#' + first_id + '">'
        '<span class="badge">Largest increase · RU</span><strong>' + title + '</strong>'
        '<span class="spotlight-number">+625 requests vs four-week median</span>'
        '<span class="spotlight-context">Last complete UTC week 2026-11-02–2026-11-08: '
        '2,310 requests; preceding four-week median 1,685 requests.</span>'
        '<span>Inspect 35 exact UTC days ↗</span></a>'
        '<a class="spotlight" href="#detail-en-wikipedia-4650">'
        '<span class="badge">Largest decrease · EN</span><strong>Black hole</strong>'
        '<span class="spotlight-number">−17,031.5 requests vs four-week median</span>'
        '<span class="spotlight-context">Last complete UTC week 2026-11-02–2026-11-08: '
        '34,136 requests; preceding four-week median 51,167.5 requests.</span>'
        '<span>Inspect 35 exact UTC days ↗</span></a></section>'
        '<article id="' + first_id + '">Full 35-day evidence</article>'
        '<article id="detail-en-wikipedia-4650">Full 35-day evidence</article>'
        '</body></html>'
    ).encode("utf-8")


def manifest_for(source: bytes) -> dict:
    return {
        "candidate_sha256": "a" * 64,
        "daily_observations": 700,
        "dataset_id": "run-20261111-063102-a32c03ef7daa",
        "html_sha256": digest(source),
        "method_version": "v0-empirical-35d",
        "observation_end": END_DAY.isoformat(),
        "retrieved_at": "2026-11-11T06:31:02Z",
        "schema_version": "dayflare.m1.static-snapshot.v1",
        "series": 20,
        "source_receipt_sha256": "b" * 64,
        "source_seed_sha256": "c" * 64,
        "status": "DATED_ARCHIVE_NOT_LIVE",
    }


class AcceptedM1FirstScreenTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.release = self.root / "accepted"
        self.release.mkdir()
        self.site = self.root / "site.html"
        self.readme = self.root / "README.md"
        self.site.write_text(
            render_window(END_DAY, RETRIEVED) + "\n" + START + "\nOLD\n" + END,
            encoding="utf-8",
        )
        self.make_release(sample_source())

    def make_release(self, source: bytes):
        (self.release / "index.html").write_bytes(source)
        self.manifest = manifest_for(source)
        raw = (json.dumps(self.manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        (self.release / "release-manifest.json").write_bytes(raw)
        self.pin = digest(raw)
        from tools.m1_readme_sync import accepted_manifest
        self.manifest = accepted_manifest(self.release, self.pin)
        self.readme.write_text(render_readme(self.manifest), encoding="utf-8")

    def sync(self, *, write: bool = False, pin: str | None = None,
             revision: str = REVISION):
        return run(self.site, self.readme, self.release, pin or self.pin,
                   revision, write=write)

    def test_current_two_examples_are_source_derived_and_stable(self):
        original = self.site.read_bytes()
        with self.assertRaisesRegex(SyncError, "use --write"):
            self.sync()
        self.assertEqual(self.site.read_bytes(), original)
        self.assertTrue(self.sync(write=True))
        rendered = self.site.read_text(encoding="utf-8")
        self.assertEqual(rendered.count('class="m1-home-example"'), 2)
        self.assertIn("Компьютерная игра", rendered)
        self.assertIn("Black hole", rendered)
        self.assertIn("+625 requests vs four-week median", rendered)
        self.assertIn("−17,031.5 requests vs four-week median", rendered)
        self.assertIn('data-dataset-id="run-20261111-063102-a32c03ef7daa"', rendered)
        self.assertIn('data-html-sha256="' + self.manifest["html_sha256"] + '"', rendered)
        self.assertEqual(rendered.count(REVISION + "/m1/index.html"), 2)
        self.assertIn('data-m1-detail="detail-ru-wikipedia-7638"', rendered)
        self.assertFalse(self.sync())
        self.assertFalse(self.sync(write=True))

    def test_bad_pin_modified_source_and_stale_date_fail_without_writes(self):
        old = self.site.read_bytes()
        with self.assertRaisesRegex(SyncError, "independent"):
            self.sync(write=True, pin="0" * 64)
        self.assertEqual(self.site.read_bytes(), old)
        (self.release / "index.html").write_text("modified after approval", encoding="utf-8")
        with self.assertRaisesRegex(SyncError, "HTML differs"):
            self.sync(write=True)
        self.assertEqual(self.site.read_bytes(), old)
        self.make_release(sample_source())
        self.site.write_text(
            render_window(date(2026, 11, 7), datetime(2026, 11, 10, 6, 31, 2))
            + "\n" + START + "\nOLD\n" + END, encoding="utf-8"
        )
        old = self.site.read_bytes()
        with self.assertRaisesRegex(SyncError, "dates must first match"):
            self.sync(write=True)
        self.assertEqual(self.site.read_bytes(), old)

    def test_duplicate_or_missing_evidence_links_fail_closed(self):
        for bad in (
            sample_source().decode().replace('id="detail-en-wikipedia-4650"', "id=\"missing\""),
            sample_source().decode().replace(
                '<article id="detail-en-wikipedia-4650">',
                '<article id="detail-en-wikipedia-4650">'
                '<article id="detail-en-wikipedia-4650">'
            ),
            sample_source().decode().replace("Largest decrease", "Largest increase"),
        ):
            self.make_release(bad.encode("utf-8"))
            old = self.site.read_bytes()
            with self.assertRaises(SyncError):
                self.sync(write=True)
            self.assertEqual(self.site.read_bytes(), old)

    def test_escapes_title_and_rejects_untrusted_revision_and_bad_markers(self):
        source = sample_source(title="Chess &lt;script&gt;")
        safe = render_feature(source.decode(), manifest_for(source), REVISION)
        self.assertIn("Chess &lt;script&gt;", safe)
        self.assertNotIn("<script>", safe)
        with self.assertRaisesRegex(SyncError, "revision"):
            render_feature(source.decode(), manifest_for(source), "gh-pages")
        with self.assertRaisesRegex(SyncError, "duplicate"):
            synchronize(START + "\nOLD\n" + END + START + END, "new")
        self.make_release(source)
        self.assertTrue(self.sync(write=True))

    def test_shipped_first_screen_prioritizes_accepted_snapshot(self):
        site = (ROOT / "site/index.html").read_text(encoding="utf-8")
        app = (ROOT / "site/app.js").read_text(encoding="utf-8")
        self.assertLess(site.index('id="m1-spotlight-title"'), site.index('id="spotlight-title"'))
        self.assertLess(site.index('id="m1-spotlight-title"'), site.index("<!-- M1_DEMO_START"))
        self.assertIn('data-observation-end="2026-11-10"', site)
        self.assertIn("run-20261113-032300-a32c03ef7daa", site)
        self.assertIn("e0e7ec6443dc8a34362c5165e7a294d9925118a3f8fbc02477d769078e4db13a", site)
        self.assertEqual(site.count(REVISION + "/m1/index.html"), 2)
        self.assertIn('<details class="m0-archive">', site)
        # The top keyboard shortcut goes to accepted M1 rather than August M0.
        self.assertIn('<a class="skip" href="#latest-atlas">Skip to latest accepted M1 atlas</a>', site)
        self.assertIn('id="latest-atlas" href=', site)
        self.assertIn('the Chess six-series and October examples further down are older, separately dated samples.', site)
        self.assertNotIn('the examples below are earlier, separately dated samples.', site)
        self.assertIn("EARLIER SAMPLE / CHESS · EN", site)
        self.assertIn("data-m1-detail", app)
        self.assertIn("manifest.html_sha256 !== evidence.dataset.htmlSha256", app)
        self.assertIn("location.hostname === 'drevendev.github.io'", app)


if __name__ == "__main__":
    unittest.main()
