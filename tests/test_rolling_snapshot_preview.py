"""Synthetic-only offline preview coverage; never evidence of live Wikimedia retrieval."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import re
import shutil
import tempfile
import unittest
from html import unescape
from urllib.parse import parse_qs, urlsplit

from tools.rolling_pageview_source import (
    FetchResult, SourceError, canonical, collect_to_new_directory, sha,
    stage_verified_bundle,
)
from tools.rolling_snapshot_preview import (
    export_staged_current_preview, export_verified_preview, main, render_html, _lift,
    _weekly_bars, _daily_curve, _spotlights, _subject_examples, _article_href,
    _page_id_href, _subject_change_coverage, _detail_weekly_totals, _daily_rise,
    _latest_week_step,
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

    def test_print_view_preserves_source_dated_evidence_without_javascript(self):
        self.export("printable-evidence")
        html = (self.root / "printable-evidence" / "index.html").read_text(
            encoding="utf-8")
        self.assertIn('<p class="print-note">For a paper or PDF evidence copy, '
                      'use browser Print / Save as PDF.', html)
        self.assertIn('Modern browsers include collapsed history and source evidence '
                      'automatically', html)
        self.assertIn('in older browsers, expand the desired sections first.', html)
        self.assertEqual(html.count('details::details-content{content-visibility:visible!important}'), 1)
        self.assertGreater(html.index('details::details-content{content-visibility:visible!important}'),
                           html.index('@media print{@page{size:auto;margin:14mm}'))
        self.assertIn('@media print{@page{size:auto;margin:14mm}', html)
        self.assertIn('color-scheme:light!important;background:#fff!important;'
                      'color:#101820!important', html)
        self.assertIn('caption{background:#fff!important;color:#101820!important', html)
        self.assertIn('.scroll{overflow:visible!important;width:100%!important;', html)
        self.assertIn('table{table-layout:fixed!important;width:100%!important;'
                      'min-width:0!important;', html)
        self.assertIn('th,td{position:static!important;white-space:normal!important;'
                      'overflow-wrap:anywhere!important;', html)
        self.assertIn('button,.subject-scroll-note,.share-restore,#pair-form'
                      '{display:none!important}', html)
        self.assertIn('<span><strong>Retrieved:</strong>', html)
        self.assertIn('id="day-detail-en-wikipedia-1234-2026-09-17"', html)
        self.assertIn('id="overview"', html)
        self.assertIn('class="daily-curve"', html)

    def test_print_restores_all_filtered_titles_and_exact_weekly_rows(self):
        # Generated HTML: the print-only rules override discovery's [hidden]
        # selectors, without changing screen filters or source-backed values.
        self.export("complete-print-cohort")
        html = (self.root / "complete-print-cohort" / "index.html").read_text(
            encoding="utf-8")
        self.assertIn(".print-cohort-note{display:none}", html)
        self.assertIn(
            "Complete selected atlas: all 2 selected title histories and exact "
            "weekly comparisons are included in this printout, regardless of "
            "on-screen discovery filters.", html)
        self.assertIn(".cards>.card[hidden]{display:block!important}", html)
        self.assertIn(
            "#compare-table tbody tr[hidden]{display:table-row!important}", html)
        self.assertIn(
            "#atlas-results,#compare-results,#atlas-empty,#compare-empty,"
            "#atlas-filter-warning{display:none!important}", html)
        self.assertIn(
            ".print-cohort-note{display:block!important;font-weight:750", html)
        self.assertGreater(
            html.index(".cards>.card[hidden]{display:block!important}"),
            html.index("@media print{@page{size:auto;margin:14mm}"))
        # The original screen-only hidden rules must remain unchanged.
        self.assertIn(".cards>.card[hidden],#compare-table tbody tr[hidden]"
                      "{display:none!important}", html)

    def test_discovery_cards_wrap_unbroken_ru_titles_like_detail_headings(self):
        # Synthetic fixture: actual 30-title source is separately checked in
        # Chromium by tests/m1/browser_30_source_artifact.py on master.
        self.export("discovery-heading-wrap")
        html = (self.root / "discovery-heading-wrap" / "index.html").read_text(
            encoding="utf-8")
        self.assertIn(
            '.card h3{font-size:1.2rem;line-height:1.35;margin:.3rem 0;overflow-wrap:anywhere}',
            html)
        self.assertIn(
            'article h3{font-size:1.5rem;margin:.2rem 0;overflow-wrap:anywhere}',
            html)
        self.assertIn('class="card"', html)

    def test_daily_rise_is_exact_bounded_and_never_imputes_missing_days(self):
        days = [{"date": (START + timedelta(days=i)).isoformat(), "views": 20}
                for i in range(35)]
        self.assertEqual(_daily_rise(days), (0, None))
        days[2]["views"] = 40   # first positive step: +20 on day 2
        days[9]["views"] = 40   # tied later +20, keep earliest
        self.assertEqual(_daily_rise(days), (20, days[2]["date"]))
        days[30]["views"] = 9007199254740991
        self.assertEqual(_daily_rise(days), (9007199254740971, days[30]["date"]))
        descending = [{"date": (START + timedelta(days=i)).isoformat(),
                       "views": 40 - i} for i in range(35)]
        self.assertEqual(_daily_rise(descending), (0, None))
        for corrupted in [
            days[:-1],
            [*days[:-1], {**days[-1], "views": True}],
            [*days[:-1], {**days[-1], "views": -1}],
            [*days[:-1], {**days[-1], "views": 2**53}],
            [*days[:-1], {**days[-1], "date": days[-2]["date"]}],
            [*days[:-1], {**days[-1], "date": "2026-10-9"}],
        ]:
            with self.subTest(corrupted=corrupted[-1]), self.assertRaises(ValueError):
                _daily_rise(corrupted)

    def test_generated_daily_rise_is_visible_and_targets_exact_source_day(self):
        self.export("daily-rise-evidence")
        html = (self.root / "daily-rise-evidence" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<option value="daily-rise">Largest daily rise</option>', html)
        self.assertIn('data-last-week="224" data-daily-rise="1"', html)
        self.assertIn('data-last-week="0" data-daily-rise="0"', html)
        self.assertIn('Largest daily rise in 34 adjacent UTC-day comparisons: +1 requests on '
                      '<time datetime="2026-09-18">2026-09-18</time> UTC', html)
        self.assertIn('href="#day-detail-en-wikipedia-1234-2026-09-18">Inspect exact day ↓</a>', html)
        self.assertIn('<tr id="day-detail-en-wikipedia-1234-2026-09-18"><th scope="row">2026-09-18</th><td>2</td>', html)
        self.assertIn('No positive one-day increase in 34 adjacent UTC-day comparisons', html)
        self.assertEqual(html.count('class="daily-rise"'), 2)
        self.assertIn('.daily-rise a{display:inline-flex;align-items:center;min-height:44px;', html)
        self.assertIn('.daily-rise a:focus-visible{outline:3px solid', html)
        self.assertIn('BigInt(a.dataset.dailyRise)', html)
        self.assertIn('return leftRise > rightRise ? -1 : 1', html)
        self.assertIn('Zero means no positive step, not a missing day', html)

    def test_latest_week_step_is_exact_and_not_the_median_delta(self):
        self.assertEqual(_latest_week_step([28, 77, 126, 175, 224]), 49)
        self.assertEqual(_latest_week_step([25, 7, 7, 17, 0]), -17)
        self.assertEqual(_latest_week_step([0, 0, 0, 0, 0]), 0)
        self.assertEqual(_latest_week_step([0, 0, 0, 2**65, 2**65 + 1]), 1)
        for bad in [
            [0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, -1],
            [0, 0, 0, 0, True],
            [0, 0, 0, 0, 1.5],
        ]:
            with self.subTest(weeks=bad), self.assertRaisesRegex(ValueError, "five nonnegative"):
                _latest_week_step(bad)

    def test_cards_show_prior_week_step_separately_without_javascript(self):
        self.export("latest-week-step")
        html = (self.root / "latest-week-step" / "index.html").read_text(
            encoding="utf-8")
        self.assertEqual(html.count('class="latest-week-step"'), 2)
        self.assertIn(
            '<p class="latest-week-step"><strong>Latest vs prior full UTC week:</strong> '
            '+49 requests <small>(separate from the four-week median)</small></p>',
            html)
        self.assertIn(
            '<p class="latest-week-step"><strong>Latest vs prior full UTC week:</strong> '
            '0 requests <small>(separate from the four-week median)</small></p>',
            html)
        self.assertIn('The card’s separate latest-week step subtracts', html)
        self.assertIn('median delta and does not establish a trend or cause', html)
        self.assertIn('vs baseline', html)
        self.assertIn('class="week-bars" role="img"', html)
        self.assertIn('class="detail-weeks"', html)

    def test_week_step_direction_filter_is_independent_dataset_bound_and_no_js_safe(self):
        self.export("step-direction")
        html = (self.root / "step-direction" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="atlas-step-direction"', html)
        self.assertIn('Latest vs prior UTC week', html)
        self.assertIn('Exact weekly change (vs four-week median)', html)
        self.assertIn('<option value="positive">Gain</option>', html)
        self.assertIn('<option value="negative">Drop</option>', html)
        self.assertIn('data-week-step="49"', html)
        self.assertIn('data-week-step="0"', html)
        self.assertIn('const weekStep = BigInt(card.dataset.weekStep);', html)
        self.assertIn('signMatches && stepMatches;', html)
        self.assertIn('params.getAll("af_step").length > 1', html)
        self.assertIn('(stepMode !== null && !changeModes.has(stepMode))', html)
        self.assertIn('stepDirection.value = stepMode === null ? "all" : stepMode;', html)
        self.assertIn('url.searchParams.set("af_step", stepDirection.value)', html)
        self.assertIn('stepDirection.value = "all";', html)
        self.assertIn('The separate week-to-week direction filter uses the sign', html)
        self.assertIn('class="print-cohort-note"', html)
        # No-JavaScript readers retain both full evidence sections.
        self.assertIn('id="detail-en-wikipedia-1234"', html)
        self.assertIn('id="detail-ru-wikipedia-5678"', html)

    def test_week_to_week_order_is_distinct_from_median_change_and_source_bound(self):
        self.export("step-order")
        html = (self.root / "step-order" / "index.html").read_text(encoding="utf-8")
        # Python renders from the existing five complete weeks; no new metric source.
        self.assertIn('data-daily-rise="1" data-week-step="49"', html)
        self.assertIn('data-daily-rise="0" data-week-step="0"', html)
        self.assertIn('<option value="step-rise">Week-to-week gain</option>', html)
        self.assertIn('<option value="step-fall">Week-to-week drop</option>', html)
        self.assertIn('BigInt(a.dataset.weekStep)', html)
        self.assertIn('BigInt(b.dataset.weekStep)', html)
        self.assertIn('if (leftStep === rightStep) return fallback;', html)
        self.assertIn('(order.value === "step-rise")) ? -1 : 1', html)
        self.assertIn('!/^-?\\d+$/.test(card.dataset.weekStep || "")', html)
        self.assertIn('"step-rise", "step-fall", "relative-increase"', html)
        self.assertIn('url.searchParams.set("af_sort", order.value)', html)
        self.assertIn('Week-to-week gain/drop orders by the signed exact difference', html)
        self.assertIn('not percentages or changes against the median', html)

    def test_detail_five_week_totals_are_exact_dated_and_bounded(self):
        disclosure = _detail_weekly_totals([0, 7, 14, 21, 35], "2027-01-07")
        self.assertIn('<details class="detail-weeks"><summary>Five exact weekly totals (UTC)</summary>', disclosure)
        self.assertEqual(disclosure.count("<li>"), 5)
        for start, finish, count in [
            ("2026-12-04", "2026-12-10", 0),
            ("2026-12-11", "2026-12-17", 7),
            ("2026-12-18", "2026-12-24", 14),
            ("2026-12-25", "2026-12-31", 21),
            ("2027-01-01", "2027-01-07", 35),
        ]:
            self.assertIn(
                '<li><time datetime="' + start + '">' + start +
                '</time> – <time datetime="' + finish + '">' + finish +
                '</time> UTC: <strong>' + str(count) + ' requests</strong>',
                disclosure,
            )
        self.assertEqual(disclosure.count('class="week-step"'), 5)
        self.assertIn('Δ unavailable (no preceding week in this snapshot)', disclosure)
        self.assertEqual(disclosure.count('Δ vs previous UTC week: +7 requests'), 3)
        self.assertIn('Δ vs previous UTC week: +14 requests', disclosure)
        self.assertIn('first week has no preceding observed week (unavailable, not zero)', disclosure)
        self.assertIn("the preceding four weekly totals, not their sum", disclosure)
        self.assertIn("not unique people", disclosure)
        for totals, end in [
            ([0, 1, 2, 3], "2027-01-07"),
            ([0, 1, 2, 3, 4, 5], "2027-01-07"),
            ([0, -1, 2, 3, 4], "2027-01-07"),
            ([True, 1, 2, 3, 4], "2027-01-07"),
            ([0, 1.0, 2, 3, 4], "2027-01-07"),
            ([0, 1, 2, 3, 4], "2027-01-7"),
            ([0, 1, 2, 3, 4], "2027-02-30"),
            ([0, 1, 2, 3, 4], "0001-01-10"),
            ([0, 1, 2, 3, 4], None),
        ]:
            with self.subTest(totals=totals, end=end), self.assertRaises(ValueError):
                _detail_weekly_totals(totals, end)

    def test_detail_week_on_week_changes_are_signed_exact_and_zero_safe(self):
        changed = _detail_weekly_totals([25, 7, 7, 0, 17], "2027-01-07")
        self.assertEqual(changed.count('class="week-step"'), 5)
        for value in ["Δ vs previous UTC week: −18 requests",
                      "Δ vs previous UTC week: 0 requests",
                      "Δ vs previous UTC week: −7 requests",
                      "Δ vs previous UTC week: +17 requests"]:
            self.assertIn(value, changed)
        huge = _detail_weekly_totals([9007199254740993,
                                      9007199254740994,
                                      9007199254740994, 0, 1], "2027-01-07")
        self.assertIn("Δ vs previous UTC week: +1 requests", huge)
        self.assertIn("Δ vs previous UTC week: −9,007,199,254,740,994 requests", huge)
        self.assertIn("Δ vs previous UTC week: 0 requests", huge)

    def test_generated_details_show_all_five_week_totals_for_both_editions(self):
        self.export("topic-weekly-evidence")
        page = (self.root / "topic-weekly-evidence" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(page.count('<details class="detail-weeks">'), 2)
        self.assertIn('.detail-weeks summary:focus-visible{outline:3px solid', page)
        self.assertIn('Five exact weekly totals (UTC)', page)
        for series, expected in [
            ("detail-en-wikipedia-1234", [28, 77, 126, 175, 224]),
            ("detail-ru-wikipedia-5678", [0, 0, 0, 0, 0]),
        ]:
            article = re.search(r'<article id="' + series + r'".*?</article>', page, re.S)
            self.assertIsNotNone(article, series)
            html = article.group()
            self.assertEqual(html.count('<details class="detail-weeks">'), 1)
            self.assertEqual(html.count("<li><time datetime="), 5)
            for week, total in enumerate(expected):
                start = (START + timedelta(days=week * 7)).isoformat()
                finish = (START + timedelta(days=week * 7 + 6)).isoformat()
                self.assertIn(
                    '<time datetime="' + start + '">' + start + '</time> – '
                    '<time datetime="' + finish + '">' + finish +
                    '</time> UTC: <strong>' + str(total) + ' requests</strong>',
                    html,
                )
            steps = re.findall(r'<span class="week-step">([^<]+)</span>', html)
            self.assertEqual(len(steps), 5)
            self.assertIn("unavailable", steps[0])
            if series.endswith("1234"):
                self.assertTrue(all(" +49 requests" in s for s in steps[1:]))
            else:
                self.assertTrue(all(" 0 requests" in s for s in steps[1:]))
            # The separate daily evidence selector still sees exactly 35 rows.
            self.assertEqual(html.count('<tr id="day-' + series + '-2026-'), 35)
        self.assertIn('function exactDailyRows(id)', page)
        self.assertIn('article.querySelectorAll(".scroll table tbody tr")', page)

    def test_selected_subject_change_coverage_is_exact_and_no_js(self):
        self.export("subject-direction-coverage")
        page = (self.root / "subject-direction-coverage" / "index.html").read_text(
            encoding="utf-8")
        self.assertIn('<table id="subject-change-coverage">', page)
        self.assertIn('Scrollable selected-subject change coverage table', page)
        self.assertIn('id="subject-coverage-scroll-tip"', page)
        self.assertIn('aria-describedby="subject-coverage-scroll-tip"', page)
        self.assertIn('swipe sideways to see EN, RU and changes', page)
        self.assertIn('Subject names remain visible.', page)
        self.assertIn('#subject-change-coverage thead th:first-child{position:sticky;left:0;', page)
        self.assertIn('#subject-change-coverage tbody th:first-child{position:sticky;left:0;', page)
        self.assertIn('#subject-change-coverage th:first-child{min-width:8.5rem;max-width:8.5rem;', page)
        self.assertIn('id="subject-coverage-heading"', page)
        self.assertIn('id="subject-signal-heading">Direction mix in selected subjects', page)
        self.assertIn('class="subject-signal-list"', page)
        self.assertIn('Each bar represents 100% of its own selected subject', page)
        self.assertIn('Exact counts are written beside every bar.', page)
        self.assertLess(page.index('id="subject-signal-heading"'),
                        page.index('<table id="subject-change-coverage">'))
        self.assertIn('Increase 1 · Decrease 0 · No change 0 / 1 selected', page)
        self.assertIn('Increase 0 · Decrease 0 · No change 1 / 1 selected', page)
        self.assertIn('Vs four-week median: Increase 1 · Decrease 0 · No change 0 / 1 selected', page)
        self.assertIn('median of the preceding four complete UTC weeks', page)
        self.assertIn('Latest full UTC week vs prior: Gain 1 · Drop 0 · No change 0 / 1 selected', page)
        self.assertIn('Latest full UTC week vs prior: Gain 0 · Drop 0 · No change 1 / 1 selected', page)
        self.assertIn('these are two distinct signed comparisons', page.lower())
        self.assertEqual(page.count('class="signal-step-counts"'), 2)
        self.assertIn('.signal-step-counts{margin-top:.18rem;', page)
        self.assertIn('<span class="signal-segment signal-up" style="flex:1"></span>', page)
        self.assertIn('<span class="signal-segment signal-even" style="flex:1"></span>', page)
        self.assertIn('class="signal-track" aria-hidden="true"', page)
        self.assertNotIn('style="flex:0"', page)
        self.assertIn('these are not validated rising/fading labels', page)
        self.assertIn('irrespective of active discovery filters', page)
        # The injected EN title increases; the injected RU title stays at zero.
        self.assertIn(
            '<tr><th scope="row"><a href="#detail-en-wikipedia-1234" data-filter-subject="sport">Sport</a></th>'
            '<td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>0</td>'
            '<td>1</td><td>0</td><td>0</td></tr>', page)
        self.assertIn(
            '<tr><th scope="row"><a href="#detail-ru-wikipedia-5678" data-filter-subject="culture">Culture</a></th>'
            '<td>1</td><td>0</td><td>1</td><td>0</td><td>0</td><td>1</td>'
            '<td>0</td><td>0</td><td>1</td></tr>', page)
        self.assertLess(page.index('>Culture</a></th>'), page.index('>Sport</a></th>'))
        self.assertEqual(page.count('id="subject-change-coverage"'), 1)
        self.assertIn("Choose a subject to filter all its selected", page)
        self.assertIn("or inspect one measured example without it.", page)
        self.assertIn("data-filter-subject=\"sport\"", page)
        self.assertIn("data-filter-subject=\"culture\"", page)
        self.assertIn('ending 2026-10-21 UTC. Not Wikipedia-wide.', page)
        self.assertIn('<th scope="col">Median increase</th>', page)
        self.assertIn('<th scope="col">Week gain</th>', page)
        self.assertIn('<th scope="col">Week drop</th>', page)
        self.assertIn('<th scope="col">Week no change</th>', page)
        self.assertIn('Columns separate four-week-median change from prior-week movement.', page)
        self.assertIn('id="subject-coverage-csv" hidden>Download selected-subject coverage CSV</button>', page)
        self.assertIn('id="subject-coverage-csv-status" role="status" aria-live="polite"', page)
        self.assertIn('#subject-coverage-csv[hidden]{display:none!important}', page)
        self.assertIn('#subject-coverage-csv:focus-visible{outline:3px solid', page)
        self.assertIn('function downloadSubjectCoverageCsv()', page)
        self.assertIn('const verified = checkedWeeklyCells(', page)
        self.assertIn('id, Array.from(source.querySelectorAll("td")), card.dataset.delta2);', page)
        self.assertIn('const step = BigInt(verified[4]) - BigInt(verified[3]);', page)
        self.assertIn('if (step !== BigInt(card.dataset.weekStep))', page)
        self.assertIn('Subject CSV unavailable: selected coverage or exact daily evidence did not reconcile.', page)

    def test_subject_coverage_csv_validates_exact_evidence_and_rejects_tampering(self):
        """CSV is dataset-bound, independent of UI filters, and fails closed."""
        import csv
        import io
        import subprocess
        from tools.rolling_snapshot_preview import _FILTER_SCRIPT

        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js unavailable; hosted Chromium checks actual downloads")
        csv_start = _FILTER_SCRIPT.index("    function csvCell(value, protectFormula) {")
        csv_end = _FILTER_SCRIPT.index("    function countText(value) {", csv_start)
        count_start = csv_end
        count_end = _FILTER_SCRIPT.index("    function deltaText(value, expected2) {", count_start)
        start = _FILTER_SCRIPT.index("    function downloadSubjectCoverageCsv() {")
        end = _FILTER_SCRIPT.index("    function downloadPairChangeCsv(ids) {", start)
        program = r"""
