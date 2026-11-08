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
    _weekly_bars, _daily_curve, _spotlights,
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

    def test_sample_highlights_are_no_js_source_derived_and_honest(self):
        self.export("spotlight-jump")
        page = (self.root / "spotlight-jump" / "index.html").read_text()
        self.assertIn('id="spotlight-heading">Start with a measured change', page)
        self.assertIn("within these selected titles only", page)
        self.assertIn("neither a Wikipedia-wide ranking", page)
        self.assertLess(page.index('id="spotlight-heading"'), page.index('id="overview"'))
        self.assertIn('class="spotlight" href="#detail-en-wikipedia-1234"', page)
        self.assertIn("Largest increase · EN", page)
        self.assertIn("+122.5 requests vs four-week median", page)
        self.assertIn("Last complete UTC week 2026-10-15–2026-10-21: "
                      "224 requests; preceding four-week median 101.5 requests.", page)
        self.assertIn("No negative weekly change among these selected title histories", page)
        self.assertEqual(page.count('class="spotlight" href='), 1)
        self.assertIn('.spotlight:focus-visible{outline:3px solid #ffca7f', page)
        self.assertIn('grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr))', page)

    def test_sample_highlights_choose_largest_signed_change_not_popularity(self):
        def row(edition, page_id, title, prior, last):
            return {"project": edition, "page_id": page_id, "title": title,
                    "daily": [{"views": prior if day < 28 else last}
                              for day in range(35)]}
        sample = [
            row("en.wikipedia", 1, "A & <test>", 10, 25),  # +105
            row("ru.wikipedia", 2, "Б", 25, 5),           # -140
            row("en.wikipedia", 3, "C", 10, 25),          # +105, later tie
            row("en.wikipedia", 4, "High volume", 1000, 1005),  # +35
            row("ru.wikipedia", 5, "Шахматы", 10, 5),    # -35
        ]
        increase, decrease = _spotlights(sample, "2026-11-04")
        self.assertIn('href="#detail-en-wikipedia-1"', increase)
        self.assertNotIn('href="#detail-en-wikipedia-3"', increase)
        self.assertIn("A &amp; &lt;test&gt;", increase)
        self.assertIn("+105 requests vs four-week median", increase)
        self.assertIn("Last complete UTC week 2026-10-29–2026-11-04: "
                      "175 requests; preceding four-week median 70 requests.", increase)
        self.assertIn('href="#detail-ru-wikipedia-2"', decrease)
        self.assertIn("−140 requests vs four-week median", decrease)
        self.assertIn("Last complete UTC week 2026-10-29–2026-11-04: "
                      "35 requests; preceding four-week median 175 requests.", decrease)
        self.assertNotIn("High volume", increase + decrease)
        self.assertEqual((increase + decrease).count("Inspect 35 exact UTC days"), 2)
        year_boundary, _ = _spotlights(sample, "2026-01-02")
        self.assertIn("Last complete UTC week 2025-12-27–2026-01-02", year_boundary)

    def test_sample_highlights_without_both_signs_never_invent_changes(self):
        no_change = [{"project": "ru.wikipedia", "page_id": 6,
                      "title": "No change", "daily": [{"views": 0}] * 35}]
        increase, decrease = _spotlights(no_change, "2026-11-04")
        self.assertNotIn("href=", increase + decrease)
        self.assertIn("No positive weekly change", increase)
        self.assertIn("No negative weekly change", decrease)
        only_negative = [{"project": "ru.wikipedia", "page_id": 7,
                          "title": "fall", "daily": [{"views": 10}] * 28 +
                          [{"views": 9}] * 7}]
        inc2, dec2 = _spotlights(only_negative, "2026-11-04")
        self.assertIn("No positive weekly change", inc2)
        self.assertIn('href="#detail-ru-wikipedia-7"', dec2)
        self.assertIn("63 requests; preceding four-week median 70 requests.", dec2)

    def test_cards_offer_accessible_progressive_pair_shortcut(self):
        self.export("card-shortcut")
        page = (self.root / "card-shortcut" / "index.html").read_text(encoding="utf-8")
        # Native links remain useful without JavaScript; JS only selects the
        # exact already-recorded series, never guesses an equivalent topic.
        self.assertEqual(page.count('href="#pair-compare" class="card-pair"'), 2)
        self.assertIn('aria-label="Use EN Chess &amp; &lt;svg', page)
        self.assertIn('aria-label="Use RU Шахматы as first comparison title"', page)
        self.assertIn('">Compare this title ↗</a>', page)
        self.assertIn('.card-pair{display:inline-flex;align-items:center;min-height:44px', page)
        self.assertIn('.card-pair:focus-visible{outline:3px solid #ffca7f', page)
        self.assertIn('action.closest(".card")', page)
        self.assertIn('if (!bySeries.has(id)) return;', page)
        self.assertIn('pairLeft.value = id;', page)
        self.assertIn('if (pairRight.value === id) pairRight.value = "";', page)
        self.assertIn('action.addEventListener("click", event => {', page)
        self.assertIn('event.preventDefault();', page)
        self.assertIn('history.pushState(null, "", "#pair-compare");', page)
        self.assertIn('pairRight.focus();', page)
        self.assertIn('renderPair();', page)
        self.assertNotIn("<svg onload='bad()'>", page)

    def test_selected_pair_csv_uses_existing_exact_rows_without_discovery_filters(self):
        self.export("pair-csv")
        page = (self.root / "pair-csv" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="pair-csv" hidden>Download selected pair CSV</button>', page)
        self.assertIn('id="pair-csv-status" role="status" aria-live="polite"', page)
        self.assertIn('const csvSupported = typeof Blob === "function"', page)
        self.assertIn('pairCsvButton.hidden = !valid || !csvSupported;', page)
        self.assertIn('function downloadCsv(selected, filenamePrefix)', page)
        self.assertIn('downloadCsv(rows, "dayflare-pair-");', page)
        self.assertIn('rows[0].dataset.series !== pairLeft.value', page)
        self.assertIn('rows[1].dataset.series !== pairRight.value', page)
        self.assertIn('pairRows.querySelectorAll("tr")', page)
        self.assertIn('Pair CSV unavailable: an exact comparison value was invalid', page)
        self.assertIn('#compare-csv:focus-visible,#compare-daily-csv:focus-visible,#pair-csv:focus-visible,#pair-daily-csv:focus-visible,.detail-daily-csv:focus-visible{outline:3px solid #ffca7f', page)
        self.assertIn('#compare-csv[hidden],#compare-daily-csv[hidden],#pair-csv[hidden],#pair-daily-csv[hidden],.detail-daily-csv[hidden]{display:none!important}', page)
        self.assertIn('id="pair-daily-csv" hidden>Download selected pair daily CSV</button>', page)
        self.assertIn('id="pair-daily-csv-status" role="status" aria-live="polite"', page)
        self.assertIn('function downloadDailyCsv(ids, filenamePrefix)', page)
        self.assertIn('sourceRows.length !== 35', page)
        self.assertIn('cells[0].textContent.trim() !== expectedDay', page)
        self.assertIn('if (lines.length !== 1 + ids.length * 35)', page)
        self.assertIn('downloadDailyCsv([pairLeft.value, pairRight.value], "dayflare-pair-daily-");', page)
        self.assertIn('.detail-daily-csv:focus-visible{outline:3px solid #ffca7f', page)

    def test_visible_daily_csv_reuses_exact_bounded_utc_histories(self):
        self.export("visible-daily")
        page = (self.root / "visible-daily" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="compare-daily-csv" hidden>Download visible daily CSV</button>', page)
        self.assertIn('id="compare-daily-csv-status" role="status" aria-live="polite"', page)
        self.assertIn('visibleDailyButton.disabled = shown === 0;', page)
        self.assertIn('visibleDailyButton.hidden = false;', page)
        self.assertIn('ids.length > cards.length', page)
        self.assertIn('new Set(ids).size !== ids.length', page)
        self.assertIn('downloadDailyCsv(ids, "dayflare-visible-daily-");', page)
        self.assertIn('const visibleCards = Array.from(cardsContainer.querySelectorAll(".card"))', page)
        self.assertIn('ids.some((id, index) => id !== visibleCards[index].dataset.series)', page)
        self.assertIn('visible series mismatch', page)
        self.assertIn('cells[0].textContent.trim() !== expectedDay', page)
        self.assertIn('countText(cells[1].textContent)', page)
        self.assertIn('Daily CSV unavailable: incomplete, misaligned or invalid exact daily evidence.', page)
        self.assertIn('compare-daily-csv:disabled{opacity:.5;', page)
        self.assertIn('compare-daily-csv[hidden],#pair-csv[hidden]', page)

    def test_two_title_comparison_uses_exact_existing_rows_and_strict_links(self):
        html = (self.root / "pair-preview" / "index.html")
        self.export("pair-preview")
        page = html.read_text(encoding="utf-8")
        # The second table reuses the exact-source weekly rows and dates,
        # rather than recomputing a metric from rounded screen text.
        self.assertIn('id="pair-compare" aria-labelledby="pair-heading"', page)
        self.assertIn('id="pair-form" aria-label="Choose two histories to compare" hidden', page)
        self.assertIn('id="pair-output" tabindex="0" hidden', page)
        self.assertIn('<table id="pair-table">', page)
        self.assertIn('id="pair-status" role="status" aria-live="polite"', page)
        self.assertIn('id="pair-share" href="#pair-compare" hidden', page)
        self.assertIn('rowBySeries.get(id).cloneNode(true)', page)
        self.assertIn('row.hidden = false', page)
        self.assertIn('const shareUrl = new URL(link.href)', page)
        self.assertIn('shareUrl.searchParams.set("af_left", leftId)', page)
        self.assertIn('shareUrl.searchParams.set("af_right", rightId)', page)
        self.assertIn('params.getAll("af_left").length > 1', page)
        self.assertIn('params.getAll("af_right").length > 1', page)
        self.assertIn('leftId === rightId', page)
        self.assertIn('!bySeries.has(leftId) || !bySeries.has(rightId)', page)
        self.assertIn('This does not establish cross-edition entity equivalence', page)
        self.assertIn('Without JavaScript, compare every selected title', page)
        self.assertIn('#pair-form select{width:100%;min-width:0;max-width:100%', page)
        self.assertIn('#pair-form button{min-height:44px;', page)
        self.assertIn('scroll sideways or focus it and use arrow keys', page)
        self.assertEqual(page.count('<option value="detail-en-wikipedia-1234">'), 2)
        self.assertEqual(page.count('<option value="detail-ru-wikipedia-5678">'), 2)
        self.assertIn('Chess &amp; &lt;svg onload=&#x27;bad()&#x27;&gt;</option>', page)
        self.assertNotIn("<svg onload='bad()'>", page)
        # The source-generated full comparison and 35-day evidence must survive.
        self.assertEqual(page.count('<tr data-series="detail-en-wikipedia-1234">'), 1)
        self.assertEqual(page.count('<tr data-series="detail-ru-wikipedia-5678">'), 1)
        self.assertEqual(page.count('<caption>Daily all-access/user requests'), 2)

    def test_full_local_visitor_journey_and_exact_values(self):
        manifest = self.export("preview")
        self.assertEqual(manifest["publication_status"], "LOCAL_PREVIEW_NOT_PUBLISHED")
        self.assertEqual(manifest["series"], 2)
        self.assertEqual(manifest["provenance_status"], "synthetic_injected_not_upstream_evidence")
        html = (self.root / "preview" / "index.html").read_text()
        self.assertEqual(sha256(html.encode()).hexdigest(), manifest["html_sha256"])
        self.assertIn('SYNTHETIC TEST DATA — NOT WIKIPEDIA EVIDENCE', html)
        self.assertIn('2026-09-17 – 2026-10-21 UTC', html)
        # Discoverable on the first narrow screen; the anchor remains usable
        # without JavaScript and always resolves to the real overview.
        self.assertIn('<a class="hero-action" href="#overview">Explore 2 measured histories ↓</a>', html)
        self.assertEqual(html.count('class="hero-action"'), 1)
        self.assertLess(html.index('class="hero-action"'), html.index('class="warning"'))
        self.assertIn('id="overview"', html)
        self.assertIn('justify-content:center;min-height:44px;', html)
        self.assertIn('.hero-action:focus-visible{outline:3px solid #ffca7f;', html)
        self.assertIn('<time datetime="2026-10-21">2026-10-21 UTC</time>', html)
        self.assertIn('id="atlas-observation-age" data-observed-end="2026-10-21"', html)
        self.assertIn('Historical archive; age cannot be calculated without JavaScript. Not live.', html)
        self.assertIn('Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())', html)
        self.assertIn('Number.isSafeInteger(days) || days < 0', html)
        self.assertIn('according to your device clock', html)
        self.assertIn('<details id="atlas-method" class="method-explainer">', html)
        self.assertIn('<summary>How the weekly change is measured</summary>', html)
        self.assertIn('Browse selected English and Russian titles, or filter by', html)
        self.assertIn('</details><form id="atlas-filters"', html)
        self.assertLess(html.index('id="atlas-method"'), html.index('id="atlas-filters"'))
        self.assertIn('A larger share is not proof of a cause.', html)
        self.assertIn('rising, returning or fading classification.', html)
        self.assertIn('id="atlas-filters" aria-label="Filter selected titles" hidden', html)
        self.assertIn('id="atlas-query" type="search"', html)
        self.assertIn('id="atlas-order"', html)
        self.assertIn('<label for="atlas-order">Sort by weekly change', html)
        # Sample-bounded spotlights now precede the filterable overview.
        # This synthetic fixture has a positive change, but no negative one.
        self.assertLess(html.index('id="spotlight-heading"'), html.index('id="overview"'))
        self.assertIn('Largest increase · EN', html)
        self.assertIn('class="spotlight" href="#detail-en-wikipedia-1234"', html)
        self.assertIn('No negative weekly change among these selected title histories', html)
        self.assertEqual(html.count('class="spotlight" href='), 1)
        self.assertIn('id="atlas-change"', html)
        self.assertIn('Exact weekly change', html)
        self.assertIn('#atlas-filters label{display:grid;gap:.25rem;font-weight:650;min-width:0}', html)
        self.assertIn('#atlas-filters select{width:100%;min-width:0}', html)
        self.assertIn('<option value="editorial">Original</option>', html)
        self.assertIn('<option value="increase">Increase</option>', html)
        self.assertIn('<option value="decrease">Decrease</option>', html)
        self.assertIn('<option value="relative-increase">Relative rise (%)</option>', html)
        self.assertIn('<option value="relative-decrease">Relative fall (%)</option>', html)
        self.assertIn('<option value="all">All changes</option>', html)
        self.assertIn('<option value="positive">Increase</option>', html)
        self.assertIn('<option value="negative">Decrease</option>', html)
        self.assertIn('<option value="unchanged">No change</option>', html)
        self.assertIn('Order by exact last-week change in requests', html)
        self.assertIn('data-delta2="245" data-baseline2="203"', html)  # +122.5 / 101.5
        self.assertIn('data-delta2="0" data-baseline2="0"', html)
        self.assertIn('Zero baselines are unavailable', html)
        self.assertIn('tiny baselines can magnify', html)
        self.assertIn('left * rightBase - right * leftBase', html)
        self.assertIn('leftBase === 0n ? 1 : -1', html)
        self.assertIn('relative-increase", "relative-decrease"', html)
        self.assertIn('BigInt(a.dataset.delta2)', html)
        self.assertIn('const signedDelta = BigInt(card.dataset.delta2)', html)
        self.assertIn('(change.value === "negative" && signedDelta < 0n)', html)
        self.assertIn('(change.value === "unchanged" && signedDelta === 0n)', html)
        self.assertIn('not</strong> a validated', html)
        self.assertIn('compareBody.appendChild(rowBySeries.get(card.dataset.series))', html)
        self.assertIn('params.getAll("af_sort").length > 1', html)
        self.assertIn('params.getAll("af_change").length > 1', html)
        self.assertIn('url.searchParams.set("af_sort", order.value)', html)
        self.assertIn('url.searchParams.set("af_change", change.value)', html)
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
        self.assertIn('    signMatches;', html)
        self.assertIn('href="#detail-en-wikipedia-1234"', html)
        self.assertIn('id="detail-ru-wikipedia-5678"', html)
        self.assertIn('>Шахматы</h3>', html)
        self.assertNotIn("<svg onload=", html)
        self.assertIn('&lt;svg onload=&#x27;bad()&#x27;&gt;', html)
        self.assertIn('>224</td>', html)  # 29+30+31+32+33+34+35 = 224
        self.assertIn('>0</td>', html)  # explicit observed zeros, not inferred
        self.assertIn('35 exact daily', html)
        self.assertEqual(html.count('class="detail-daily-csv" data-series='), 2)
        self.assertIn('hidden>Download this title’s 35-day CSV</button>', html)
        self.assertIn('class="detail-daily-csv-status" role="status" aria-live="polite"', html)
        self.assertIn('new Set(ids).size !== ids.length', html)
        self.assertIn('1 + ids.length * 35', html)
        self.assertIn('downloadDailyCsv([id], "dayflare-title-daily-")', html)
        self.assertIn('downloadDailyCsv([pairLeft.value, pairRight.value], "dayflare-pair-daily-")', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn('prefers-reduced-motion', html)
        self.assertIn('aria-label="Scrollable weekly comparison table"', html)
        self.assertIn('<script>', html)
        self.assertNotIn('<script src=', html)
        self.assertEqual(set(p.name for p in (self.root / "preview").iterdir()),
                         {"index.html", "preview-manifest.json"})

    def test_daily_curve_is_zero_origin_and_redundant_with_exact_daily_table(self):
        self.export("daily-chart")
        html = (self.root / "daily-chart" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('class="daily-curve"'), 2)
        self.assertEqual(html.count('class="daily-line"'), 2)
        self.assertIn('aria-label="Daily requests, 2026-09-17 to 2026-10-21 UTC; peak 35 requests;', html)
        self.assertIn('aria-label="Daily requests, 2026-09-17 to 2026-10-21 UTC; peak 0 requests;', html)
        self.assertIn('points="12,88 22,86', html)
        self.assertIn('352,16"/>', html)
        self.assertIn('points="12,90 22,90', html)
        self.assertIn('Zero-origin; exact values below.', html)
        self.assertIn('35 daily requests · 2026-09-17 → 2026-10-21 UTC · peak 35', html)
        self.assertIn('.daily-curve svg{display:block;width:100%;height:auto;max-height:9rem}', html)
        self.assertEqual(html.count('<table><caption>Daily all-access/user requests'), 2)
        daily = [{"date": (START + timedelta(days=i)).isoformat(), "views": 0}
                 for i in range(35)]
        with self.assertRaises(ValueError):
            _daily_curve(daily[:-1])
        with self.assertRaises(ValueError):
            _daily_curve(daily[:-1] + [{**daily[-1], "views": -1}])
        with self.assertRaises(ValueError):
            _daily_curve(daily[:-1] + [{**daily[-1], "views": 2.5}])

    def test_daily_curve_requires_canonical_consecutive_utc_days(self):
        # A missing or moved day must not be drawn as an ordinary 10px step.
        start = date(2024, 2, 14)
        daily = [{"date": (start + timedelta(days=i)).isoformat(), "views": i}
                 for i in range(35)]
        self.assertEqual(daily[15]["date"], "2024-02-29")  # included leap day
        self.assertIn("2024-02-14 to 2024-03-19 UTC", _daily_curve(daily))
        end_of_year = date(2026, 12, 20)
        rollover = [{"date": (end_of_year + timedelta(days=i)).isoformat(), "views": 0}
                    for i in range(35)]
        self.assertIn("2027-01-23", _daily_curve(rollover))

        duplicated = [dict(point) for point in daily]
        duplicated[17]["date"] = duplicated[16]["date"]
        missing = [{"date": (start + timedelta(days=i + (i >= 17))).isoformat(),
                    "views": i} for i in range(35)]
        reversed_days = [dict(point) for point in daily]
        reversed_days[17], reversed_days[18] = reversed_days[18], reversed_days[17]
        malformed = [dict(point) for point in daily]
        malformed[17]["date"] = "2024-02-30"
        compact = [dict(point) for point in daily]
        compact[17]["date"] = compact[17]["date"].replace("-", "")
        for label, rows in (("duplicate", duplicated), ("missing", missing),
                            ("out of order", reversed_days), ("invalid date", malformed),
                            ("noncanonical ISO", compact)):
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "35 consecutive canonical UTC dates"):
                    _daily_curve(rows)

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
