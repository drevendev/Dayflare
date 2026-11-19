"""Fail-closed source-derived current M1 first-screen examples (offline tests)."""
from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import tempfile
import unittest

from tools.m1_home_feature_sync import (
    END, START, pin_primary_entry, render_feature, run, source_examples, synchronize,
)
from tools.m1_home_window_sync import render_window
from tools.m1_readme_sync import SyncError, digest, render as render_readme

ROOT = Path(__file__).resolve().parents[1]
REVISION = "4851d6a7e106f02261b6e7a58226295ac94a664d"
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
            '<a class="primary" id="latest-atlas" href="https://raw.githubusercontent.com/drevendev/Dayflare/gh-pages/m1/index.html">Download</a>'
            + render_window(END_DAY, RETRIEVED) + "\n" + START + "\nOLD\n" + END,
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
        self.assertEqual(rendered.count('class="m1-home-bars"'), 2)
        self.assertIn('Zero-origin weekly requests for Компьютерная игра', rendered)
        self.assertIn('style="width:72.9%"', rendered)  # 1,685 / 2,310
        self.assertIn('style="width:66.7%"', rendered)  # 34,136 / 51,167.5
        self.assertIn('<strong class="m1-home-bar-value">2,310</strong>', rendered)
        self.assertIn('<strong class="m1-home-bar-value">51,167.5</strong>', rendered)
        self.assertIn("Компьютерная игра", rendered)
        self.assertIn("Black hole", rendered)
        self.assertIn("+625 requests vs four-week median", rendered)
        self.assertIn("−17,031.5 requests vs four-week median", rendered)
        self.assertIn('data-dataset-id="run-20261111-063102-a32c03ef7daa"', rendered)
        self.assertIn('data-html-sha256="' + self.manifest["html_sha256"] + '"', rendered)
        self.assertEqual(rendered.count(REVISION + "/m1/index.html"), 3)
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


    def test_spotlight_chart_rejects_mismatched_or_malformed_weekly_values(self):
        original = self.site.read_bytes()
        for broken in (
            sample_source().replace(b"+625 requests", b"+626 requests"),
            sample_source().replace(b"1,685 requests", b"1,684 requests"),
            sample_source().replace(b"2,310 requests", b"2,310.25 requests"),
            sample_source().replace(b"34,136 requests", b"bad requests"),
        ):
            with self.subTest(broken=broken[-100:]):
                self.make_release(broken)
                with self.assertRaisesRegex(SyncError, "weekly evidence|change disagrees"):
                    self.sync(write=True)
                self.assertEqual(self.site.read_bytes(), original)

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

    def test_primary_entry_is_pinned_and_fails_closed_for_unsafe_routes(self):
        original = self.site.read_text(encoding="utf-8")
        self.assertIn("/gh-pages/m1/index.html", original)
        pinned = pin_primary_entry(original, REVISION)
        self.assertIn(REVISION + "/m1/index.html", pinned)
        self.assertNotIn("/gh-pages/m1/index.html", pinned)
        for broken in (
            original.replace('id="latest-atlas"', 'id="unrelated"'),
            original.replace("/gh-pages/m1/index.html", "/unreviewed/m1/index.html"),
            original + original.split(render_window(END_DAY, RETRIEVED))[0],
        ):
            with self.subTest(broken=broken[-80:]):
                self.site.write_text(broken, encoding="utf-8")
                with self.assertRaisesRegex(SyncError, "primary"):
                    self.sync(write=True)
                self.assertEqual(self.site.read_text(encoding="utf-8"), broken)

    def test_shipped_first_screen_prioritizes_accepted_snapshot(self):
        site = (ROOT / "site/index.html").read_text(encoding="utf-8")
        app = (ROOT / "site/app.js").read_text(encoding="utf-8")
        self.assertLess(site.index('id="m1-spotlight-title"'), site.index('id="spotlight-title"'))
        self.assertLess(site.index('id="m1-spotlight-title"'), site.index("<!-- M1_DEMO_START"))
        self.assertIn('data-observation-end="2026-11-11"', site)
        self.assertEqual(site.count('class="m1-home-bars"'), 2)
        self.assertIn('style="width:96.4%"', site)  # Chess baseline/final
        self.assertIn('style="width:64.1%"', site)  # Black hole final/baseline
        self.assertIn("run-20261114-163048-a32c03ef7daa", site)
        self.assertIn("4553257f5b16dd3a94d18fd19bea9b3289a670c85055ee231f6a2289f2a7d85f", site)
        self.assertEqual(site.count(REVISION + "/m1/index.html"), 13)
        self.assertIn('id="latest-atlas" href="https://raw.githubusercontent.com/drevendev/Dayflare/' + REVISION + '/m1/index.html"', site)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('**[Download the accepted M1 atlas (11 Nov 2026; pinned HTML)](https://raw.githubusercontent.com/drevendev/Dayflare/' + REVISION + '/m1/index.html)**', readme)
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


    def test_first_screen_offers_in_browser_dated_archive_discovery(self):
        """The latest download stays pinned; the directly browsable October atlas is obvious."""
        page = (ROOT / "site/index.html").read_text(encoding="utf-8")
        curated = (ROOT / "site/m1-curated-20261023.html").read_text(encoding="utf-8")
        css = (ROOT / "site/styles.css").read_text(encoding="utf-8")
        self.assertIn('id="curated-tools"', curated)
        self.assertEqual(page.count('class="hero-actions"'), 1)
        self.assertEqual(page.count('class="hero-explore"'), 1)
        self.assertIn('class="hero-explore" href="m1-curated-20261023.html#curated-tools"', page)
        self.assertIn('Earlier archive · 19 Sep–23 Oct 2026', page)
        self.assertLess(page.index('class="hero-explore"'), page.index('class="hero-foot"'))
        self.assertIn('id="latest-atlas" href="https://raw.githubusercontent.com/drevendev/Dayflare/' + REVISION + '/m1/index.html"', page)
        self.assertIn(".hero-explore{display:inline-flex", css)
        self.assertIn(".hero-actions a{width:100%}", css)
        self.assertIn("a:focus-visible", css)



    def test_pinned_bilingual_subject_discovery_is_dated_and_safe(self):
        """Ten independent EN/RU examples from the accepted 11 Nov M1 cards."""
        site = (ROOT / "site/index.html").read_text(encoding="utf-8")
        app = (ROOT / "site/app.js").read_text(encoding="utf-8")
        css = (ROOT / "site/styles.css").read_text(encoding="utf-8")
        start = site.index('<details id="m1-subject-quicklinks"')
        stop = site.index('</details>', start) + len('</details>')
        section = site[start:stop]
        self.assertEqual(site.count('id="m1-subject-quicklinks"'), 1)
        self.assertIn('data-observation-end="2026-11-11"', section)
        self.assertIn('5–11 Nov 2026 UTC', section)
        self.assertIn('not verified identity matches or population comparisons', section)
        self.assertEqual(section.count('class="m1-subject-pair"'), 5)
        self.assertEqual(section.count('class="m1-subject-item"'), 10)
        self.assertEqual(section.count('data-m1-detail='), 10)
        self.assertEqual(section.count(REVISION + '/m1/index.html'), 10)
        expected = [
            ("detail-en-wikipedia-155311", "War and Peace", "−1,131.5 requests", "12,385 requests"),
            ("detail-ru-wikipedia-6269", "Война и мир", "+38 requests", "3,945 requests"),
            ("detail-en-wikipedia-18839", "Music", "−1,566.5 requests", "15,707 requests"),
            ("detail-ru-wikipedia-463", "Музыка", "−513.5 requests", "1,320 requests"),
            ("detail-en-wikipedia-5134", "Chess", "+916.5 requests", "25,147 requests"),
            ("detail-ru-wikipedia-7638", "Компьютерная игра", "+649.5 requests", "2,453 requests"),
            ("detail-en-wikipedia-4650", "Black hole", "−17,404 requests", "31,062 requests"),
            ("detail-ru-wikipedia-4665", "Квантовая механика", "−143 requests", "1,313 requests"),
            ("detail-en-wikipedia-23976719", "Football", "−1,113 requests", "7,932 requests"),
            ("detail-ru-wikipedia-7963", "Футбол", "+248.5 requests", "3,337 requests"),
        ]
        for detail, title, change, final in expected:
            with self.subTest(detail=detail):
                self.assertEqual(section.count('data-m1-detail="' + detail + '"'), 1)
                self.assertIn(title, section)
                self.assertIn('>' + change + '</span>', section)
                self.assertIn('Final week: ' + final, section)
        self.assertIn(
            "document.querySelectorAll('#m1-home-evidence a[data-m1-detail], #m1-subject-quicklinks a[data-m1-detail]')", app
        )
        self.assertIn("manifest.html_sha256 !== evidence.dataset.htmlSha256", app)
        self.assertIn(".m1-subject-quicklinks>summary:focus-visible", css)
        self.assertIn(".m1-subject-links{grid-template-columns:minmax(0,1fr)}", css)


if __name__ == "__main__":
    unittest.main()