const snapshot = {dataset: {
    dataset: "a".repeat(64), method: "v0-empirical-35d", end: "2026-10-21"
}};
const cards = [
    {dataset: {series: "a", subject: "sport", edition: "en.wikipedia", delta2: "2", weekStep: "1"}},
    {dataset: {series: "b", subject: "sport", edition: "ru.wikipedia", delta2: "-2", weekStep: "-1"}},
    {dataset: {series: "c", subject: "=science", edition: "en.wikipedia", delta2: "0", weekStep: "0"}}
];
const rowBySeries = new Map(cards.map(card => [
    card.dataset.series,
    {querySelectorAll(selector) {
        if (selector !== "td") throw Error("unexpected weekly selector");
        return Array(6).fill({textContent: "0"});
    }}
]));
const sourceRows = [
    {name: "sport", cells: ["2", "1", "1", "1", "1", "0", "1", "1", "0"]},
    {name: "=science", cells: ["1", "1", "0", "0", "0", "1", "0", "0", "1"]}
].map(entry => ({
    entry,
    querySelector(selector) {
        return selector === "th a[data-filter-subject]" ?
            {dataset: {filterSubject: this.entry.name}} : null;
    },
    querySelectorAll(selector) {
        if (selector !== "td") throw Error("unexpected coverage selector");
        return this.entry.cells.map(value => ({textContent: value}));
    }
}));
const document = {getElementById(id) {
    return id === "subject-change-coverage" ?
        {querySelectorAll(selector) {
            if (selector !== "tbody tr") throw Error("unexpected table selector");
            return sourceRows;
        }} : null;
}};
let rejectDaily = false;
let verified = 0;
function checkedWeeklyCells(id, cells, delta) {
    verified += 1;
    const card = cards.find(item => item.dataset.series === id);
    if (rejectDaily || !card || delta !== card.dataset.delta2 || cells.length !== 6)
        throw Error("daily/weekly evidence mismatch");
    if (id === "a") return ["0", "0", "0", "3", "4", "2"];
    if (id === "b") return ["0", "0", "0", "3", "2", "-2"];
    return ["0", "0", "0", "0", "0", "0"];
}
let latest = null;
function saveCsv(lines, filenamePrefix) { latest = {lines, filenamePrefix}; }
""" + _FILTER_SCRIPT[csv_start:csv_end] + _FILTER_SCRIPT[count_start:count_end] + _FILTER_SCRIPT[start:end] + r"""
const count = downloadSubjectCoverageCsv();
if (count !== 2 || verified !== 3 || latest.lines.length !== 3 ||
    !latest.filenamePrefix.startsWith("dayflare-subject-coverage-"))
    throw Error("complete exact coverage CSV was not exported");
const accepted = latest;
rejectDaily = true;
let rejected = false;
try { downloadSubjectCoverageCsv(); } catch (error) { rejected = true; }
if (!rejected || latest !== accepted)
    throw Error("bad daily evidence was exported");
rejectDaily = false;
sourceRows[0].entry.cells[3] = "2";
rejected = false;
try { downloadSubjectCoverageCsv(); } catch (error) { rejected = true; }
if (!rejected || latest !== accepted)
    throw Error("altered static sign count was exported");
sourceRows[0].entry.cells[3] = "1";
sourceRows[0].entry.cells[6] = "2";
rejected = false;
try { downloadSubjectCoverageCsv(); } catch (error) { rejected = true; }
if (!rejected || latest !== accepted)
    throw Error("altered recent-week sign count was exported");
sourceRows[0].entry.cells[6] = "1";
cards[0].dataset.weekStep = "99";
rejected = false;
try { downloadSubjectCoverageCsv(); } catch (error) { rejected = true; }
if (!rejected || latest !== accepted)
    throw Error("altered card week-step metadata was exported");
cards[0].dataset.weekStep = "1";
sourceRows.pop();
rejected = false;
try { downloadSubjectCoverageCsv(); } catch (error) { rejected = true; }
if (!rejected || latest !== accepted)
    throw Error("missing subject was exported");
console.log(JSON.stringify(accepted.lines));
"""
        result = subprocess.run(
            [node, "-e", program], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        records = list(csv.reader(io.StringIO("\n".join(json.loads(result.stdout)))))
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0], [
            "dataset_sha256", "method_version", "observation_end_utc", "subject",
            "selected", "en", "ru", "increase", "decrease", "no_change",
            "week_gain", "week_drop", "week_no_change"])
        self.assertEqual(records[1], [
            "a" * 64, "v0-empirical-35d", "2026-10-21", "sport",
            "2", "1", "1", "1", "1", "0", "1", "1", "0"])
        self.assertEqual(records[2], [
            "a" * 64, "v0-empirical-35d", "2026-10-21", "'=science",
            "1", "1", "0", "0", "0", "1", "0", "0", "1"])

    def test_subject_coverage_signs_and_invalid_cohorts(self):
        def series(project, page_id, early, last):
            return {"project": project, "page_id": page_id,
                    "daily": [{"date": (START + timedelta(days=i)).isoformat(),
                               "views": early if i < 28 else last}
                              for i in range(35)]}
        en_up = series("en.wikipedia", 11, 10, 20)
        ru_down = series("ru.wikipedia", 22, 20, 5)
        en_flat = series("en.wikipedia", 33, 0, 0)
        rows = [en_up, ru_down, en_flat]
        subjects = {("en.wikipedia", 11): "sport",
                    ("ru.wikipedia", 22): "sport",
                    ("en.wikipedia", 33): "science"}
        html = _subject_change_coverage(rows, subjects, "2026-10-21")
        self.assertIn(
            '<tr><th scope="row"><a href="#detail-ru-wikipedia-22" data-filter-subject="sport">Sport</a></th>'
            '<td>2</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td>'
            '<td>1</td><td>1</td><td>0</td></tr>', html)
        self.assertIn(
            '<tr><th scope="row"><a href="#detail-en-wikipedia-33" data-filter-subject="science">Science</a></th>'
            '<td>1</td><td>1</td><td>0</td><td>0</td><td>0</td><td>1</td>'
            '<td>0</td><td>0</td><td>1</td></tr>', html)
        self.assertLess(html.index('>Science</a></th>'), html.index('>Sport</a></th>'))
        # The bars use the exact same sign/edition aggregation as the table,
        # omit zero-width segments and normalize each subject separately.
        self.assertEqual(html.count('class="signal-item"'), 2)
        self.assertIn('Increase 1 · Decrease 1 · No change 0 / 2 selected', html)
        self.assertIn('Increase 0 · Decrease 0 · No change 1 / 1 selected', html)
        self.assertIn('Latest full UTC week vs prior: Gain 1 · Drop 1 · No change 0 / 2 selected', html)
        self.assertIn('Latest full UTC week vs prior: Gain 0 · Drop 0 · No change 1 / 1 selected', html)
        self.assertIn('<span class="signal-segment signal-up" style="flex:1"></span>', html)
        self.assertIn('<span class="signal-segment signal-down" style="flex:1"></span>', html)
        self.assertIn('<span class="signal-segment signal-even" style="flex:1"></span>', html)
        self.assertNotIn('style="flex:0"', html)
        self.assertLess(html.index('>Science</strong>'), html.index('>Sport</strong>'))
        escaped = _subject_change_coverage([en_flat],
                {("en.wikipedia", 33): "science & <fake>"}, "2026-10-21")
        self.assertIn('Science &amp; &lt;Fake&gt;', escaped)
        self.assertNotIn('<fake>', escaped)
        self.assertIn('No selected subject histories available.',
                      _subject_change_coverage([], {}, "2026-10-21"))
        with self.assertRaisesRegex(ValueError, "missing selected identity"):
            _subject_change_coverage(rows, {}, "2026-10-21")
        invalid = series("not.wikipedia", 11, 1, 2)
        with self.assertRaisesRegex(ValueError, "unsupported edition"):
            _subject_change_coverage([invalid],
                                      {("not.wikipedia", 11): "sport"}, "2026-10-21")

    def test_subject_week_step_is_distinct_from_baseline_even_when_signs_disagree(self):
        # Two complete 7-day windows can move opposite to the four-week median:
        # 10/10/10/50/40 -> baseline gain and recent drop;
        # 30/30/30/5/20 -> baseline drop and recent gain.
        def item(page_id, levels):
            return {"project": "en.wikipedia", "page_id": page_id,
                    "daily": [{"date": (START + timedelta(days=i)).isoformat(),
                               "views": levels[i // 7]} for i in range(35)]}

        rows = [item(11, [10, 10, 10, 50, 40]),
                item(12, [30, 30, 30, 5, 20]),
                item(13, [0, 0, 0, 0, 0])]
        subjects = {("en.wikipedia", page): "books" for page in (11, 12, 13)}
        html = _subject_change_coverage(rows, subjects, "2026-10-21")
        self.assertIn('Increase 1 · Decrease 1 · No change 1 / 3 selected', html)
        self.assertIn('Latest full UTC week vs prior: Gain 1 · Drop 1 · No change 1 / 3 selected', html)
        self.assertEqual(html.count('class="signal-step-counts"'), 1)
        # No automatic trend labels, thresholds, inferred absent days or percentage rankings.
        self.assertIn('not validated trends or a ranking of subjects', html)
        self.assertNotIn('returning</span>', html)
        self.assertIn('<span class="signal-segment signal-even" style="flex:1"></span>', html)

    def test_observed_title_links_are_safe_current_context_not_identity_evidence(self):
        self.export("article-context")
        page = (self.root / "article-context" / "index.html").read_text(encoding="utf-8")
        en = ("https://en.wikipedia.org/wiki/"
              "Chess_%26_%3Csvg_onload%3D%27bad%28%29%27%3E")
        ru = ("https://ru.wikipedia.org/wiki/"
              "%D0%A8%D0%B0%D1%85%D0%BC%D0%B0%D1%82%D1%8B")
        self.assertEqual(page.count('class="current-context"'), 2)
        for href in (en, ru):
            self.assertIn('href="' + href + '" rel="noopener noreferrer">'
                          'Open observed title on Wikipedia ↗</a>', page)
        self.assertIn("the address may redirect or no longer exist", page)
        self.assertIn("not a verified historical page-ID link", page)
        self.assertEqual(page.count('class="page-id-context"'), 2)
        for project, page_id in (("en.wikipedia", 1234), ("ru.wikipedia", 5678)):
            link = _page_id_href(project, page_id)
            self.assertIn('href="' + link + '" rel="noopener noreferrer">'
                          'Open current page by selected ID ↗</a>', page)
        self.assertIn("Selected Wikipedia page ID 1234", page)
        self.assertIn("Selected Wikipedia page ID 5678", page)
        self.assertIn("cannot verify the identity behind 35 days", page)
        self.assertIn(".page-id-context a{display:inline-block", page)
        self.assertEqual(_article_href("en.wikipedia", "A/B?# 100%"),
                         "https://en.wikipedia.org/wiki/A%2FB%3F%23_100%25")
        self.assertEqual(_article_href("ru.wikipedia", "Шахматы"), ru)
        with self.assertRaisesRegex(ValueError, "unsupported Wikipedia edition"):
            _article_href("evil.example", "Chess")
        self.assertNotIn('href="javascript:', page)
        self.assertEqual(_page_id_href("en.wikipedia", 1234),
                         "https://en.wikipedia.org/wiki/Special:Redirect/page/1234")
        self.assertEqual(_page_id_href("ru.wikipedia", 5678),
                         "https://ru.wikipedia.org/wiki/Special:Redirect/page/5678")
        with self.assertRaisesRegex(ValueError, "unsupported Wikipedia edition"):
            _page_id_href("evil.example", 1234)
        for invalid in (0, -1, True, False, 1.0, "1234", 9007199254740992):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "positive safe integer"):
                    _page_id_href("en.wikipedia", invalid)

    def test_no_js_save_preserves_exact_snapshot_without_a_hosted_link(self):
        self.export("save-snapshot")
        folder = self.root / "save-snapshot"
        page = (folder / "index.html").read_text(encoding="utf-8")
        manifest = json.loads((folder / "preview-manifest.json").read_text(encoding="utf-8"))
        digest = manifest["candidate_sha256"]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        name = "dayflare-m1-2026-10-21-" + digest[:12] + ".html"
        self.assertIn('<a class="save-snapshot" href="" download="' + name +
                      '">Save this dated HTML offline ↓</a>', page)
        self.assertEqual(page.count('class="save-snapshot"'), 1)
        self.assertIn(".save-snapshot{display:inline-flex;align-items:center;min-height:44px", page)
        self.assertIn(".save-snapshot:focus-visible{outline:3px solid #ffca7f", page)
        self.assertIn("Works without JavaScript", page)
        self.assertIn("An offline copy is not a public immutable Share URL.", page)
        # The empty URL is deliberate: unlike relative index.html or
        # archives/<hash>/index.html, it identifies the *current* HTML at
        # /m1/, at /m1/archives/<hash>/, or under an arbitrary file:// name.
        # The user saves the already-verified HTML; this creates no host claim.
        self.assertEqual(manifest["html_sha256"], sha((folder / "index.html").read_bytes()))
        self.assertNotIn("drevendev.github.io/Dayflare", page)

    def test_detail_sharing_is_no_js_and_matches_card_dataset_bound_url(self):
        self.export("detail-sharing")
        page = (self.root / "detail-sharing" / "index.html").read_text(encoding="utf-8")
        card_urls = re.findall(
            r'<p class="share-action"><a href="([^"]+)">Share this exact history</a></p>',
            page)
        detail_urls = re.findall(
            r'<p class="detail-share"><a href="([^"]+)">Share this exact history ↗</a>',
            page)
        self.assertEqual(len(card_urls), 2)
        self.assertEqual(detail_urls, card_urls)
        self.assertIn("Same dataset, method and observation end;", page)
        self.assertIn("the link will not substitute another title history.", page)
        self.assertIn(".detail-share a:focus-visible{outline:3px solid #ffca7f", page)
        self.assertIn(".detail-share a{display:inline-flex;align-items:center;min-height:44px", page)
        for href, edition, page_id in zip(detail_urls,
                                          ("en.wikipedia", "ru.wikipedia"),
                                          ("1234", "5678")):
            parts = urlsplit(unescape(href))
            self.assertEqual(parts.fragment, "share-restore")
            self.assertEqual(parts.path, "")
            values = parse_qs(parts.query)
            self.assertEqual(set(values), {"df_dataset", "df_method", "df_end",
                                           "df_edition", "df_page"})
            self.assertEqual(values["df_edition"], [edition])
            self.assertEqual(values["df_page"], [page_id])
            self.assertEqual(values["df_method"], ["v0-empirical-35d"])
            self.assertEqual(values["df_end"], ["2026-10-21"])
            self.assertRegex(values["df_dataset"][0], r"^[0-9a-f]{64}$")
        # Only mutable published M1 URLs are enhanced to verified archives.
        self.assertIn('const shareBase = mutableM1', page)
        self.assertIn('new URL("archives/" + snapshot.dataset.dataset + "/index.html"', page)
        self.assertIn('new URL(shareBase.href)', page)
        self.assertIn('relative.pathname = shareBase.pathname;', page)
        # The canonical share restoration handler stays unchanged and
        # rejects dataset/window mismatches instead of choosing another title.
        self.assertIn("This link belongs to a different dataset, method or observation window.", page)

    def test_subject_example_shortcuts_are_measured_no_js_jumps(self):
        self.export("subject-examples")
        page = (self.root / "subject-examples" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="subject-examples-heading">Choose a subject example', page)
        self.assertLess(page.index('id="subject-examples-heading"'),
                        page.index('id="overview"'))
        self.assertIn('aria-label="Measured subject examples"', page)
        self.assertIn('subject-wide rankings, filters, or validated trends.', page)
        self.assertIn('href="#detail-en-wikipedia-1234"', page)
        self.assertIn('href="#detail-ru-wikipedia-5678"', page)
        self.assertIn('Sport · 1 selected', page)
        self.assertIn('Culture · 1 selected', page)
        self.assertIn('class="subject-example"', page)
        self.assertIn('.subject-example:focus-visible{outline:3px solid #ffca7f', page)
        self.assertNotIn('subject-example" href="#detail-en-wikipedia-5678"', page)

    def test_russian_titles_expose_ru_language_without_changing_english_chrome(self):
        self.export("title-language")
        page = (self.root / "title-language" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<h3 lang="ru"><a href="#detail-ru-wikipedia-5678">Шахматы</a></h3>', page)
        self.assertIn('<h3><a href="#detail-en-wikipedia-1234">Chess &amp;', page)
        self.assertIn('<h3 id="heading-detail-ru-wikipedia-5678" lang="ru">Шахматы</h3>', page)
        self.assertIn('<a lang="ru" href="#detail-ru-wikipedia-5678">Шахматы</a> (RU)', page)
        self.assertIn('<option value="detail-ru-wikipedia-5678" lang="ru">RU · Шахматы</option>', page)
        self.assertNotIn('<option value="detail-en-wikipedia-1234" lang="ru">', page)
        self.assertIn('data-title="Шахматы"', page)
        self.assertIn('data-page-id="5678"', page)
        self.assertIn('lang="en"', page)
        # Labels and source identity remain unchanged; language is a presentation hint.
        self.assertIn('>Compare this title ↗</a>', page)
        ru = {"project": "ru.wikipedia", "page_id": 5678, "title": "Шахматы",
              "daily": [{"views": 1}] * 28 + [{"views": 3}] * 7}
        en = {"project": "en.wikipedia", "page_id": 1234, "title": "Chess",
              "daily": [{"views": 3}] * 28 + [{"views": 1}] * 7}
        inc, dec = _spotlights([ru, en], "2026-11-08")
        self.assertIn('<strong lang="ru">Шахматы</strong>', inc)
        self.assertIn('<strong>Chess</strong>', dec)
        shortcuts = _subject_examples([ru, en], {
            ("ru.wikipedia", 5678): "games",
            ("en.wikipedia", 1234): "sport"})
        self.assertIn('<strong lang="ru">Шахматы</strong>', shortcuts)
        self.assertIn('<strong>Chess</strong>', shortcuts)

    def test_subject_shortcuts_choose_largest_abs_delta_tie_first_and_escape(self):
        def row(project, page_id, title, previous, latest):
            return {"project": project, "page_id": page_id, "title": title,
                    "daily": [{"views": previous}] * 28 +
                             [{"views": latest}] * 7}
        a = row("en.wikipedia", 1, "A & <script>", 10, 20)  # +70
        b = row("ru.wikipedia", 2, "Later tie", 20, 10)  # -70, not selected
        c = row("ru.wikipedia", 3, "C", 10, 0)  # -70, one book
        d = row("en.wikipedia", 4, "Zero", 0, 0)  # missing subject
        subjects = {
            ("en.wikipedia", 1): "science",
            ("ru.wikipedia", 2): "science",
            ("ru.wikipedia", 3): "books",
            ("en.wikipedia", 4): "games",
        }
        result = _subject_examples([a, b, c, d], subjects)
        self.assertEqual(result.count('class="subject-example"'), 3)
        self.assertIn('href="#detail-en-wikipedia-1"', result)
        self.assertNotIn('href="#detail-ru-wikipedia-2"', result)
        self.assertIn("Science · 2 selected", result)
        self.assertIn("Books · 1 selected", result)
        self.assertIn("Games · 1 selected", result)
        self.assertIn("A &amp; &lt;script&gt;", result)
        self.assertNotIn("<script>", result)
        self.assertIn("EN · +70 requests vs four-week median", result)
        self.assertIn("RU · −70 requests vs four-week median", result)
        self.assertIn('href="#detail-en-wikipedia-4"', result)
        self.assertIn("EN · 0 requests vs four-week median", result)
        self.assertLess(result.index("Books ·"), result.index("Games ·"))
        self.assertLess(result.index("Games ·"), result.index("Science ·"))
        self.assertEqual(_subject_examples([], {}), "")

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

    def test_russian_yo_search_hint_and_query_provenance(self):
        self.export("russian-search")
        page = (self.root / "russian-search" / "index.html").read_text(encoding="utf-8")
        self.assertIn('Find a title (е matches ё; _ matches spaces)', page)
        self.assertIn('value.normalize("NFC").toLowerCase()', page)
        self.assertIn('replace(/ё/g, "е").replace(/_/g, " ")', page)
        self.assertIn('replace(/\\s+/g, " ").trim()', page)
        # The source title, stable series and sharing query are not rewritten.
        self.assertIn('>Шахматы</h3>', page)
        self.assertIn('data-title="Шахматы"', page)
        self.assertIn('url.searchParams.set("af_query", query.value.trim().normalize("NFC").slice(0, 120))', page)
        self.assertIn('const text = normalized(query.value.trim());', page)
        self.assertIn('normalized(card.dataset.title || "").includes(text)', page)

    def test_exact_current_page_id_discovery_never_rewrites_title_or_share(self):
        self.export("id-discovery")
        page = (self.root / "id-discovery" / "index.html").read_text(encoding="utf-8")
        self.assertIn('or current page ID (id:5134)', page)
        self.assertIn('data-page-id="1234"', page)
        self.assertIn('data-page-id="5678"', page)
        self.assertIn('const queryIsPageId = text.startsWith("id:");', page)
        self.assertIn('const canonicalPageId = /^[1-9][0-9]*$/.test(pageIdQuery);', page)
        self.assertIn('canonicalPageId && card.dataset.pageId === pageIdQuery', page)
        self.assertIn('normalized(card.dataset.title || "").includes(text)', page)
        self.assertIn('url.searchParams.set("af_query", query.value.trim().normalize("NFC").slice(0, 120))', page)
        self.assertIn('data-title="Шахматы"', page)
        self.assertIn('df_page=5678', page)
        self.assertNotIn('data-title="5678"', page)

    def test_cards_offer_accessible_progressive_pair_shortcut(self):
        self.export("card-shortcut")
        page = (self.root / "card-shortcut" / "index.html").read_text(encoding="utf-8")
        # Native links remain useful without JavaScript; JS only selects the
        # exact already-recorded series, never guesses an equivalent topic.
        # Native links jump to the exact matching weekly row without JS;
        # the interactive JS shortcut still preselects the first pair title.
        for series in ("detail-en-wikipedia-1234", "detail-ru-wikipedia-5678"):
            self.assertIn('href="#compare-' + series + '" class="card-pair"', page)
            self.assertIn('<tr id="compare-' + series + '" data-series="' +
                          series + '" tabindex="-1">', page)
            self.assertEqual(page.count('id="compare-' + series + '"'), 1)
        self.assertIn('aria-label="Compare EN Chess &amp; &lt;svg', page)
        self.assertIn('aria-label="Compare RU Шахматы: exact weekly row or interactive pair"', page)
        self.assertIn('#compare-table tbody tr:target{outline:3px solid #ffca7f', page)
        self.assertIn('row.removeAttribute("id");', page)
        self.assertIn('row.removeAttribute("tabindex");', page)
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

    def test_detail_evidence_can_compare_this_exact_title_without_javascript(self):
        self.export("detail-pair-shortcut")
        page = (self.root / "detail-pair-shortcut" / "index.html").read_text(encoding="utf-8")
        # A visitor arriving at the 35-day detail should not have to return to
        # the discovery card to select that exact title for comparison.
        self.assertEqual(page.count('class="detail-pair-action"'), 2)
        for series in ("detail-en-wikipedia-1234", "detail-ru-wikipedia-5678"):
            self.assertIn('href="#compare-' + series +
                          '" class="detail-pair">Compare this title ↗</a>', page)
            self.assertEqual(page.count('id="compare-' + series + '"'), 1)
        self.assertIn("without it, inspect this exact row in the five-week table", page)
        self.assertIn(".detail-pair{display:inline-flex;align-items:center;min-height:44px", page)
        self.assertIn(".detail-pair:focus-visible{outline:3px solid #ffca7f", page)
        self.assertIn('document.querySelectorAll(".card-pair, .detail-pair")', page)
        self.assertIn('action.closest(\'article[id^="detail-"]\')', page)
        self.assertIn('action.getAttribute("href") !== "#compare-" + id', page)
        self.assertIn("pairLeft.value = id;", page)
        self.assertIn("pairRight.focus();", page)
        self.assertNotIn("<svg onload='bad()'>", page)

    def test_selected_pair_csv_uses_existing_exact_rows_without_discovery_filters(self):
        self.export("pair-csv")
        page = (self.root / "pair-csv" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="pair-csv" hidden>Download selected pair CSV</button>', page)
        self.assertIn('id="pair-csv-status" role="status" aria-live="polite"', page)
        self.assertIn('const csvSupported = typeof Blob === "function"', page)
        self.assertIn('pairCsvButton.hidden = !evidenceValid || !csvSupported;', page)
        self.assertIn('function downloadCsv(selected, filenamePrefix)', page)
        self.assertIn('downloadCsv(rows, "dayflare-pair-");', page)
        self.assertIn('rows[0].dataset.series !== pairLeft.value', page)
        self.assertIn('rows[1].dataset.series !== pairRight.value', page)
        self.assertIn('pairRows.querySelectorAll("tr")', page)
        self.assertIn('Pair CSV unavailable: an exact comparison value was invalid', page)
        self.assertIn('#compare-csv:focus-visible,#compare-daily-csv:focus-visible,#pair-csv:focus-visible,#pair-change-csv:focus-visible,#pair-daily-csv:focus-visible,.detail-daily-csv:focus-visible{outline:3px solid #ffca7f', page)
        self.assertIn('#compare-csv[hidden],#compare-daily-csv[hidden],#pair-csv[hidden],#pair-change-csv[hidden],#pair-daily-csv[hidden],.detail-daily-csv[hidden]{display:none!important}', page)
        self.assertIn('id="pair-daily-csv" hidden>Download selected pair daily CSV</button>', page)
        self.assertIn('id="pair-daily-csv-status" role="status" aria-live="polite"', page)
        self.assertIn('function downloadDailyCsv(ids, filenamePrefix)', page)
        self.assertIn('sourceRows.length !== 35', page)
        self.assertIn('cells[0].textContent.trim() !== expectedDay', page)
        self.assertIn('if (lines.length !== 1 + ids.length * 35)', page)
        self.assertIn('downloadDailyCsv([pairLeft.value, pairRight.value], "dayflare-pair-daily-");', page)
        self.assertIn('.detail-daily-csv:focus-visible{outline:3px solid #ffca7f', page)

    def test_weekly_csv_delta_validates_grouping_and_source_value(self):
        # The deployed validator is JavaScript; exercise the exact embedded
        # function, including half-integer baselines, in a JS runtime.
        self.export("weekly-delta-validation")
        html = (self.root / "weekly-delta-validation" / "index.html").read_text(encoding="utf-8")
        self.assertIn("checkedWeeklyCells(row.dataset.series, cells, card.dataset.delta2)", html)
        self.assertIn("mismatched exact baseline delta", html)
        from tools.rolling_snapshot_preview import _FILTER_SCRIPT
        first = _FILTER_SCRIPT.index("    function deltaText(value, expected2) {")
        last = _FILTER_SCRIPT.index("    function downloadCsv(", first)
        validator = _FILTER_SCRIPT[first:last]
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js unavailable; browser acceptance must run this behavior")
        program = validator + r"""
const cases = [
    ["+1,234.5", "2469", "+1234.5"],
    ["−1,234.5", "-2469", "-1234.5"],
    ["0", "0", "0"],
    ["+0.5", "1", "+0.5"],
    ["−0.5", "-1", "-0.5"],
    ["+1,2,3.5", "247", null],
    ["+001", "2", null],
    ["1e3", "2000", null],
    ["+123", "244", null],
    ["+1,234.5", "2471", null],
    ["+1,234.6", "2469", null],
];
for (const [text, doubled, expected] of cases) {
    let actual;
    try {
        actual = deltaText(text, doubled);
    } catch (error) {
        if (expected === null) continue;
        throw error;
    }
    if (actual !== expected)
        throw new Error("CSV delta check failed for " + text);
}
"""
        import subprocess
        result = subprocess.run(
            [node, "-e", program], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_weekly_csv_reconciles_five_weeks_with_all_35_exact_daily_rows(self):
        self.export("weekly-daily-consistency")
        html = (self.root / "weekly-daily-consistency" / "index.html").read_text(encoding="utf-8")
        self.assertIn("checkedWeeklyCells(row.dataset.series, cells, card.dataset.delta2)", html)
        self.assertIn("weekly/daily evidence mismatch", html)
        self.assertIn("weekly delta does not match daily evidence", html)
        self.assertIn("for (const [expectedDay, count] of exactDailyRows(id))", html)
        # Exercise the exact generated JavaScript helpers with independent DOM
        # row objects; tampering with a week, daily value/date or median must fail.
        from tools.rolling_snapshot_preview import _FILTER_SCRIPT
        start = _FILTER_SCRIPT.index("    function countText(value) {")
        end = _FILTER_SCRIPT.index("    function downloadCsv(", start)
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js unavailable; hosted Chromium acceptance required")
        program = r"""
const snapshot = {dataset: {end: "2026-11-08"}};
const first = Date.UTC(2026, 9, 5);
const rows = Array.from({length: 35}, (_, i) => ({children: [
    {tagName: "TH", textContent: new Date(first + i * 86400000).toISOString().slice(0, 10)},
    {tagName: "TD", textContent: String(i < 28 ? 10 : 20)}
]}));
const document = {getElementById(id) {
    return id === "detail-en-wikipedia-1" ? {querySelectorAll() {return rows;}} : null;
}};
""" + _FILTER_SCRIPT[start:end] + r"""
const values = ["70", "70", "70", "70", "140", "+70"];
const cells = () => values.map(textContent => ({textContent}));
function fails(fn) {
    let failed = false;
    try {fn();} catch (error) {failed = true;}
    if (!failed) throw new Error("invalid CSV input was accepted");
}
if (checkedWeeklyCells("detail-en-wikipedia-1", cells(), "140").join("|") !==
    values.join("|")) throw new Error("valid exact evidence rejected");
fails(() => checkedWeeklyCells("unknown", cells(), "140"));
const badWeek = cells(); badWeek[2].textContent = "71";
fails(() => checkedWeeklyCells("detail-en-wikipedia-1", badWeek, "140"));
const badDelta = cells(); badDelta[5].textContent = "+71";
fails(() => checkedWeeklyCells("detail-en-wikipedia-1", badDelta, "140"));
fails(() => checkedWeeklyCells("detail-en-wikipedia-1", cells(), "142"));
fails(() => countText("01"));
const savedDate = rows[10].children[0].textContent;
rows[10].children[0].textContent = rows[9].children[0].textContent;
fails(() => checkedWeeklyCells("detail-en-wikipedia-1", cells(), "140"));
rows[10].children[0].textContent = savedDate;
const savedCount = rows[10].children[1].textContent;
rows[10].children[1].textContent = "11";
fails(() => checkedWeeklyCells("detail-en-wikipedia-1", cells(), "140"));
rows[10].children[1].textContent = savedCount;
const lastRow = rows.pop();
fails(() => checkedWeeklyCells("detail-en-wikipedia-1", cells(), "140"));
rows.push(lastRow);
"""
        import subprocess
        result = subprocess.run(
            [node, "-e", program], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

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
        self.assertEqual(page.count('<option value="detail-ru-wikipedia-5678" lang="ru">'), 2)
        self.assertIn('Chess &amp; &lt;svg onload=&#x27;bad()&#x27;&gt;</option>', page)
        self.assertNotIn("<svg onload='bad()'>", page)
        # The source-generated full comparison and 35-day evidence must survive.
        self.assertEqual(page.count('<tr id="compare-detail-en-wikipedia-1234" data-series="detail-en-wikipedia-1234" tabindex="-1">'), 1)
        self.assertEqual(page.count('<tr id="compare-detail-ru-wikipedia-5678" data-series="detail-ru-wikipedia-5678" tabindex="-1">'), 1)
        self.assertEqual(page.count('<caption>Daily all-access/user requests'), 2)

    def test_pair_week_changes_exact_safe_counts_and_source_contract(self):
        self.export("pair-week-changes")
        page = (self.root / "pair-week-changes" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="pair-changes" tabindex="0" hidden', page)
        self.assertIn('id="pair-changes-table"', page)
        self.assertIn("Week-over-week Δ is each title", page)
        self.assertIn("pairChanges.hidden = true;", page)
        self.assertIn("pairChangesBody.replaceChildren();", page)
        self.assertIn("pairChanges.hidden = false;", page)
        self.assertIn("signedWeeklyChanges(checkedWeeklyCells(", page)
        from tools.rolling_snapshot_preview import _FILTER_SCRIPT
        start = _FILTER_SCRIPT.index("    function signedWeeklyChanges(counts) {")
        end = _FILTER_SCRIPT.index("    function renderPair()", start)
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js unavailable; native Chromium must test derived changes")
        program = _FILTER_SCRIPT[start:end] + r"""
const equal = (actual, expected) => {
  if (JSON.stringify(actual) !== JSON.stringify(expected))
    throw Error(JSON.stringify({actual, expected}));
};
equal(signedWeeklyChanges(["28","77","126","175","224"]),
      ["—","+49","+49","+49","+49"]);
equal(signedWeeklyChanges(["0","0","0","0","0"]),
      ["—","0","0","0","0"]);
equal(signedWeeklyChanges(["100","90","90","95","0"]),
      ["—","−10","0","+5","−95"]);
equal(signedWeeklyChanges(["90071992547409930000","90071992547409930007",
                           "90071992547409930000","0","0"]),
      ["—","+7","−7","−90,071,992,547,409,930,000","0"]);
"""
        import subprocess
        run = subprocess.run([node, "-e", program], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_pair_share_fail_closed_when_exact_evidence_is_corrupt(self):
        # Guard the pair UI and its Share/export surface, not just the chart:
        # a damaged daily table cannot make a misleading weekly pair sharable.
        self.export("pair-evidence-guard")
        page = (self.root / "pair-evidence-guard" / "index.html").read_text(encoding="utf-8")
        self.assertIn("const evidenceValid = Boolean(valid) && pairEvidenceValid([leftId, rightId]);", page)
        self.assertIn("pairOutput.hidden = !evidenceValid;", page)
        self.assertIn("pairShare.hidden = !evidenceValid;", page)
        self.assertIn("pairCsvButton.hidden = !evidenceValid || !csvSupported;", page)
        self.assertIn("pairDailyCsvButton.hidden = !evidenceValid || !csvSupported;", page)
        self.assertIn("Comparison unavailable: exact daily and weekly evidence did not reconcile.", page)
        self.assertIn('<table id="pair-table">', page)
        from tools.rolling_snapshot_preview import _FILTER_SCRIPT
        start = _FILTER_SCRIPT.index("    function pairEvidenceValid(ids) {")
        end = _FILTER_SCRIPT.index("    function renderPair()", start)
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js unavailable; Chromium acceptance must cover this behavior")
        program = r"""
const row = cells => ({querySelectorAll(selector) {
    if (selector !== "td") throw Error("unexpected selector");
    return cells;
}});
const six = () => Array.from({length: 6}, () => ({textContent: "70"}));
const rowBySeries = new Map([["left", row(six())], ["right", row(six())]]);
const bySeries = new Map([
    ["left", {dataset: {delta2: "140"}}],
    ["right", {dataset: {delta2: "140"}}]
]);
let corruptDaily = false;
function checkedWeeklyCells(id, cells, delta) {
    if (corruptDaily || cells.length !== 6 || delta !== "140")
        throw Error("daily/weekly mismatch");
    return ["70", "70", "70", "70", "140", "+70"];
}
""" + _FILTER_SCRIPT[start:end] + r"""
if (!pairEvidenceValid(["left", "right"]))
    throw Error("valid two-title evidence rejected");
corruptDaily = true;
if (pairEvidenceValid(["left", "right"]))
    throw Error("corrupt source history exposed pair Share");
corruptDaily = false;
rowBySeries.set("left", row([]));
if (pairEvidenceValid(["left", "right"]))
    throw Error("missing weekly cells exposed pair Share");
rowBySeries.set("left", row(six()));
bySeries.get("right").dataset.delta2 = "142";
if (pairEvidenceValid(["left", "right"]))
    throw Error("changed weekly delta exposed pair Share");
bySeries.get("right").dataset.delta2 = "140";
rowBySeries.delete("left");
if (pairEvidenceValid(["left", "right"]))
    throw Error("missing selected title exposed pair Share");
"""
        import subprocess
        result = subprocess.run(
            [node, "-e", program], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pair_daily_charts_use_shared_zero_origin_and_verified_exact_history(self):
        self.export("aligned-pair")
        page = (self.root / "aligned-pair" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="pair-daily-charts" aria-label="Aligned daily request charts" hidden', page)
        self.assertIn("function drawPairDailyCharts(ids)", page)
        self.assertIn("checkedWeeklyCells(id, weekly, card.dataset.delta2)", page)
        self.assertIn("exactDailyRows(id).map(([day, count])", page)
        self.assertIn("requests: BigInt(count)", page)
        self.assertIn("maximum === 0n ? 0", page)
        self.assertIn("(point.requests * 96n + maximum / 2n) / maximum", page)
        self.assertIn("item.daily.length !== 35", page)
        self.assertIn("SAME zero-origin scale", page)
        self.assertIn("Heights are directly comparable", page)
        self.assertIn('svg.setAttribute("role", "img")', page)
        self.assertIn('zero.setAttribute("class", "pair-zero-axis")', page)
        self.assertIn('line.setAttribute("class", "pair-daily-line")', page)
        self.assertIn("pairCharts.replaceChildren();", page)
        self.assertIn("drawPairDailyCharts([leftId, rightId]);", page)
        self.assertIn("Daily charts unavailable: exact dates or counts did not reconcile.", page)
        self.assertIn("#pair-daily-charts[hidden]{display:none!important}", page)
        self.assertIn("grid-template-columns:minmax(0,1fr)", page)
        # The full no-JavaScript comparison and all daily evidence remain in place.
        self.assertIn('<table id="pair-table">', page)
        self.assertEqual(page.count("<caption>Daily all-access/user requests"), 2)

    def test_visible_weekly_changes_export_is_separate_and_source_checked(self):
        self.export("visible-week-changes")
        page = (self.root / "visible-week-changes" / "index.html").read_text(
            encoding="utf-8")
        self.assertIn('id="compare-week-changes-csv" hidden>Download visible weekly changes CSV</button>', page)
        self.assertIn('id="compare-week-changes-csv-status" role="status" aria-live="polite"', page)
        self.assertIn('visibleChangesButton.disabled = shown === 0;', page)
        self.assertIn('visibleChangesButton.hidden = false;', page)
        self.assertIn('function downloadVisibleWeekChangesCsv(ids)', page)
        self.assertIn('function weekChangeLines(ids)', page)
        self.assertIn('function checkedWeekHeaders()', page)
        self.assertIn('weekly CSV dates do not match source observation window', page)
        self.assertIn('const verifiedWeeks = checkedWeekHeaders();', page)
        self.assertIn('downloadVisibleWeekChangesCsv(ids);', page)
        self.assertIn('weekHeaders.length !== 5', page)
        self.assertIn('new Set(ids).size !== ids.length', page)
        self.assertIn('checkedWeeklyCells(', page)
        self.assertIn('saveCsv(lines, "dayflare-visible-week-changes-")', page)
        self.assertIn('The first week', page)
        self.assertIn('#compare-week-changes-csv:focus-visible{outline:3px solid', page)
        self.assertIn('#compare-week-changes-csv[hidden]{display:none!important}', page)
        self.assertIn('Week-to-week CSV unavailable: visible selection or exact source evidence did not reconcile.', page)
        # All exact source rows and the no-JS reading path remain available.
        self.assertIn('id="compare-table"', page)
        self.assertIn('id="detail-en-wikipedia-1234"', page)

    def test_pair_weekly_change_csv_keeps_exact_signed_counts_and_missing_first_week(self):
        self.export("pair-change-csv")
        page = (self.root / "pair-change-csv" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="pair-change-csv" hidden>Download pair weekly changes CSV</button>', page)
        self.assertIn('id="pair-change-csv-status" role="status" aria-live="polite"', page)
        self.assertIn('pairChangeCsvButton.hidden = !evidenceValid || !csvSupported;', page)
        self.assertIn('pairChangeCsvButton.addEventListener("click"', page)
        self.assertIn('.detail-daily-csv[hidden]{display:none!important}', page)
        self.assertIn('#pair-change-csv:focus-visible', page)
        self.assertIn('function downloadPairChangeCsv(ids)', page)
        self.assertIn('checkedWeeklyCells(', page)
        self.assertIn('week === 0 ? ""', page)
        self.assertIn('saveCsv(lines, "dayflare-pair-week-changes-")', page)
        self.assertIn('the first change is unavailable, not zero', page)
        from tools.rolling_snapshot_preview import _FILTER_SCRIPT
        start = _FILTER_SCRIPT.index("    function checkedWeekHeaders() {")
        end = _FILTER_SCRIPT.index("    function downloadCsv(selected, filenamePrefix)", start)
        csv_start = _FILTER_SCRIPT.index("    function csvCell(value, protectFormula) {")
        csv_end = _FILTER_SCRIPT.index("    function countText(value) {", csv_start)
        import csv
        import io
        import subprocess
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js unavailable; Chromium covers real exports")
        program = r"""
const snapshot = {dataset: {dataset: "a".repeat(64), method: "v0", end: "2026-10-21"}};
const weekDates = [["2026-09-17", "2026-09-23"], ["2026-09-24", "2026-09-30"],
    ["2026-10-01", "2026-10-07"], ["2026-10-08", "2026-10-14"],
    ["2026-10-15", "2026-10-21"]];
const weekHeaders = weekDates.map(([weekStart, weekEnd]) => ({
    dataset: {weekStart, weekEnd}
}));
const a = ["9007199254740994", "9007199254741000", "9007199254741000",
           "9007199254740998", "9007199254741001"];
const b = ["100", "30", "30", "50", "10"];
const bySeries = new Map([
    ["left", {dataset: {edition: "en.wikipedia", subject: "science", delta2: "2"}}],
    ["right", {dataset: {edition: "ru.wikipedia", subject: "books", delta2: "-2"}}],
]);
const row = title => ({
    querySelector(selector) { if (selector !== "th a") throw Error("selector"); return {textContent: title}; },
    querySelectorAll(selector) { if (selector !== "td") throw Error("selector"); return Array(6).fill({}); }
});
const rowBySeries = new Map([
    ["left", row("=1+2")], ["right", row("Шахматы")]
]);
let corrupt = false;
function checkedWeeklyCells(id, cells, delta) {
    if (corrupt || cells.length !== 6 || delta !== bySeries.get(id).dataset.delta2)
        throw Error("bad source evidence");
    return [...(id === "left" ? a : b), "+0"];
}
let latest = null;
function saveCsv(lines, name) { latest = {lines, name}; }
""" + _FILTER_SCRIPT[csv_start:csv_end] + _FILTER_SCRIPT[start:end] + r"""
downloadPairChangeCsv(["left", "right"]);
if (!latest || !latest.name.startsWith("dayflare-pair-week-changes-"))
    throw Error("CSV not emitted");
const saved = latest;
corrupt = true;
let rejected = false;
try { downloadPairChangeCsv(["left", "right"]); }
catch (e) { rejected = true; }
if (!rejected || latest !== saved) throw Error("invalid evidence generated CSV");
corrupt = false;
try { downloadPairChangeCsv(["left", "left"]); }
catch (e) { rejected = true; }
if (latest !== saved) throw Error("invalid pair generated CSV");
downloadVisibleWeekChangesCsv(["right"]);
if (!latest || latest.name !== "dayflare-visible-week-changes-" ||
    latest.lines.length !== 6 ||
    !latest.lines[1].includes("right") || !latest.lines[1].endsWith(',""'))
    throw Error("one-title weekly changes missing or first week changed into zero");
const filtered = latest;
downloadVisibleWeekChangesCsv(["right", "left"]);
if (latest.lines.length !== 11 || !latest.lines[1].includes("right") ||
    !latest.lines[6].includes("left"))
    throw Error("filtered cohort order or length changed");
const validVisible = latest;
// A valid-looking but shifted, repeated or reordered calendar heading must
// fail before either export emits a CSV, even if all request counts reconcile.
for (const [index, field, altered] of [
    [0, "weekStart", "2026-09-18"],
    [1, "weekEnd", "2026-10-01"],
    [2, "weekStart", weekDates[1][0]],
    [4, "weekEnd", "2026-10-20"]
]) {
    const previous = weekHeaders[index].dataset[field];
    weekHeaders[index].dataset[field] = altered;
    for (const exportCsv of [
        () => downloadVisibleWeekChangesCsv(["right"]),
        () => downloadPairChangeCsv(["left", "right"])
    ]) {
        let rejected = false;
        try { exportCsv(); } catch (e) { rejected = true; }
        if (!rejected || latest !== validVisible)
            throw Error("altered weekly UTC dates generated a CSV");
    }
    weekHeaders[index].dataset[field] = previous;
}
// Exact seven-day boundaries must also hold across leap day and New Year.
// These explicit expected dates are independent of the helper calculation.
function checkCalendar(end, expected) {
    snapshot.dataset.end = end;
    expected.forEach(([weekStart, weekEnd], index) => {
        weekHeaders[index].dataset.weekStart = weekStart;
        weekHeaders[index].dataset.weekEnd = weekEnd;
    });
    if (JSON.stringify(checkedWeekHeaders()) !== JSON.stringify(expected))
        throw Error("incorrect week boundaries for " + end);
}
checkCalendar("2024-03-06", [
    ["2024-02-01", "2024-02-07"], ["2024-02-08", "2024-02-14"],
    ["2024-02-15", "2024-02-21"], ["2024-02-22", "2024-02-28"],
    ["2024-02-29", "2024-03-06"]
]);
checkCalendar("2027-01-06", [
    ["2026-12-03", "2026-12-09"], ["2026-12-10", "2026-12-16"],
    ["2026-12-17", "2026-12-23"], ["2026-12-24", "2026-12-30"],
    ["2026-12-31", "2027-01-06"]
]);
snapshot.dataset.end = "2024-02-30";
let invalidEndRejected = false;
try { checkedWeekHeaders(); } catch (e) { invalidEndRejected = true; }
if (!invalidEndRejected) throw Error("impossible UTC end accepted");
checkCalendar("2026-10-21", weekDates);
corrupt = true;
rejected = false;
try { downloadVisibleWeekChangesCsv(["left"]); }
catch (e) { rejected = true; }
if (!rejected || latest !== validVisible)
    throw Error("corrupted source generated visible weekly changes");
corrupt = false;
rejected = false;
try { downloadVisibleWeekChangesCsv(["left", "left"]); }
catch (e) { rejected = true; }
if (!rejected || latest !== validVisible)
    throw Error("duplicate visible history generated a CSV");
console.log(JSON.stringify(saved.lines));
"""
        result = subprocess.run(
            [node, "-e", program], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        records = list(csv.reader(io.StringIO("\n".join(json.loads(result.stdout)))))
        self.assertEqual(len(records), 11)
        self.assertEqual(records[0], [
            "dataset_sha256", "method_version", "observation_end_utc",
            "snapshot_series_key", "edition", "title", "subject",
            "utc_week_start", "utc_week_end", "weekly_requests",
            "change_from_prior_week_requests"])
        self.assertEqual([row[10] for row in records[1:6]], ["", "+6", "0", "-2", "+3"])
        self.assertEqual([row[10] for row in records[6:]], ["", "-70", "0", "+20", "-40"])
        self.assertEqual(records[1][9], "9007199254740994")
        self.assertEqual(records[2][9], "9007199254741000")
        self.assertEqual(records[1][3:7], ["left", "en.wikipedia", "'=1+2", "science"])
        self.assertEqual(records[6][3:7], ["right", "ru.wikipedia", "Шахматы", "books"])
        self.assertTrue(all(row[0] == "a" * 64 and row[1:3] == ["v0", "2026-10-21"]
                            for row in records[1:]))

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
        # Source dates and archive status precede optional download guidance
        # in DOM order, including on narrow screens and without JavaScript.
        self.assertLess(html.index('class="hero-action"'), html.index('class="metadata"'))
        self.assertLess(html.index('class="metadata"'), html.index('class="warning"'))
        self.assertLess(html.index('class="warning"'), html.index('class="archive-age"'))
        self.assertLess(html.index('class="archive-age"'), html.index('class="save-action"'))
        self.assertIn('@media(max-width:560px){header{padding:max(3.75rem,60px) 0 2rem}', html)
        self.assertIn('.skip:focus{top:.5rem;display:inline-flex;align-items:center;min-height:44px;', html)
        self.assertIn('padding:.45rem .7rem;line-height:1.25;outline-offset:2px}', html)
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
        self.assertIn('<label for="atlas-order">Sort selected titles', html)
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
        self.assertIn('<option value="volume">Last-week volume</option>', html)
        self.assertIn('<option value="increase">Increase</option>', html)
        self.assertIn('<option value="decrease">Decrease</option>', html)
        self.assertIn('<option value="relative-increase">Relative rise (%)</option>', html)
        self.assertIn('<option value="relative-decrease">Relative fall (%)</option>', html)
        self.assertIn('<option value="all">All changes</option>', html)
        self.assertIn('<option value="positive">Increase</option>', html)
        self.assertIn('<option value="negative">Decrease</option>', html)
        self.assertIn('<option value="unchanged">No change</option>', html)
        self.assertIn('Order by exact last-week change in requests', html)
        self.assertIn('data-delta2="245" data-baseline2="203" data-last-week="224"', html)  # +122.5 / 101.5, 224 requests
        self.assertIn('data-delta2="0" data-baseline2="0" data-last-week="0"', html)
        self.assertIn('Zero baselines are unavailable', html)
        self.assertIn('tiny baselines can magnify', html)
        self.assertIn('left * rightBase - right * leftBase', html)
        self.assertIn('leftBase === 0n ? 1 : -1', html)
        self.assertIn('"editorial", "volume", "daily-rise", "increase"', html)
        self.assertIn('relative-increase", "relative-decrease"', html)
        self.assertIn('const leftVolume = BigInt(a.dataset.lastWeek)', html)
        self.assertIn('const rightVolume = BigInt(b.dataset.lastWeek)', html)
        self.assertIn('leftVolume > rightVolume ? -1 : 1', html)
        self.assertIn('Last-week volume orders by the most recent complete seven-day request total', html)
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
        self.assertIn("Visible: EN ", html)
        self.assertIn("weekly increases ", html)
        self.assertIn("vs each title's four-week median.", html)
        self.assertIn("if (signedDelta > 0n) increaseShown++;", html)
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
        self.assertIn('<tr id="compare-detail-ru-wikipedia-5678" data-series="detail-ru-wikipedia-5678" tabindex="-1">', html)
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
        self.assertIn('                signMatches && stepMatches;', html)
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

    def test_peak_caption_links_to_its_exact_daily_row_without_script(self):
        self.export("peak-evidence-link")
        html = (self.root / "peak-evidence-link" / "index.html").read_text(encoding="utf-8")
        target = "day-detail-en-wikipedia-1234-2026-10-21"
        self.assertIn(
            '<a class="daily-peak-jump" href="#' + target +
            '">Jump to exact daily row ↓</a>', html)
        self.assertIn('<tr id="' + target + '"><th scope="row">2026-10-21</th><td>35</td>', html)
        self.assertEqual(html.count('class="daily-peak-jump"'), 1)
        # All 35 dates per edition are stable unique anchors, without changing table cells.
        self.assertEqual(len(re.findall(
            r'<tr id="day-detail-(?:en|ru)-wikipedia-(?:1234|5678)-2026-[0-9]{2}-[0-9]{2}">',
            html)), 70)
        self.assertIn('article .scroll table tbody tr:target{outline:3px solid #ffca7f', html)
        days = [{"date": (START + timedelta(days=i)).isoformat(), "views": 0}
                for i in range(35)]
        self.assertNotIn('daily-peak-jump', _daily_curve(days, "detail-ru-wikipedia-5678"))
        days[4]["views"] = 10
        days[12]["views"] = 10
        linked = _daily_curve(days, "detail-en-wikipedia-1234")
        self.assertIn('href="#day-detail-en-wikipedia-1234-' + days[4]["date"] + '"', linked)
        self.assertIn("also on 1 other UTC day", linked)
        with self.assertRaises(ValueError):
            _daily_curve(days, 'detail-"><script')

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
        self.assertIn('first peak <time datetime="2026-10-21">2026-10-21</time> UTC', html)
        self.assertIn("no distinct peak (0 requests on all 35 days)", html)
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

    def test_daily_curve_reports_first_peak_ties_and_all_zero(self):
        start = date(2026, 9, 17)
        days = [{"date": (start + timedelta(days=i)).isoformat(), "views": 0}
                for i in range(35)]
        empty = _daily_curve(days)
        self.assertIn("no distinct peak: all 35 UTC days recorded zero requests", empty)
        self.assertIn("no distinct peak (0 requests on all 35 days)", empty)
        self.assertNotIn("<time datetime=", empty)
        # Three equal maxima must not silently imply one unique peak day.
        for index in (2, 9, 30):
            days[index]["views"] = 17
        original = [dict(point) for point in days]
        result = _daily_curve(days)
        first_peak = days[2]["date"]
        self.assertIn('first peak <time datetime="' + first_peak + '">' +
                      first_peak + '</time> UTC (also on 2 other UTC days)', result)
        self.assertIn("first peak on " + first_peak + " UTC; also on 2 other UTC days", result)
        self.assertEqual(result.count("<time datetime="), 1)
        self.assertEqual(days, original)  # observation values are not modified
        days[9]["views"] = 0
        one_tie = _daily_curve(days)
        self.assertIn("also on 1 other UTC day", one_tie)
        days[30]["views"] = 0
        unique = _daily_curve(days)
        self.assertNotIn("also on", unique)
        self.assertIn("first peak on " + first_peak + " UTC", unique)

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

    def test_weekly_bars_have_visible_utc_starts_and_exact_accessible_ranges(self):
        self.export("weekly-bars")
        html = (self.root / "weekly-bars" / "index.html").read_text()
        self.assertEqual(html.count('class="week-bars" role="img"'), 2)
        self.assertIn(
            'aria-label="Weekly requests, oldest to newest: '
            'week 1 2026-09-17 to 2026-09-23 UTC: 28 requests; '
            'week 2 2026-09-24 to 2026-09-30 UTC: 77 requests; '
            'week 3 2026-10-01 to 2026-10-07 UTC: 126 requests; '
            'week 4 2026-10-08 to 2026-10-14 UTC: 175 requests; '
            'week 5 2026-10-15 to 2026-10-21 UTC: 224 requests"',
            html)
        self.assertIn(
            'aria-label="Weekly requests, oldest to newest: '
            'week 1 2026-09-17 to 2026-09-23 UTC: 0 requests;',
            html)
        self.assertEqual(html.count('class="bar-index" datetime="2026-09-17">17 Sep</time>'), 2)
        self.assertEqual(html.count('class="bar-index" datetime="2026-10-15">15 Oct</time>'), 2)
        self.assertEqual(html.count('class="bar-index" datetime='), 10)
        self.assertIn('style="height:13%"', html)  # Week 1: 28 / 224
        self.assertIn('style="height:100%"', html)
        self.assertIn('style="height:0%"', html)
        self.assertIn('each label shows the week start date', html)
        self.assertIn('each title has its own scale', html)
        self.assertIn('href="#compare">Exact weekly values</a>', html)
        self.assertEqual(_weekly_bars([0, 0, 0, 0, 0], "2026-10-21").count('height:0%'), 5)
        self.assertEqual(_weekly_bars([0, 0, 0, 0, 0], "2026-10-21").count('0 requests'), 5)
        with self.assertRaisesRegex(ValueError, "five nonnegative"):
            _weekly_bars([1, -1, 2, 3, 4], "2026-10-21")
        with self.assertRaisesRegex(ValueError, "five nonnegative"):
            _weekly_bars([1, 2, 3, 4], "2026-10-21")
        self.assertIn('<script>', html)
        self.assertNotIn('<script src=', html)

    def test_weekly_bar_dates_are_canonical_and_span_year_boundary(self):
        years = _weekly_bars([1, 2, 3, 4, 5], "2026-01-02")
        self.assertIn('datetime="2025-11-29">29 Nov</time>', years)
        self.assertIn('datetime="2025-12-27">27 Dec</time>', years)
        self.assertIn('week 5 2025-12-27 to 2026-01-02 UTC: 5 requests', years)
        for bad in ("20260102", "2026-01-00", "2026-02-30",
                    "2026-01-02T00:00:00Z", "0001-01-01", None):
            with self.subTest(end=bad):
                with self.assertRaisesRegex(ValueError, "canonical complete UTC"):
                    _weekly_bars([1, 2, 3, 4, 5], bad)

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
