"""Actual Chromium local-HTTP acceptance of the synthetic rolling-source atlas."""
from __future__ import annotations

import csv
import json
import shutil

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import threading

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rolling_pageview_source import canonical, collect_to_new_directory
from tools.rolling_snapshot_preview import export_verified_preview
SHOTS = ROOT / "evidence" / "local-m1-browser"


def main():
    # Reuse exactly the offline injected source fixture, never call Wikimedia.
    spec = importlib.util.spec_from_file_location(
        "rolling_preview_fixture", ROOT / "tests" / "test_rolling_snapshot_preview.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    SHOTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        seed_path = root / "seed.json"
        seed_path.write_bytes(canonical(fixture.seed()))
        source = root / "source"
        collect_to_new_directory(seed_path, source, now=lambda: fixture.NOW,
                                 fetch=fixture.fake, sleep=lambda _: None, injected=True)
        export_verified_preview(source, root / "preview", now=fixture.NOW)
        # Synthetic stage fixture for local-HTTP /m1/ and immutable paths.
        digest = json.loads((root / "preview/preview-manifest.json").read_text())["candidate_sha256"]
        m1 = root / "m1"
        m1.mkdir()
        immutable = m1 / "archives" / digest
        immutable.mkdir(parents=True)
        for target in (m1 / "index.html", immutable / "index.html"):
            shutil.copyfile(root / "preview/index.html", target)
        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/preview/"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True,
                    executable_path=os.environ.get("CHROMIUM_EXECUTABLE"))
                for width, height in [(1280, 850), (390, 844), (320, 700)]:
                    page = browser.new_page(viewport={"width": width, "height": height},
                                            device_scale_factor=1, java_script_enabled=False)
                    page.goto(url, wait_until="domcontentloaded")
                    expect(page.locator("h1")).to_have_text("Where did attention change?")
                    # Same-document download works at arbitrary offline filenames
                    # and hosted mutable/immutable paths without JavaScript.
                    save = page.locator(".save-snapshot")
                    expect(save).to_be_visible()
                    expect(save).to_have_attribute("href", "")
                    expect(save).to_have_attribute(
                        "download", "dayflare-m1-2026-10-21-" + digest[:12] + ".html")
                    assert save.evaluate(
                        "(el) => el.getBoundingClientRect().height") >= 44
                    assert save.evaluate(
                        "(el) => new URL(el.getAttribute('href'), document.baseURI).pathname"
                    ) == "/preview/"
                    expect(page.locator(".card")).to_have_count(2)
                    # Cohort coverage is a real, source-derived no-JS overview;
                    # signs are title-level comparisons, not lifecycle labels.
                    subject_rows = page.locator("#subject-change-coverage tbody tr")
                    expect(subject_rows).to_have_count(2)
                    expect(subject_rows.first).to_contain_text("Culture")
                    expect(subject_rows.last).to_contain_text("Sport")
                    assert [cell.inner_text() for cell in
                            subject_rows.first.locator("td").all()] == [
                                "1", "0", "1", "0", "0", "1", "0", "0", "1"]
                    assert [cell.inner_text() for cell in
                            subject_rows.last.locator("td").all()] == [
                                "1", "1", "0", "1", "0", "0", "1", "0", "0"]
                    expect(page.locator('.subject-signal-list .signal-counts').last).to_contain_text(
                        'Vs four-week median: Increase 1 · Decrease 0 · No change 0')
                    # A second, dated and source-derived sign summary stays
                    # readable without script; it must not overwrite median bars.
                    steps = page.locator(".subject-signal-list .signal-step-counts")
                    expect(steps).to_have_count(2)
                    expect(steps.first).to_have_text(
                        "Latest full UTC week vs prior: Gain 0 · Drop 0 · No change 1 / 1 selected")
                    expect(steps.last).to_have_text(
                        "Latest full UTC week vs prior: Gain 1 · Drop 0 · No change 0 / 1 selected")
                    assert steps.first.evaluate(
                        "(el) => el.getBoundingClientRect().width <= innerWidth"
                    )
                    if width == 320:
                        steps.first.scroll_into_view_if_needed()
                        page.screenshot(
                            path=str(SHOTS / "m1-rolling-subject-week-step-320.png"),
                            full_page=False)
                    expect(page.locator(".subject-coverage-scroll")).to_be_visible()
                    # Native subject links remain useful without JavaScript.
                    expect(subject_rows.first.locator("a")).to_have_attribute(
                        "href", "#detail-ru-wikipedia-5678")
                    expect(subject_rows.last.locator("a")).to_have_attribute(
                        "href", "#detail-en-wikipedia-1234")

                    expect(page.locator("article .detail-weeks")).to_have_count(2)
                    expect(page.locator("#detail-en-wikipedia-1234 .detail-weeks")).to_be_visible()
                    expect(page.locator("#detail-ru-wikipedia-5678 .detail-weeks")).to_be_visible()
                    expect(page.locator("#detail-en-wikipedia-1234 .detail-weeks li")).to_have_count(5)
                    expect(page.locator("#detail-ru-wikipedia-5678 .detail-weeks li")).to_have_count(5)
                    en_steps = page.locator("#detail-en-wikipedia-1234 .detail-weeks .week-step")
                    ru_steps = page.locator("#detail-ru-wikipedia-5678 .detail-weeks .week-step")
                    expect(en_steps).to_have_count(5)
                    expect(ru_steps).to_have_count(5)
                    expect(en_steps.first).to_contain_text("unavailable")
                    for step in en_steps.all()[1:]:
                        expect(step).to_contain_text("Δ vs previous UTC week: +49 requests")
                    for step in ru_steps.all()[1:]:
                        expect(step).to_contain_text("Δ vs previous UTC week: 0 requests")
                    expect(page.locator("article .daily-curve svg[role=img]")).to_have_count(2)
                    assert "peak 35 requests; zero-origin" in page.locator("article .daily-curve svg").first.get_attribute("aria-label")
                    assert "peak 0 requests; zero-origin" in page.locator("article .daily-curve svg").last.get_attribute("aria-label")
                    assert page.locator("article .daily-curve .daily-line").first.get_attribute("points").startswith("12,88 22,86")
                    assert page.locator("article .daily-curve .daily-line").last.get_attribute("points").startswith("12,90 22,90")
                    # Peak timing is both visible and screen-reader accessible even with JS off.
                    expect(page.locator("article .daily-curve figcaption time")).to_have_count(1)
                    expect(page.locator("article .daily-curve figcaption time")).to_have_attribute(
                        "datetime", "2026-10-21")
                    expect(page.locator("article .daily-curve").first).to_contain_text(
                        "first peak 2026-10-21 UTC")
                    expect(page.locator("article .daily-curve").last).to_contain_text(
                        "no distinct peak (0 requests on all 35 days)")
                    # The first-screen latest-week step is distinct from the
                    # four-week median delta, exact and visible with JS disabled.
                    expect(page.locator(".card .latest-week-step")).to_have_count(2)
                    expect(page.locator(
                        '.card[data-series="detail-en-wikipedia-1234"] .latest-week-step')
                    ).to_contain_text("+49 requests")
                    expect(page.locator(
                        '.card[data-series="detail-ru-wikipedia-5678"] .latest-week-step')
                    ).to_contain_text("0 requests")
                    # Daily rise is an independent source-derived 34-step measure,
                    # with a real native jump to the second exact date.
                    expect(page.locator('.card[data-series="detail-en-wikipedia-1234"] .daily-rise')).to_contain_text(
                        "Largest daily rise in 34 adjacent UTC-day comparisons: +1 requests on 2026-09-18 UTC")
                    expect(page.locator('.card[data-series="detail-ru-wikipedia-5678"] .daily-rise')).to_contain_text(
                        "No positive one-day increase")
                    expect(page.locator('.card .daily-rise a')).to_have_count(1)
                    assert page.locator('.card .daily-rise a').evaluate(
                        'el => el.getBoundingClientRect().height') >= 44
                    expect(page.locator('.card .daily-rise a')).to_have_attribute(
                        "href", "#day-detail-en-wikipedia-1234-2026-09-18")
                    expect(page.locator("#atlas-filters")).to_be_hidden()
                    expect(page.locator(".card-pair")).to_have_count(2)
                    expect(page.locator("#compare-csv")).to_be_hidden()
                    expect(page.locator("#subject-coverage-csv")).to_be_hidden()
                    expect(page.locator("#compare-daily-csv")).to_be_hidden()
                    expect(page.locator("#compare-week-changes-csv")).to_be_hidden()
                    expect(page.locator("#pair-csv")).to_be_hidden()
                    expect(page.locator("#pair-change-csv")).to_be_hidden()
                    expect(page.locator("#pair-daily-charts")).to_be_hidden()
                    expect(page.locator("#pair-changes")).to_be_hidden()
                    expect(page.locator(".detail-daily-csv")).to_have_count(2)
                    expect(page.locator(".detail-daily-csv").first).to_be_hidden()
                    share_link = page.locator("#atlas-filter-link")
                    expect(share_link).to_be_hidden()
                    assert share_link.evaluate("(el) => getComputedStyle(el).display") == "none"
                    expect(page.locator("article")).to_have_count(2)
                    expect(page.locator(".warning")).to_contain_text("SYNTHETIC TEST DATA")
                    expect(page.locator("tbody tr")).to_have_count(2 + 2 + 2 * 35)
                    expect(page.locator("#compare-table tbody tr:visible")).to_have_count(2)
                    expect(page.locator("#compare-results")).to_contain_text("All 2")
                    geometry = page.evaluate("""() => ({
                        viewport: innerWidth,
                        document: document.documentElement.scrollWidth,
                        offenders: [...document.querySelectorAll('body *')]
                          .filter(el => el.getBoundingClientRect().right > innerWidth + 1)
                          .slice(0, 8)
                          .map(el => ({tag: el.tagName, class: el.className,
                                       text: el.textContent.slice(0, 80),
                                       right: el.getBoundingClientRect().right}))
                    })""")
                    assert geometry["document"] <= geometry["viewport"], (
                        f"document overflow at {width}px: {geometry}")
                    if width == 320:
                        # A real 30-title EN/RU source preview exposed a long
                        # unbroken Russian title that widened the whole page.
                        # Exercise the same heading in the no-JS visitor flow.
                        ru_heading = page.locator(
                            "#heading-detail-ru-wikipedia-5678")
                        original_heading = ru_heading.text_content()
                        ru_heading.evaluate(
                            "(el) => el.textContent = 'Дезоксирибонуклеиновая кислота'")
                        assert ru_heading.evaluate(
                            "el => el.scrollWidth <= el.clientWidth"), (
                            "Long Russian detail title must wrap in its card")
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"), (
                            "Long Russian detail title caused document overflow at 320px")
                        ru_heading.evaluate(
                            "(el, title) => el.textContent = title", original_heading)
                    page.keyboard.press("Tab")
                    assert page.evaluate('document.activeElement.className') == 'skip'
                    assert page.locator('.skip').evaluate('(el) => getComputedStyle(el).outlineWidth') != '0px'
                    # Verify first-Tab skip navigation from untouched page load
                    # before clicking a card link (which changes focus/hash).
                    # Without JS the native shortcut lands on THIS title's
                    # exact weekly row, not an uninitialized pair selector.
                    native_pair_link = page.locator(".card-pair").first
                    expect(native_pair_link).to_have_attribute(
                        "href", "#compare-detail-en-wikipedia-1234")
                    native_pair_link.click()
                    assert page.evaluate("location.hash") == "#compare-detail-en-wikipedia-1234"
                    native_row = page.locator("#compare-detail-en-wikipedia-1234")
                    expect(native_row).to_be_visible()
                    expect(native_row).to_contain_text("Chess")
                    assert native_row.evaluate(
                        "el => getComputedStyle(el).outlineStyle") != "none"
                    expect(page.locator("#pair-form")).to_be_hidden()
                    expect(page.locator("#compare-table tbody tr")).to_have_count(2)
                    # The detail itself also offers a native exact-row action.
                    # This works at 320/390/1280 without script or another title.
                    detail_pair = page.locator("#detail-en-wikipedia-1234 .detail-pair")
                    expect(detail_pair).to_have_attribute(
                        "href", "#compare-detail-en-wikipedia-1234")
                    assert detail_pair.evaluate(
                        "el => el.getBoundingClientRect().height") >= 44
                    detail_pair.click()
                    assert page.evaluate("location.hash") == "#compare-detail-en-wikipedia-1234"
                    expect(native_row).to_be_visible()
                    assert native_row.evaluate(
                        "el => getComputedStyle(el).outlineStyle") != "none"
                    # Method explanation is keyboard-accessible without JavaScript,
                    # but collapsed by default so discovery is the first action.
                    method = page.locator("#atlas-method")
                    expect(method.locator("summary")).to_be_visible()
                    assert not method.evaluate("el => el.open")
                    assert method.evaluate("(el) => el.nextElementSibling.id") == "atlas-filters"
                    method.locator("summary").focus()
                    page.keyboard.press("Enter")
                    assert method.evaluate("el => el.open")
                    expect(method.locator("p")).to_have_count(3)
                    page.keyboard.press("Enter")
                    assert not method.evaluate("el => el.open")
                    page.get_by_role("link", name="Chess & <svg onload='bad()'>").first.click()
                    assert page.evaluate("location.hash") == "#detail-en-wikipedia-1234"
                    expect(page.locator("#detail-en-wikipedia-1234 h3")).to_contain_text("Chess")
                    # Native peak-to-source navigation stays useful with JavaScript disabled.
                    # In the all-zero RU history there is no fabricated peak to jump to.
                    peak_jump = page.locator("#detail-en-wikipedia-1234 .daily-peak-jump")
                    expect(peak_jump).to_have_count(1)
                    expect(page.locator("#detail-ru-wikipedia-5678 .daily-peak-jump")).to_have_count(0)
                    expect(peak_jump).to_have_attribute(
                        "href", "#day-detail-en-wikipedia-1234-2026-10-21")
                    assert peak_jump.evaluate(
                        "el => el.getBoundingClientRect().height") >= 44
                    peak_jump.focus()
                    page.keyboard.press("Enter")
                    assert page.evaluate("location.hash") == "#day-detail-en-wikipedia-1234-2026-10-21"
                    exact_peak = page.locator(
                        "#day-detail-en-wikipedia-1234-2026-10-21")
                    expect(exact_peak).to_be_visible()
                    expect(exact_peak).to_contain_text("35")
                    expect(exact_peak).to_contain_text("2026-10-21")
                    assert exact_peak.evaluate(
                        "el => getComputedStyle(el).outlineStyle") != "none"
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    # This native weekly disclosure remains usable without JS
                    # via keyboard and exposes the exact source-derived dates.
                    weekly = page.locator("#detail-en-wikipedia-1234 .detail-weeks")
                    weekly_summary = weekly.locator("summary")
                    expect(weekly_summary).to_have_text("Five exact weekly totals (UTC)")
                    assert not weekly.evaluate("el => el.open")
                    weekly_summary.focus()
                    page.keyboard.press("Enter")
                    assert weekly.evaluate("el => el.open")
                    expect(weekly.locator("li")).to_have_count(5)
                    expect(weekly.locator("li").last).to_contain_text(
                        "2026-10-15 – 2026-10-21 UTC: 224 requests")
                    assert weekly_summary.evaluate(
                        "(el) => getComputedStyle(el).outlineStyle") != "none"
                    # A separate source-evidence disclosure still works; don't
                    # confuse it with the new weekly-history disclosure.
                    source_detail = page.locator(
                        "#detail-en-wikipedia-1234 details:not(.detail-weeks)")
                    source_summary = source_detail.locator("summary")
                    source_summary.focus()
                    page.keyboard.press("Enter")
                    assert source_detail.evaluate("el => el.open")
                    expect(source_detail.locator("code")).to_be_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=str(SHOTS / f"m1-rolling-atlas-{width}.png"),
                                    full_page=(width != 1280))
                    page.close()
                # The identical HTML is also staged at mutable and immutable
                # URLs. No-JS saving must retain whichever exact URL is open.
                for path in ("/m1/", "/m1/archives/" + digest + "/"):
                    saved = browser.new_page(viewport={"width": 390, "height": 844},
                                             java_script_enabled=False)
                    saved.goto(f"http://127.0.0.1:{server.server_port}" + path,
                               wait_until="domcontentloaded")
                    expect(saved.locator(".save-snapshot")).to_have_attribute(
                        "download", "dayflare-m1-2026-10-21-" + digest[:12] + ".html")
                    assert saved.locator(".save-snapshot").evaluate(
                        "(el) => new URL(el.getAttribute('href'), document.baseURI).pathname"
                    ) == path
                    # The element must actually download the exact currently
                    # served HTML bytes, not merely display a download label.
                    with saved.expect_download() as download:
                        saved.locator(".save-snapshot").click()
                    assert download.value.suggested_filename == (
                        "dayflare-m1-2026-10-21-" + digest[:12] + ".html")
                    assert Path(download.value.path()).read_bytes() == (
                        root / "preview/index.html").read_bytes()
                    saved.close()
                # Progressive enhancement: discovery filters scope the weekly
                # comparison rows, but never remove the exact daily evidence.
                page = browser.new_page(viewport={"width": 390, "height": 844},
                                        device_scale_factor=1, java_script_enabled=True)
                errors = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.goto(url, wait_until="domcontentloaded")
                expect(page.locator("#atlas-filters")).to_be_visible()
                expect(page.locator("#subject-change-coverage tbody tr")).to_have_count(2)
                expect(page.locator("#subject-change-coverage caption")).to_contain_text(
                    "Not Wikipedia-wide.")
                # Exercise the actual blob download via keyboard, not just the
                # embedded JS helper. This is SYNTHETIC evidence, not live data.
                coverage_export = page.get_by_role(
                    "button", name="Download selected-subject coverage CSV")
                expect(coverage_export).to_be_visible()
                expect(coverage_export).to_be_enabled()
                assert coverage_export.evaluate(
                    "el => el.getBoundingClientRect().height") >= 44
                coverage_export.focus()
                with page.expect_download() as coverage_download:
                    page.keyboard.press("Enter")
                assert coverage_download.value.suggested_filename.startswith(
                    "dayflare-subject-coverage-")
                with Path(coverage_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    coverage_csv = list(csv.reader(handle))
                assert coverage_csv[0] == [
                    "dataset_sha256", "method_version", "observation_end_utc",
                    "subject", "selected", "en", "ru", "increase", "decrease",
                    "no_change", "week_gain", "week_drop", "week_no_change"]
                assert [row[3:] for row in coverage_csv[1:]] == [
                    ["culture", "1", "0", "1", "0", "0", "1", "0", "0", "1"],
                    ["sport", "1", "1", "0", "1", "0", "0", "1", "0", "0"]]
                assert all(row[:3] == [digest, "v0-empirical-35d", "2026-10-21"]
                           for row in coverage_csv[1:])
                expect(page.locator("#subject-coverage-csv-status")).to_contain_text(
                    "CSV prepared for 2 selected subjects")
                page.set_viewport_size({"width": 320, "height": 700})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                coverage_export.scroll_into_view_if_needed()
                page.screenshot(path=str(SHOTS / "m1-rolling-subject-coverage-csv-320.png"),
                                animations="disabled")
                page.set_viewport_size({"width": 390, "height": 844})
                # Clicking subject coverage scopes the selected cohort rather
                # than silently opening only one example; exact filtered-view
                # links still include the immutable dataset identity.
                page.locator('#subject-change-coverage a[data-filter-subject="sport"]').click()
                expect(page.locator("#atlas-subject")).to_have_value("sport")
                expect(page.locator("#atlas-subject")).to_be_focused()
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator(".card:visible")).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                assert page.locator("#atlas-filter-link").evaluate(
                    "(a) => new URL(a.href).searchParams.get('af_subject')") == "sport"
                assert page.locator("#atlas-filter-link").evaluate(
                    "(a) => new URL(a.href).searchParams.get('af_dataset')") == digest
                # A discovery filter never alters the editorially selected
                # cohort exported by the exact coverage table.
                with page.expect_download() as filtered_coverage_download:
                    coverage_export.click()
                with Path(filtered_coverage_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    assert list(csv.reader(handle)) == coverage_csv
                page.locator('#subject-change-coverage a[data-filter-subject="culture"]').click()
                expect(page.locator("#atlas-subject")).to_have_value("culture")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator(".card:visible")).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                page.locator("#atlas-filters button[type=reset]").click()
                expect(page.locator("#atlas-subject")).to_have_value("all")
                expect(page.locator(".card:visible")).to_have_count(2)
                # Invalid 35-day evidence must fail closed: no Blob/download.
                # Restore the DOM immediately so other browser journeys remain
                # independent of these deliberately corrupted fixture values.
                bad_daily = page.locator(
                    "#detail-en-wikipedia-1234 .scroll table tbody tr td").first
                bad_daily_creations = bad_daily.evaluate("""el => {
                    const originalCell = el.textContent;
                    const originalBlob = URL.createObjectURL;
                    let created = 0;
                    URL.createObjectURL = function(...args) {
                        created++;
                        return originalBlob.apply(this, args);
                    };
                    try {
                        el.textContent = 'not-a-source-count';
                        document.querySelector('#subject-coverage-csv').click();
                        return created;
                    } finally {
                        el.textContent = originalCell;
                        URL.createObjectURL = originalBlob;
                    }
                }""")
                assert bad_daily_creations == 0, "corrupt daily data generated a CSV Blob"
                expect(page.locator("#subject-coverage-csv-status")).to_contain_text(
                    "Subject CSV unavailable")
                bad_count = page.locator(
                    "#subject-change-coverage tbody tr:first-child td:first-of-type")
                bad_count_creations = bad_count.evaluate("""el => {
                    const originalCell = el.textContent;
                    const originalBlob = URL.createObjectURL;
                    let created = 0;
                    URL.createObjectURL = function(...args) {
                        created++;
                        return originalBlob.apply(this, args);
                    };
                    try {
                        el.textContent = '2';
                        document.querySelector('#subject-coverage-csv').click();
                        return created;
                    } finally {
                        el.textContent = originalCell;
                        URL.createObjectURL = originalBlob;
                    }
                }""")
                assert bad_count_creations == 0, "tampered subject count generated a CSV Blob"
                expect(page.locator("#subject-coverage-csv-status")).to_contain_text(
                    "Subject CSV unavailable")
                # A changed week-step table cell must not generate a plausible
                # CSV; neither may edited card metadata that disagrees with the
                # five source-verified complete UTC weeks.
                bad_recent_count = page.locator(
                    "#subject-change-coverage tbody tr:last-child td:last-child")
                bad_recent_creations = bad_recent_count.evaluate("""el => {
                    const old = el.textContent;
                    const originalBlob = URL.createObjectURL;
                    let created = 0;
                    URL.createObjectURL = function(...args) {
                        created++;
                        return originalBlob.apply(this, args);
                    };
                    try {
                        el.textContent = '1';
                        document.querySelector('#subject-coverage-csv').click();
                        return created;
                    } finally {
                        el.textContent = old;
                        URL.createObjectURL = originalBlob;
                    }
                }""")
                assert bad_recent_creations == 0, "tampered week-step count generated CSV"
                card_recent_creations = page.locator(
                    '.card[data-series="detail-en-wikipedia-1234"]').evaluate("""el => {
                    const old = el.dataset.weekStep;
                    const originalBlob = URL.createObjectURL;
                    let created = 0;
                    URL.createObjectURL = function(...args) {
                        created++;
                        return originalBlob.apply(this, args);
                    };
                    try {
                        el.dataset.weekStep = '999';
                        document.querySelector('#subject-coverage-csv').click();
                        return created;
                    } finally {
                        el.dataset.weekStep = old;
                        URL.createObjectURL = originalBlob;
                    }
                }""")
                assert card_recent_creations == 0, "tampered week-step metadata generated CSV"
                expect(page.locator("#subject-coverage-csv-status")).to_contain_text(
                    "Subject CSV unavailable")
                with page.expect_download() as restored_coverage_download:
                    coverage_export.click()
                with Path(restored_coverage_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    assert list(csv.reader(handle)) == coverage_csv
                expect(page.locator("#subject-coverage-csv-status")).to_contain_text(
                    "CSV prepared for 2 selected subjects")
                # Keep visible discovery ahead of the long methodology copy on
                # narrow screens; a collapsed native disclosure keeps all caveats.
                assert page.evaluate("""() => (
                    document.querySelector("#atlas-filters").getBoundingClientRect().top -
                    document.querySelector("#overview").getBoundingClientRect().bottom
                )""") < 300
                assert not page.locator("#atlas-method").evaluate("el => el.open")
                expect(page.locator(".card:visible")).to_have_count(2)
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(2)
                # Pasted Wikipedia URL title slugs are searchable without
                # rewriting the title, data or the exact shared query.
                english = page.locator('.card[data-edition="en.wikipedia"]')
                original_english_title = english.get_attribute("data-title")
                english.evaluate("(card) => { card.dataset.title = 'Black hole'; }")
                for slug in ("black_hole", "BLACK__HOLE"):
                    page.locator("#atlas-query").fill(slug)
                    expect(page.locator(".card:visible")).to_have_count(1)
                    expect(page.locator(".card:visible")).to_have_attribute(
                        "data-series", "detail-en-wikipedia-1234")
                    expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                    assert page.locator("#atlas-filter-link").evaluate(
                        "(a) => new URL(a.href).searchParams.get('af_query')") == slug
                    expect(page.locator(".card:visible h3")).to_contain_text("Chess")
                page.locator("#atlas-query").fill("")
                english.evaluate("(card, value) => { card.dataset.title = value; }",
                                 original_english_title)
                # Common Russian typography: a visitor may type е for source ё.
                # Inject a synthetic title into the existing card only for this
                # interaction; the visible source title and stable series stay intact.
                russian = page.locator('.card[data-edition="ru.wikipedia"]')
                russian.evaluate("(card) => { card.dataset.title = 'Чёрная дыра'; }")
                page.locator("#atlas-query").fill("черная_дыра")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator(".card:visible")).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                assert page.locator("#atlas-filter-link").evaluate(
                    "(a) => new URL(a.href).searchParams.get('af_query')") == "черная_дыра"
                page.locator("#atlas-query").fill("черная дыра")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator(".card:visible")).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                assert page.locator("#atlas-filter-link").evaluate(
                    "(a) => new URL(a.href).searchParams.get('af_query')") == "черная дыра"
                expect(page.locator(".card:visible h3")).to_have_text("Шахматы")
                page.locator("#atlas-query").fill("")
                russian.evaluate("(card) => { card.dataset.title = 'Шахматы'; }")
                expect(page.locator(".card:visible")).to_have_count(2)
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(2)
                # A pasted observed current page ID selects only its exact title.
                # Do not turn that ID into proof of historical pageview continuity.
                page.locator("#atlas-query").fill("id:5678")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator(".card:visible")).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                assert page.locator("#atlas-filter-link").evaluate(
                    "(a) => new URL(a.href).searchParams.get('af_query')") == "id:5678"
                page.locator("#atlas-edition").select_option("en.wikipedia")
                expect(page.locator(".card:visible")).to_have_count(0)
                page.locator("#atlas-edition").select_option("all")
                expect(page.locator(".card:visible")).to_have_count(1)
                for bad_id in ("id:05678", "id:567", "id:99999999999999999", "id:"):
                    page.locator("#atlas-query").fill(bad_id)
                    expect(page.locator(".card:visible")).to_have_count(0)
                    expect(page.locator("#atlas-empty")).to_be_visible()
                page.locator("#atlas-query").fill("")
                expect(page.locator(".card:visible")).to_have_count(2)
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(2)
                # Pairwise comparison reuses the existing exact weekly rows;
                # no-JS visitors still have the full accessible comparison.
                expect(page.locator("#pair-form")).to_be_visible()
                expect(page.locator("#pair-output")).to_be_hidden()
                expect(page.locator("#pair-changes")).to_be_hidden()
                expect(page.locator("#pair-share")).to_be_hidden()
                expect(page.locator("#pair-csv")).to_be_hidden()
                expect(page.locator("#pair-change-csv")).to_be_hidden()
                # From discovery, a keyboard-activated card link selects that
                # exact title and focuses the second selector.
                shortcut = page.locator(".card-pair").first
                assert shortcut.evaluate("el => el.getBoundingClientRect().height") >= 44
                shortcut.focus()
                page.keyboard.press("Enter")
                expect(page.locator("#pair-left")).to_have_value("detail-en-wikipedia-1234")
                expect(page.locator("#pair-right")).to_be_focused()
                assert page.evaluate("location.hash") == "#pair-compare"
                expect(page.locator("#pair-output")).to_be_hidden()
                # The exact detail-to-comparison action shares the same safe
                # selector behavior: it preserves this title, then focuses the
                # explicitly chosen second history (no inferred equivalence).
                detail_shortcut = page.locator("#detail-en-wikipedia-1234 .detail-pair")
                assert detail_shortcut.evaluate(
                    "el => el.getBoundingClientRect().height") >= 44
                detail_shortcut.focus()
                page.keyboard.press("Enter")
                expect(page.locator("#pair-left")).to_have_value("detail-en-wikipedia-1234")
                expect(page.locator("#pair-right")).to_be_focused()
                assert page.evaluate("location.hash") == "#pair-compare"
                # Changing the first title to the currently selected second
                # never leaves an invalid or silently substituted pair.
                page.locator("#pair-right").select_option("detail-ru-wikipedia-5678")
                page.locator(".card-pair").last.click()
                expect(page.locator("#pair-left")).to_have_value("detail-ru-wikipedia-5678")
                expect(page.locator("#pair-right")).to_have_value("")
                expect(page.locator("#pair-output")).to_be_hidden()
                page.locator("#pair-left").select_option("detail-en-wikipedia-1234")
                page.locator("#pair-right").select_option("detail-ru-wikipedia-5678")
                expect(page.locator("#pair-output")).to_be_visible()
                expect(page.locator("#pair-compare")).to_contain_text("scroll sideways or focus it")
                assert page.locator("#pair-form button[type=reset]").evaluate(
                    "button => button.getBoundingClientRect().height") >= 44
                expect(page.locator("#pair-table tbody tr")).to_have_count(2)
                # Pair clones must not duplicate native weekly-row fragment IDs.
                expect(page.locator("#pair-table tbody tr[id]")).to_have_count(0)
                expect(page.locator("#compare-detail-en-wikipedia-1234")).to_have_count(1)
                expect(page.locator("#compare-detail-ru-wikipedia-5678")).to_have_count(1)
                expect(page.locator("#pair-table thead th")).to_have_count(7)
                expect(page.locator("#pair-table tbody tr").first).to_contain_text("Chess")
                expect(page.locator("#pair-table tbody tr").last).to_contain_text("Шахматы")
                # Five aligned weeks: the first has no predecessor; the second
                # is +49 requests for Chess and exactly 0 for flat RU evidence.
                expect(page.locator("#pair-changes")).to_be_visible()
                expect(page.locator("#pair-changes-table tbody tr")).to_have_count(5)
                assert page.locator("#pair-changes-table tbody tr").first.locator(
                    "td").all_text_contents() == ["—", "—"]
                assert page.locator("#pair-changes-table tbody tr").nth(1).locator(
                    "td").all_text_contents() == ["+49", "0"]
                assert page.locator("#pair-changes-table tbody tr").nth(4).locator(
                    "td").all_text_contents() == ["+49", "0"]
                expect(page.locator("#pair-changes-table thead")).to_contain_text("Chess")
                expect(page.locator("#pair-changes-table thead")).to_contain_text("Шахматы")
                # Two exact 35-day curves use the same zero and shared peak,
                # not independent normalizations that exaggerate differences.
                expect(page.locator("#pair-daily-charts")).to_be_visible()
                expect(page.locator("#pair-daily-charts figure")).to_have_count(2)
                expect(page.locator("#pair-daily-charts svg[role=img]")).to_have_count(2)
                expect(page.locator("#pair-daily-charts")).to_contain_text(
                    "SAME zero-origin scale (0 to 35 requests)")
                assert page.locator(".pair-daily-line").first.get_attribute(
                    "points").split(" ").__len__() == 35
                assert page.locator(".pair-daily-line").last.get_attribute(
                    "points").split(" ")[0].endswith(",108")
                assert page.locator(".pair-zero-axis").first.get_attribute("y1") == "108"
                assert page.locator(".pair-zero-axis").last.get_attribute("y1") == "108"
                # A corrupted retained daily row cannot produce a persuasive
                # but false comparison curve, even if weekly cells look valid.
                daily_cell = page.locator(
                    "#detail-en-wikipedia-1234 .scroll table tbody tr").first.locator("td")
                preserved_daily = daily_cell.text_content()
                daily_cell.evaluate("el => el.textContent = 'not-a-count'")
                page.locator("#pair-right").select_option("")
                page.locator("#pair-right").select_option("detail-ru-wikipedia-5678")
                # Corrupt evidence invalidates the entire selected pair,
                # not just its charts. No share or exports may remain visible.
                expect(page.locator("#pair-status")).to_contain_text(
                    "exact daily and weekly evidence did not reconcile")
                expect(page.locator("#pair-output")).to_be_hidden()
                expect(page.locator("#pair-share")).to_be_hidden()
                expect(page.locator("#pair-csv")).to_be_hidden()
                expect(page.locator("#pair-change-csv")).to_be_hidden()
                expect(page.locator("#pair-daily-csv")).to_be_hidden()
                expect(page.locator("#pair-daily-charts")).to_be_hidden()
                expect(page.locator("#pair-daily-charts figure")).to_have_count(0)
                expect(page.locator(".pair-daily-line")).to_have_count(0)
                expect(page.locator("#pair-table tbody tr")).to_have_count(0)
                expect(page.locator("#pair-changes")).to_be_hidden()
                expect(page.locator("#pair-changes-table tbody tr")).to_have_count(0)
                # The two independent 35-day evidence tables stay inspectable,
                # including the damaged value; never invent replacement counts.
                expect(page.locator(
                    "#detail-en-wikipedia-1234 .scroll table tbody tr")).to_have_count(35)
                expect(page.locator(
                    "#detail-ru-wikipedia-5678 .scroll table tbody tr")).to_have_count(35)
                expect(daily_cell.first).to_have_text("not-a-count")
                daily_cell.evaluate("(el, value) => el.textContent = value",
                                    preserved_daily)
                page.locator("#pair-right").select_option("")
                page.locator("#pair-right").select_option("detail-ru-wikipedia-5678")
                # Restoring the original value fully re-enables valid comparison,
                # both exports and the dataset-bound share action.
                expect(page.locator("#pair-output")).to_be_visible()
                expect(page.locator("#pair-share")).to_be_visible()
                expect(page.locator("#pair-csv")).to_be_visible()
                expect(page.locator("#pair-change-csv")).to_be_visible()
                expect(page.locator("#pair-daily-csv")).to_be_visible()
                expect(page.locator("#pair-table tbody tr")).to_have_count(2)
                expect(page.locator("#pair-changes-table tbody tr")).to_have_count(5)
                expect(page.locator(".pair-daily-line")).to_have_count(2)
                expect(page.locator("#pair-status")).to_contain_text("does not establish")
                pair_url = page.locator("#pair-share").get_attribute("href")
                assert "af_left=detail-en-wikipedia-1234" in pair_url
                assert "af_right=detail-ru-wikipedia-5678" in pair_url
                assert "af_dataset=" in pair_url and pair_url.endswith("#pair-compare")
                pair_export = page.get_by_role("button", name="Download selected pair CSV")
                expect(pair_export).to_be_visible()
                assert pair_export.evaluate("el => el.getBoundingClientRect().height") >= 44
                with page.expect_download() as pair_download:
                    pair_export.click()
                assert pair_download.value.suggested_filename.startswith("dayflare-pair-")
                with Path(pair_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    pair_csv = list(csv.reader(handle))
                assert len(pair_csv) == 3, pair_csv
                assert pair_csv[1][3] == "detail-en-wikipedia-1234"
                assert pair_csv[2][3] == "detail-ru-wikipedia-5678"
                assert pair_csv[1][7:12] == ["28", "77", "126", "175", "224"]
                assert pair_csv[1][12] == "+122.5"
                assert pair_csv[2][7:12] == ["0"] * 5
                assert pair_csv[1][0] == page.locator("#share-restore").get_attribute("data-dataset")
                assert pair_csv[1][1] == page.locator("#share-restore").get_attribute("data-method")
                # Separate additive schema; week 1 is unavailable, not zero.
                change_export = page.get_by_role("button", name="Download pair weekly changes CSV")
                expect(change_export).to_be_visible()
                assert change_export.evaluate("el => el.getBoundingClientRect().height") >= 44
                change_export.focus()
                with page.expect_download() as change_download:
                    page.keyboard.press("Enter")
                assert change_download.value.suggested_filename.startswith(
                    "dayflare-pair-week-changes-")
                with Path(change_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    change_csv = list(csv.reader(handle))
                assert len(change_csv) == 11, len(change_csv)
                assert change_csv[0] == [
                    "dataset_sha256", "method_version", "observation_end_utc",
                    "snapshot_series_key", "edition", "title", "subject",
                    "utc_week_start", "utc_week_end", "weekly_requests",
                    "change_from_prior_week_requests"
                ]
                assert [r[10] for r in change_csv[1:6]] == ["", "+49", "+49", "+49", "+49"]
                assert [r[10] for r in change_csv[6:]] == ["", "0", "0", "0", "0"]
                assert [r[9] for r in change_csv[1:6]] == ["28", "77", "126", "175", "224"]
                assert [r[9] for r in change_csv[6:]] == ["0"] * 5
                assert change_csv[1][3] == "detail-en-wikipedia-1234"
                assert change_csv[6][3] == "detail-ru-wikipedia-5678"
                assert change_csv[1][0] == pair_csv[1][0]
                assert change_csv[1][1:3] == pair_csv[1][1:3]
                expect(page.locator("#pair-change-csv-status")).to_contain_text(
                    "2 titles and 5 complete UTC weeks")
                page.set_viewport_size({"width": 320, "height": 700})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                change_export.scroll_into_view_if_needed()
                page.screenshot(path=str(SHOTS / "m1-rolling-pair-change-export-320.png"),
                                animations="disabled")
                page.set_viewport_size({"width": 390, "height": 844})
                daily_export = page.get_by_role("button", name="Download selected pair daily CSV")
                expect(daily_export).to_be_visible()
                assert daily_export.evaluate("el => el.getBoundingClientRect().height") >= 44
                with page.expect_download() as daily_download:
                    daily_export.click()
                assert daily_download.value.suggested_filename.startswith("dayflare-pair-daily-")
                with Path(daily_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    daily_csv = list(csv.reader(handle))
                assert len(daily_csv) == 71, len(daily_csv)
                assert daily_csv[0] == [
                    "dataset_sha256", "method_version", "observation_end_utc",
                    "snapshot_series_key", "edition", "title", "subject",
                    "utc_date", "daily_requests"
                ]
                assert daily_csv[1][3] == "detail-en-wikipedia-1234"
                assert daily_csv[1][7:] == ["2026-09-17", "1"]
                assert daily_csv[35][7:] == ["2026-10-21", "35"]
                assert daily_csv[36][3] == "detail-ru-wikipedia-5678"
                assert daily_csv[36][7:] == ["2026-09-17", "0"]
                assert daily_csv[70][7:] == ["2026-10-21", "0"]
                visible_daily = page.get_by_role("button", name="Download visible daily CSV")
                expect(visible_daily).to_be_visible()
                expect(visible_daily).to_be_enabled()
                assert visible_daily.evaluate("el => el.getBoundingClientRect().height") >= 44
                with page.expect_download() as visible_download:
                    visible_daily.click()
                assert visible_download.value.suggested_filename.startswith("dayflare-visible-daily-")
                with Path(visible_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    visible_rows = list(csv.reader(handle))
                assert visible_rows == daily_csv, (len(visible_rows), len(daily_csv))
                expect(page.locator("#compare-daily-csv-status")).to_contain_text(
                    "2 visible title histories")
                # New additive export keeps the existing weekly CSV unchanged;
                # exact signed steps are one row per UTC week and filtered title.
                visible_changes = page.get_by_role(
                    "button", name="Download visible weekly changes CSV")
                expect(visible_changes).to_be_visible()
                expect(visible_changes).to_be_enabled()
                assert visible_changes.evaluate(
                    "el => el.getBoundingClientRect().height") >= 44
                visible_changes.focus()
                with page.expect_download() as all_changes_download:
                    page.keyboard.press("Enter")
                with Path(all_changes_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    all_changes = list(csv.reader(handle))
                assert all_changes == change_csv, (len(all_changes), len(change_csv))
                expect(page.locator("#compare-week-changes-csv-status")).to_contain_text(
                    "2 visible title histories")
                # The five visible UTC column dates are part of the source
                # evidence, not editable metadata to trust during CSV export.
                # All four weekly/pair CSV actions must fail closed if a date
                # is shifted, repeated or reordered while counts stay intact.
                for header_index, field, wrong_date in [
                    (0, "weekStart", "2026-09-18"),
                    (1, "weekEnd", "2026-10-01"),
                    (2, "weekStart", "2026-09-24"),
                    (4, "weekEnd", "2026-10-20"),
                ]:
                    made = page.evaluate("""({headerIndex, field, wrongDate}) => {
                        const header = document.querySelectorAll(
                            "#compare-table thead th[data-week-start]")[headerIndex];
                        const previous = header.dataset[field];
                        const realCreate = URL.createObjectURL;
                        let created = 0;
                        URL.createObjectURL = function(...args) {
                            created++;
                            return realCreate.apply(this, args);
                        };
                        try {
                            header.dataset[field] = wrongDate;
                            for (const id of [
                                "compare-csv", "compare-week-changes-csv",
                                "pair-csv", "pair-change-csv"
                            ]) document.getElementById(id).click();
                            return created;
                        } finally {
                            header.dataset[field] = previous;
                            URL.createObjectURL = realCreate;
                        }
                    }""", {"headerIndex": header_index, "field": field,
                           "wrongDate": wrong_date})
                    assert made == 0, "invalid UTC week label generated a CSV"
                    expect(page.locator("#compare-csv-status")).to_contain_text("unavailable")
                    expect(page.locator("#compare-week-changes-csv-status")).to_contain_text(
                        "unavailable")
                    expect(page.locator("#pair-csv-status")).to_contain_text("unavailable")
                    expect(page.locator("#pair-change-csv-status")).to_contain_text(
                        "unavailable")
                # Returning to the original dated headers restores exact export.
                with page.expect_download() as restored_changes_download:
                    visible_changes.click()
                with Path(restored_changes_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    assert list(csv.reader(handle)) == all_changes
                # A single filtered history retains the exact 5-week sequence,
                # including unavailable (blank) first change, never zero.
                page.locator("#atlas-query").fill("Шахматы")
                expect(page.locator(".card:visible")).to_have_count(1)
                with page.expect_download() as one_change_download:
                    visible_changes.click()
                with Path(one_change_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    one_changes = list(csv.reader(handle))
                assert len(one_changes) == 6
                assert one_changes[0] == change_csv[0]
                assert one_changes[1:] == change_csv[6:]
                assert one_changes[1][-1] == ""
                page.locator("#atlas-query").fill("no_matching_selected_title_98765")
                expect(visible_changes).to_be_disabled()
                page.locator("#atlas-query").fill("")

                # Export one title without having to select a second topic.
                single = page.locator("#detail-en-wikipedia-1234 .detail-daily-csv")
                expect(single).to_be_visible()
                assert single.evaluate("el => el.getBoundingClientRect().height") >= 44
                with page.expect_download() as single_download:
                    single.click()
                assert single_download.value.suggested_filename.startswith("dayflare-title-daily-")
                with Path(single_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    single_csv = list(csv.reader(handle))
                assert len(single_csv) == 36
                assert single_csv[0] == daily_csv[0]
                assert single_csv[1:] == daily_csv[1:36]
                expect(page.locator("#detail-en-wikipedia-1234 .detail-daily-csv-status")).to_contain_text("35 exact")
                # Preserve real rendered mobile and desktop evidence of this new
                # visitor action before the negative controls change the status.
                for detail_width in (320, 390, 1280):
                    page.set_viewport_size({"width": detail_width, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    single.scroll_into_view_if_needed()
                    page.screenshot(path=str(SHOTS / f"m1-rolling-single-title-{detail_width}.png"),
                                    animations="disabled")
                page.set_viewport_size({"width": 390, "height": 844})
                # Actual zero readings are not treated as missing.
                other = page.locator("#detail-ru-wikipedia-5678 .detail-daily-csv")
                other.focus()
                with page.expect_download() as other_download:
                    page.keyboard.press("Enter")
                with Path(other_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    assert list(csv.reader(handle))[1:] == daily_csv[36:]
                single.evaluate("""el => {
                    const original = el.dataset.series;
                    el.dataset.series = 'detail-ru-wikipedia-5678';
                    el.click();
                    el.dataset.series = original;
                }""")
                expect(page.locator("#detail-en-wikipedia-1234 .detail-daily-csv-status")).to_contain_text("unavailable")
                daily_source = page.locator("#detail-en-wikipedia-1234 .scroll table tbody tr")
                assert daily_source.count() == 35
                daily_source.first.locator("td").evaluate("""el => {
                    const original = el.textContent;
                    el.textContent = 'missing';
                    document.querySelector('#pair-daily-csv').click();
                    document.querySelector('#compare-daily-csv').click();
                    el.textContent = original;
                }""")
                expect(page.locator("#pair-daily-csv-status")).to_contain_text("unavailable")
                expect(page.locator("#compare-daily-csv-status")).to_contain_text("unavailable")
                daily_source.first.locator("td").evaluate("""el => {
                    const original = el.textContent;
                    el.textContent = 'missing';
                    document.querySelector('#detail-en-wikipedia-1234 .detail-daily-csv').click();
                    el.textContent = original;
                }""")
                expect(page.locator("#detail-en-wikipedia-1234 .detail-daily-csv-status")).to_contain_text("unavailable")
                daily_source.first.locator("th").evaluate("""el => {
                    const original = el.textContent;
                    el.textContent = '2026-09-18';
                    document.querySelector('#pair-daily-csv').click();
                    el.textContent = original;
                }""")
                expect(page.locator("#pair-daily-csv-status")).to_contain_text("unavailable")
                # Chosen pair remains available regardless of discovery filters.
                page.locator("#atlas-query").fill("nothing matches")
                expect(page.locator(".card:visible")).to_have_count(0)
                expect(visible_daily).to_be_disabled()
                expect(pair_export).to_be_visible()
                expect(change_export).to_be_visible()
                expect(daily_export).to_be_visible()
                with page.expect_download() as filtered_daily_download:
                    daily_export.click()
                with Path(filtered_daily_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    assert list(csv.reader(handle)) == daily_csv
                with page.expect_download() as filtered_change_download:
                    change_export.click()
                with Path(filtered_change_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    assert list(csv.reader(handle)) == change_csv
                with page.expect_download() as filtered_pair_download:
                    pair_export.click()
                with Path(filtered_pair_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    assert list(csv.reader(handle)) == pair_csv
                page.locator("#atlas-query").fill("")
                page.locator("#atlas-query").fill("Шахматы")
                expect(visible_daily).to_be_enabled()
                with page.expect_download() as one_visible_download:
                    visible_daily.focus()
                    page.keyboard.press("Enter")
                with Path(one_visible_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    one_visible = list(csv.reader(handle))
                assert len(one_visible) == 36
                assert one_visible[0] == daily_csv[0]
                assert one_visible[1:] == daily_csv[36:]
                # A different valid row ID with the same visible-row count
                # must never produce an export for a hidden topic.
                blob_creations = page.evaluate("""() => {
                    const rows = [...document.querySelectorAll('#compare-table tbody tr')];
                    const shown = rows.find(row => !row.hidden);
                    const hidden = rows.find(row => row.hidden);
                    if (!shown || !hidden) throw new Error('fixture requires two rows');
                    const original = URL.createObjectURL;
                    let created = 0;
                    URL.createObjectURL = function(...args) {
                        created++;
                        return original.apply(this, args);
                    };
                    try {
                        shown.hidden = true;
                        hidden.hidden = false;
                        document.querySelector('#compare-daily-csv').click();
                        return created;
                    } finally {
                        URL.createObjectURL = original;
                        shown.hidden = false;
                        hidden.hidden = true;
                    }
                }""")
                assert blob_creations == 0, "wrong visible-series export created a Blob"
                expect(page.locator("#compare-daily-csv-status")).to_contain_text("unavailable")
                page.locator("#atlas-query").fill("")

                # Changed source evidence must never produce a plausible delta CSV.
                change_creations = page.evaluate("""() => {
                    const cell = document.querySelector(
                        '#detail-en-wikipedia-1234 .scroll table tbody tr td');
                    const original = cell.textContent;
                    const before = URL.createObjectURL;
                    let created = 0;
                    URL.createObjectURL = function(...args) {
                        created++;
                        return before.apply(this, args);
                    };
                    try {
                        cell.textContent = 'not-source-evidence';
                        document.querySelector('#pair-change-csv').click();
                        return created;
                    } finally {
                        cell.textContent = original;
                        URL.createObjectURL = before;
                    }
                }""")
                assert change_creations == 0, "bad source evidence generated weekly changes"
                expect(page.locator("#pair-change-csv-status")).to_contain_text("unavailable")
                # Malformed values must never become a downloadable CSV.
                pair_cell = page.locator("#pair-table tbody tr").first.locator("td").first
                # The pair view can be rebuilt after filter changes. Mutate the
                # displayed cell and dispatch its export synchronously in the same
                # renderer task so an earlier UI refresh cannot replace the row.
                pair_cell.evaluate("""el => {
                    const exact = el.textContent;
                    el.textContent = 'not-an-integer';
                    document.querySelector('#pair-csv').click();
                    el.textContent = exact;
                }""")
                expect(page.locator("#pair-csv-status")).to_contain_text("unavailable")
                for mobile_width in (320, 390, 1280):
                    page.set_viewport_size({"width": mobile_width, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                        "pair selector overflow at " + str(mobile_width))
                    assert single.evaluate("el => el.getBoundingClientRect().height") >= 44
                    page.locator("#pair-compare").screenshot(
                        path=str(SHOTS / f"m1-rolling-pair-{mobile_width}.png"),
                        animations="disabled")
                restored = browser.new_page(viewport={"width": 390, "height": 844},
                                            java_script_enabled=True)
                restored.goto(pair_url, wait_until="domcontentloaded")
                expect(restored.locator("#pair-left")).to_have_value("detail-en-wikipedia-1234")
                expect(restored.locator("#pair-right")).to_have_value("detail-ru-wikipedia-5678")
                expect(restored.locator("#pair-table tbody tr")).to_have_count(2)
                expect(restored.locator("#pair-changes-table tbody tr")).to_have_count(5)
                expect(restored.locator(".pair-daily-line")).to_have_count(2)
                # Wrong/duplicate IDs and incompatible dataset must not silently
                # substitute an arbitrary pair in a shared comparison.
                for invalid in (
                    pair_url.replace("af_right=detail-ru-wikipedia-5678",
                                     "af_right=detail-en-wikipedia-1234"),
                    pair_url.replace("af_right=detail-ru-wikipedia-5678",
                                     "af_right=detail-ru-wikipedia-999999"),
                    pair_url.replace("af_dataset=", "af_dataset=invalid-"),
                ):
                    restored.goto(invalid, wait_until="domcontentloaded")
                    expect(restored.locator("#atlas-filter-warning")).to_be_visible()
                    expect(restored.locator("#pair-output")).to_be_hidden()
                    expect(restored.locator("#pair-changes")).to_be_hidden()
                    expect(restored.locator("#pair-daily-charts")).to_be_hidden()
                    expect(restored.locator("#pair-csv")).to_be_hidden()
                restored.close()
                page.locator("#pair-right").select_option("detail-en-wikipedia-1234")
                expect(page.locator("#pair-status")).to_contain_text("two different")
                expect(page.locator("#pair-output")).to_be_hidden()
                expect(pair_export).to_be_hidden()
                expect(daily_export).to_be_hidden()
                page.locator("#pair-form button[type=reset]").click()
                expect(page.locator("#pair-output")).to_be_hidden()
                expect(pair_export).to_be_hidden()
                expect(daily_export).to_be_hidden()
                page.set_viewport_size({"width": 390, "height": 844})
                # Native <select> hides part of long values on narrow phones even
                # when the page itself has no horizontal overflow. Measure the
                # currently selected text, allowing room for the platform arrow.
                for viewport_width in (390, 320):
                    page.set_viewport_size({"width": viewport_width, "height": 844})
                    for order_mode in ("editorial", "volume", "daily-rise", "increase", "decrease",
                                       "step-rise", "step-fall", "relative-increase", "relative-decrease"):
                        page.locator("#atlas-order").select_option(order_mode)
                        metrics = page.locator("#atlas-order").evaluate("""select => {
                            const style = getComputedStyle(select);
                            const context = document.createElement("canvas").getContext("2d");
                            context.font = [style.fontStyle, style.fontWeight,
                                            style.fontSize, style.fontFamily].join(" ");
                            const option = select.selectedOptions[0].textContent;
                            return {
                                option,
                                measured: context.measureText(option).width,
                                available: select.clientWidth -
                                           parseFloat(style.paddingLeft) -
                                           parseFloat(style.paddingRight) - 28
                            };
                        }""")
                        assert metrics["measured"] <= metrics["available"], (
                            f"Sort option clipped at {viewport_width}px: {metrics}")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator("#atlas-order").select_option("editorial")
                export_button = page.get_by_role("button", name="Download visible weekly CSV")
                expect(export_button).to_be_visible()
                expect(export_button).to_be_enabled()
                with page.expect_download() as all_export:
                    export_button.click()
                all_file = all_export.value
                assert all_file.suggested_filename.startswith("dayflare-weekly-")
                assert all_file.suggested_filename.endswith(".csv")
                with Path(all_file.path()).open("r", encoding="utf-8-sig", newline="") as handle:
                    all_rows = list(csv.reader(handle))
                assert len(all_rows) == 3, all_rows
                assert all_rows[0][7] == "2026-09-17_to_2026-09-23_requests"
                assert all_rows[0][11] == "2026-10-15_to_2026-10-21_requests"
                assert all_rows[1][7:12] == ["28", "77", "126", "175", "224"]
                assert all_rows[1][12] == "+122.5", all_rows[1]
                assert all_rows[1][5].startswith("Chess & <svg onload=")
                assert all_rows[2][7:12] == ["0"] * 5
                assert all_rows[1][0] == page.locator("#share-restore").get_attribute("data-dataset")
                assert all_rows[1][2] == "2026-10-21"
                # Volume is the final complete seven-day request total, not
                # absolute change or a ranking of all Wikipedia.
                volume_select = page.locator("#atlas-order")
                volume_select.focus()
                volume_select.select_option("volume")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                expect(page.locator("#compare-table tbody tr").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                assert page.locator(".cards > .card").first.get_attribute("data-last-week") == "224"
                with page.expect_download() as volume_export:
                    export_button.click()
                with Path(volume_export.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    volume_rows = list(csv.reader(handle))
                assert [r[4] for r in volume_rows[1:]] == [
                    "en.wikipedia", "ru.wikipedia"]
                assert [r[11] for r in volume_rows[1:]] == ["224", "0"]
                volume_link = page.locator("#atlas-filter-link").get_attribute("href")
                assert "af_sort=volume" in volume_link
                page.goto(volume_link, wait_until="domcontentloaded")
                expect(page.locator("#atlas-filter-warning")).to_be_hidden()
                expect(page.locator("#atlas-order")).to_have_value("volume")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                # Synthetic DOM-only adversarial values: exact comparison must
                # distinguish adjacent totals beyond Number.MAX_SAFE_INTEGER.
                # Restore both after assertions; never export injected totals.
                ru_volume = page.locator('.card[data-series="detail-ru-wikipedia-5678"]')
                en_volume = page.locator('.card[data-series="detail-en-wikipedia-1234"]')
                ru_volume.evaluate('(el) => el.dataset.lastWeek = "9007199254740993"')
                en_volume.evaluate('(el) => el.dataset.lastWeek = "9007199254740992"')
                volume_select.select_option("editorial")
                volume_select.select_option("volume")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                expect(page.locator("#compare-table tbody tr").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                en_volume.evaluate('(el) => el.dataset.lastWeek = "9007199254740993"')
                volume_select.select_option("editorial")
                volume_select.select_option("volume")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                ru_volume.evaluate('(el) => el.dataset.lastWeek = "0"')
                en_volume.evaluate('(el) => el.dataset.lastWeek = "224"')
                volume_select.select_option("editorial")
                volume_select.select_option("volume")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                # Week-to-week order must use the separate signed exact
                # latest-versus-prior-week delta, not the four-week median.
                step_select = page.locator("#atlas-order")
                expect(page.locator('.card[data-series="detail-en-wikipedia-1234"]')).to_have_attribute(
                    "data-week-step", "49")
                expect(page.locator('.card[data-series="detail-ru-wikipedia-5678"]')).to_have_attribute(
                    "data-week-step", "0")
                step_select.select_option("step-fall")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                expect(page.locator("#compare-table tbody tr").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                with page.expect_download() as step_export:
                    export_button.click()
                with Path(step_export.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    step_csv = list(csv.reader(handle))
                assert [r[4] for r in step_csv[1:]] == [
                    "ru.wikipedia", "en.wikipedia"]
                step_link = page.locator("#atlas-filter-link").get_attribute("href")
                assert "af_sort=step-fall" in step_link
                page.goto(step_link, wait_until="domcontentloaded")
                expect(page.locator("#atlas-filter-warning")).to_be_hidden()
                expect(page.locator("#atlas-order")).to_have_value("step-fall")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                step_select.select_option("step-rise")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                # >2^53 and negative synthetic DOM-only steps: BigInt and
                # stable editorial ties, never export mutated data.
                ru_step = page.locator('.card[data-series="detail-ru-wikipedia-5678"]')
                en_step = page.locator('.card[data-series="detail-en-wikipedia-1234"]')
                ru_step.evaluate('(el) => el.dataset.weekStep = "9007199254740993"')
                en_step.evaluate('(el) => el.dataset.weekStep = "9007199254740992"')
                step_select.select_option("editorial")
                step_select.select_option("step-rise")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                en_step.evaluate('(el) => el.dataset.weekStep = "9007199254740993"')
                step_select.select_option("editorial")
                step_select.select_option("step-rise")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                ru_step.evaluate('(el) => el.dataset.weekStep = "-9007199254740993"')
                en_step.evaluate('(el) => el.dataset.weekStep = "-9007199254740992"')
                step_select.select_option("step-fall")
                expect(page.locator("#compare-table tbody tr").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                ru_step.evaluate('(el) => el.dataset.weekStep = "0"')
                en_step.evaluate('(el) => el.dataset.weekStep = "49"')
                step_select.select_option("editorial")
                # Largest positive adjacent UTC-day rise is distinct from
                # last-week volume and four-week-median change.
                daily_select = page.locator("#atlas-order")
                daily_select.select_option("daily-rise")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                expect(page.locator("#compare-table tbody tr").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                with page.expect_download() as daily_rise_export:
                    export_button.click()
                with Path(daily_rise_export.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    daily_rise_csv = list(csv.reader(handle))
                assert [r[4] for r in daily_rise_csv[1:]] == [
                    "en.wikipedia", "ru.wikipedia"]
                daily_rise_link = page.locator("#atlas-filter-link").get_attribute("href")
                assert "af_sort=daily-rise" in daily_rise_link
                page.goto(daily_rise_link, wait_until="domcontentloaded")
                expect(page.locator("#atlas-filter-warning")).to_be_hidden()
                expect(page.locator("#atlas-order")).to_have_value("daily-rise")
                ru_rise = page.locator('.card[data-series="detail-ru-wikipedia-5678"]')
                en_rise = page.locator('.card[data-series="detail-en-wikipedia-1234"]')
                # Adversarial DOM-only integer comparison beyond JS safe Number.
                ru_rise.evaluate('(el) => el.dataset.dailyRise = "9007199254740993"')
                en_rise.evaluate('(el) => el.dataset.dailyRise = "9007199254740992"')
                daily_select.select_option("editorial")
                daily_select.select_option("daily-rise")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                expect(page.locator("#compare-table tbody tr").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                en_rise.evaluate('(el) => el.dataset.dailyRise = "9007199254740993"')
                daily_select.select_option("editorial")
                daily_select.select_option("daily-rise")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                ru_rise.evaluate('(el) => el.dataset.dailyRise = "0"')
                en_rise.evaluate('(el) => el.dataset.dailyRise = "1"')
                daily_select.select_option("editorial")
                daily_select.select_option("daily-rise")
                # Restore exact fixture values before any later CSV operations.
                # Reorder cards, exact table and downloaded CSV consistently.
                page.locator("#atlas-order").select_option("decrease")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                expect(page.locator("#compare-table tbody tr").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                with page.expect_download() as sorted_export:
                    export_button.click()
                with Path(sorted_export.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    ordered_csv = list(csv.reader(handle))
                assert ordered_csv[1][4] == "ru.wikipedia"
                page.locator("#atlas-order").select_option("increase")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                expect(page.locator("#compare-table tbody tr").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                # Relative ranking is exact signed delta / preceding median.
                # Real zero baseline is unavailable (last) in both directions.
                order_select = page.locator("#atlas-order")
                order_select.select_option("relative-increase")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                order_select.select_option("relative-decrease")
                expect(page.locator("#compare-table tbody tr").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                ru_card = page.locator('.card[data-series="detail-ru-wikipedia-5678"]')
                en_card = page.locator('.card[data-series="detail-en-wikipedia-1234"]')
                # Synthetic unequal fractional ratios, without touching sources.
                # 1/3 > 2/9, even though the absolute change is smaller.
                ru_card.evaluate('(el) => { el.dataset.delta2="1"; el.dataset.baseline2="3" }')
                en_card.evaluate('(el) => { el.dataset.delta2="2"; el.dataset.baseline2="9" }')
                order_select.select_option("relative-increase")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                expect(page.locator("#compare-table tbody tr").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                order_select.select_option("relative-decrease")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                # Exact integer cross-product beyond JavaScript Number precision.
                ru_card.evaluate('(el) => { el.dataset.delta2="2"; el.dataset.baseline2="9007199254740993" }')
                en_card.evaluate('(el) => { el.dataset.delta2="2"; el.dataset.baseline2="9007199254740992" }')
                order_select.select_option("relative-increase")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                ru_card.evaluate('(el) => { el.dataset.delta2="0"; el.dataset.baseline2="0" }')
                en_card.evaluate('(el) => { el.dataset.delta2="245"; el.dataset.baseline2="203" }')
                relative_link = page.locator("#atlas-filter-link").get_attribute("href")
                assert "af_sort=relative-increase" in relative_link
                page.goto(relative_link, wait_until="domcontentloaded")
                expect(page.locator("#atlas-order")).to_have_value("relative-increase")
                expect(page.locator("#atlas-filter-warning")).to_be_hidden()
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-en-wikipedia-1234")
                order_select.select_option("editorial")
                # Adjacent integers beyond Number.MAX_SAFE_INTEGER must remain distinct.
                ru_card.evaluate('(el) => el.dataset.delta2 = "9007199254740993"')
                en_card.evaluate('(el) => el.dataset.delta2 = "9007199254740992"')
                page.locator("#atlas-order").select_option("editorial")
                page.locator("#atlas-order").select_option("increase")
                expect(page.locator(".cards > .card").first).to_have_attribute(
                    "data-series", "detail-ru-wikipedia-5678")
                ru_card.evaluate('(el) => el.dataset.delta2 = "0"')
                en_card.evaluate('(el) => el.dataset.delta2 = "245"')
                page.locator("#atlas-order").select_option("editorial")
                # Independent latest-vs-prior-week direction uses exact signed
                # BigInt, not the four-week-median sign or lifecycle labels.
                step_direction = page.locator("#atlas-step-direction")
                expect(step_direction).to_have_value("all")
                step_direction.select_option("positive")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator('.card[data-series="detail-en-wikipedia-1234"]')).to_be_visible()
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                with page.expect_download() as step_positive_export:
                    export_button.click()
                with Path(step_positive_export.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    step_rows = list(csv.reader(handle))
                assert len(step_rows) == 2 and step_rows[1][4] == "en.wikipedia"
                step_url = page.locator("#atlas-filter-link").get_attribute("href")
                assert "af_step=positive" in step_url
                page.goto(step_url, wait_until="domcontentloaded")
                expect(step_direction).to_have_value("positive")
                expect(page.locator("#atlas-filter-warning")).to_be_hidden()
                expect(page.locator(".card:visible")).to_have_count(1)
                step_direction.select_option("unchanged")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator('.card[data-series="detail-ru-wikipedia-5678"]')).to_be_visible()
                step_direction.select_option("negative")
                expect(page.locator(".card:visible")).to_have_count(0)
                expect(export_button).to_be_disabled()
                # A huge negative weekly step can coexist with an unchanged
                # median-baseline sign, proving the selectors are independent.
                ru_card.evaluate('(el) => el.dataset.weekStep = "-9007199254740993"')
                en_card.evaluate('(el) => el.dataset.delta2 = "-7"')
                step_direction.select_option("all")
                step_direction.select_option("negative")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator('.card[data-series="detail-ru-wikipedia-5678"]')).to_be_visible()
                page.locator("#atlas-change").select_option("positive")
                expect(page.locator(".card:visible")).to_have_count(0)
                page.get_by_role("button", name="Show all").click()
                expect(step_direction).to_have_value("all")
                expect(page.locator(".card:visible")).to_have_count(2)
                # Legacy dataset links without af_step restore all step signs;
                # invalid/duplicate parameters fail closed with visible warning.
                from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit
                parts = urlsplit(step_url)
                saved = parse_qs(parts.query, keep_blank_values=True)
                saved.pop("af_step")
                old_url = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                    urlencode(saved, doseq=True), parts.fragment))
                page.goto(old_url, wait_until="domcontentloaded")
                expect(step_direction).to_have_value("all")
                expect(page.locator("#atlas-filter-warning")).to_be_hidden()
                expect(page.locator(".card:visible")).to_have_count(2)
                old_parts = urlsplit(old_url)
                for invalid_step in ("af_step=positive&af_step=negative",
                                     "af_step=returning"):
                    invalid_url = urlunsplit((old_parts.scheme, old_parts.netloc,
                        old_parts.path, old_parts.query + "&" + invalid_step, old_parts.fragment))
                    page.goto(invalid_url, wait_until="domcontentloaded")
                    expect(page.locator("#atlas-filter-warning")).to_be_visible()
                    expect(page.locator(".card:visible")).to_have_count(2)
                page.goto(url, wait_until="domcontentloaded")
                expect(step_direction).to_have_value("all")

                # Exact measured sign, not a heuristic lifecycle classification.
                sign = page.locator("#atlas-change")
                expect(sign).to_have_value("all")
                sign.select_option("positive")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator("#atlas-results")).to_contain_text(
                    "Visible: EN 1, RU 0; weekly increases 1, decreases 0, unchanged 0")
                expect(page.locator('.card[data-series="detail-en-wikipedia-1234"]')).to_be_visible()
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                with page.expect_download() as positive_export:
                    export_button.click()
                with Path(positive_export.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    positive_rows = list(csv.reader(handle))
                assert len(positive_rows) == 2 and positive_rows[1][4] == "en.wikipedia"
                sign.select_option("unchanged")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator("#atlas-results")).to_contain_text(
                    "Visible: EN 0, RU 1; weekly increases 0, decreases 0, unchanged 1")
                expect(page.locator('.card[data-series="detail-ru-wikipedia-5678"]')).to_be_visible()
                sign.select_option("negative")
                expect(page.locator(".card:visible")).to_have_count(0)
                expect(page.locator("#atlas-results")).to_contain_text(
                    "Visible: EN 0, RU 0; weekly increases 0, decreases 0, unchanged 0")
                expect(page.locator("#compare-empty")).to_be_visible()
                expect(export_button).to_be_disabled()
                # Synthetic negative counterexample, without changing source data.
                ru_card.evaluate('(el) => el.dataset.delta2 = "-1"')
                sign.select_option("all")
                sign.select_option("negative")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator("#atlas-results")).to_contain_text(
                    "Visible: EN 0, RU 1; weekly increases 0, decreases 1, unchanged 0")
                expect(page.locator('.card[data-series="detail-ru-wikipedia-5678"]')).to_be_visible()
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                ru_card.evaluate('(el) => el.dataset.delta2 = "0"')
                sign.select_option("all")
                page.locator("#atlas-query").fill("ШАХ")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator("#atlas-results")).to_contain_text("Showing 1 of 2")
                expect(page.locator("#atlas-results")).to_contain_text(
                    "Visible: EN 0, RU 1; weekly increases 0, decreases 0, unchanged 1")
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                expect(page.locator("#compare-results")).to_contain_text("Showing 1 of 2")
                with page.expect_download() as ru_export:
                    export_button.click()
                with Path(ru_export.value.path()).open("r", encoding="utf-8-sig", newline="") as handle:
                    ru_rows = list(csv.reader(handle))
                assert len(ru_rows) == 2
                assert ru_rows[1][4:7] == ["ru.wikipedia", "Шахматы", "culture"]
                assert ru_rows[1][7:12] == ["0"] * 5
                assert ru_rows[1][12] == "0"
                page.locator("#atlas-edition").select_option("en.wikipedia")
                expect(page.locator(".card:visible")).to_have_count(0)
                expect(page.locator("#atlas-empty")).to_be_visible()
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(0)
                expect(page.locator("#compare-empty")).to_be_visible()
                expect(export_button).to_be_disabled()
                expect(page.locator("article")).to_have_count(2)
                expect(page.locator("tbody tr")).to_have_count(74)
                expect(page.locator("#atlas-results")).to_contain_text(
                    "Visible: EN 0, RU 0; weekly increases 0, decreases 0, unchanged 0")
                page.get_by_role("button", name="Show all").click()
                expect(page.locator(".card:visible")).to_have_count(2)
                expect(page.locator("#atlas-results")).to_contain_text(
                    "Visible: EN 1, RU 1; weekly increases 1, decreases 0, unchanged 1")
                expect(page.locator("#atlas-empty")).to_be_hidden()
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(2)
                expect(page.locator("#compare-empty")).to_be_hidden()
                expect(export_button).to_be_enabled()
                page.locator("#atlas-subject").select_option("sport")
                page.locator("#atlas-change").select_option("positive")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator(".card:visible h3")).to_contain_text("Chess")
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                filter_link = page.locator("#atlas-filter-link")
                expect(filter_link).to_be_visible()
                shared_url = filter_link.get_attribute("href")
                assert "af_dataset=" in shared_url and "af_subject=sport" in shared_url
                assert "af_sort=editorial" in shared_url
                assert "af_change=positive" in shared_url
                page.goto(shared_url, wait_until="domcontentloaded")
                expect(page.locator("#atlas-subject")).to_have_value("sport")
                expect(page.locator("#atlas-change")).to_have_value("positive")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator("#atlas-results")).to_contain_text(
                    "Visible: EN 1, RU 0; weekly increases 1, decreases 0, unchanged 0")
                expect(page.locator("#atlas-filter-warning")).to_be_hidden()
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                # Reject a link to any other dataset; do not apply its selected history.
                from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit
                pieces = urlsplit(shared_url)
                fields = parse_qs(pieces.query, keep_blank_values=True)
                # Pre-existing four-field dataset-bound links remain valid.
                legacy = dict(fields)
                legacy.pop("af_sort")
                legacy.pop("af_change")
                page.goto(urlunsplit((pieces.scheme, pieces.netloc, pieces.path,
                    urlencode(legacy, doseq=True), pieces.fragment)),
                    wait_until="domcontentloaded")
                expect(page.locator("#atlas-filter-warning")).to_be_hidden()
                expect(page.locator("#atlas-subject")).to_have_value("sport")
                expect(page.locator("#atlas-order")).to_have_value("editorial")
                expect(page.locator("#atlas-change")).to_have_value("all")
                fields["af_dataset"] = ["0" * 64]
                incompatible_url = urlunsplit((pieces.scheme, pieces.netloc,
                    pieces.path, urlencode(fields, doseq=True), pieces.fragment))
                page.goto(incompatible_url, wait_until="domcontentloaded")
                expect(page.locator("#atlas-filter-warning")).to_be_visible()
                expect(page.locator(".card:visible")).to_have_count(2)
                expect(page.locator("#atlas-subject")).to_have_value("all")
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(2)
                page.screenshot(path=str(SHOTS / "m1-rolling-filter-invalid-390.png"), full_page=False)
                # Duplicate and unexpected parameters are never silently accepted.
                clean_fields = parse_qs(pieces.query, keep_blank_values=True)
                clean_fields.pop("af_change", None)
                clean_query = urlencode(clean_fields, doseq=True)
                for invalid_change in ("af_change=positive&af_change=negative",
                                       "af_change=returning"):
                    page.goto(urlunsplit((pieces.scheme, pieces.netloc,
                        pieces.path, clean_query + "&" + invalid_change,
                        pieces.fragment)), wait_until="domcontentloaded")
                    expect(page.locator("#atlas-filter-warning")).to_be_visible()
                    expect(page.locator(".card:visible")).to_have_count(2)
                page.goto(urlunsplit((pieces.scheme, pieces.netloc, pieces.path,
                    pieces.query + "&af_subject=culture", pieces.fragment)),
                    wait_until="domcontentloaded")
                expect(page.locator("#atlas-filter-warning")).to_be_visible()
                expect(page.locator(".card:visible")).to_have_count(2)
                # A legitimate Russian query survives navigation and reset.
                page.locator("#atlas-query").fill("ШАХ")
                page.locator("#atlas-subject").select_option("culture")
                ru_url = page.locator("#atlas-filter-link").get_attribute("href")
                page.goto(ru_url, wait_until="domcontentloaded")
                expect(page.locator("#atlas-query")).to_have_value("ШАХ")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                page.screenshot(path=str(SHOTS / "m1-rolling-filter-ru-390.png"), full_page=False)
                # Capture the actual filtered comparison viewport for visual acceptance.
                page.locator("#compare").scroll_into_view_if_needed()
                page.screenshot(path=str(SHOTS / "m1-rolling-filtered-comparison-390.png"),
                                full_page=False)
                # Formula-leading titles must be plain CSV text; test download bytes.
                page.locator("#compare-table tbody tr:visible th a").evaluate(
                    """(el) => { el.textContent = '=HYPERLINK("x","y")'; }""")
                with page.expect_download() as guarded_export:
                    export_button.click()
                with Path(guarded_export.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    guarded_rows = list(csv.reader(handle))
                assert guarded_rows[1][5].startswith("'=HYPERLINK("), guarded_rows
                # Corrupted visible numbers fail closed, not a partial CSV.
                page.locator("#compare-table tbody tr:visible td").first.evaluate(
                    '(el) => el.textContent = "not-a-count"')
                export_button.click()
                expect(page.locator("#compare-csv-status")).to_contain_text("CSV unavailable")
                page.get_by_role("button", name="Show all").click()
                expect(page.locator(".card:visible")).to_have_count(2)
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(2)
                # Exact evidence and shared-history links remain available.
                expect(page.locator("tbody tr")).to_have_count(74)

                assert not errors, errors
                overflow = page.evaluate("""() => [...document.querySelectorAll('body *')]
                    .filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.right > innerWidth + 1 &&
                            getComputedStyle(el).position !== 'fixed';
                    }).slice(0, 8).map(el => ({
                        tag: el.tagName, id: el.id, className: String(el.className),
                        right: Math.round(el.getBoundingClientRect().right)
                    }))""")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), overflow
                page.close()
                # Shared topic, filter and pair URLs from the mutable site
                # must resolve through the exact accepted archive, including
                # after the synthetic mutable entrypoint changes.
                for width in (390, 320):
                    (m1 / "index.html").write_bytes((root / "preview/index.html").read_bytes())
                    restored = browser.new_page(viewport={"width": width, "height": 760},
                                                java_script_enabled=True)
                    mutable = f"http://127.0.0.1:{server.server_port}/m1/index.html"
                    restored.goto(mutable, wait_until="domcontentloaded")
                    topic_link = restored.locator(".share-action a").first.get_attribute("href")
                    assert f"/m1/archives/{digest}/index.html?df_dataset={digest}" in topic_link
                    filter_link = restored.locator("#atlas-filter-link").get_attribute("href")
                    assert f"/m1/archives/{digest}/index.html?af_dataset={digest}" in filter_link
                    restored.locator("#pair-left").select_option("detail-en-wikipedia-1234")
                    restored.locator("#pair-right").select_option("detail-ru-wikipedia-5678")
                    pair_link = restored.locator("#pair-share").get_attribute("href")
                    assert f"/m1/archives/{digest}/index.html?af_dataset={digest}" in pair_link
                    assert "af_left=detail-en-wikipedia-1234" in pair_link
                    restored.goto(topic_link, wait_until="domcontentloaded")
                    expect(restored.locator("#share-message")).to_contain_text("Shared history verified")
                    assert f"/m1/archives/{digest}/" in restored.url
                    assert restored.locator(".share-action a").first.get_attribute("href").startswith("?")
                    replacement = (root / "preview/index.html").read_bytes().replace(
                        digest.encode(), ("f" * 64).encode())
                    (m1 / "index.html").write_bytes(replacement)
                    restored.goto(topic_link, wait_until="domcontentloaded")
                    expect(restored.locator("#share-message")).to_contain_text("Shared history verified")
                    assert restored.url.endswith("#share-restore")
                    restored.goto(pair_link, wait_until="domcontentloaded")
                    expect(restored.locator("#pair-left")).to_have_value("detail-en-wikipedia-1234")
                    expect(restored.locator("#pair-right")).to_have_value("detail-ru-wikipedia-5678")
                    assert restored.url.startswith(f"http://127.0.0.1:{server.server_port}/m1/archives/{digest}/")
                    nojs = browser.new_page(viewport={"width": width, "height": 760},
                                            java_script_enabled=False)
                    nojs.goto(topic_link, wait_until="domcontentloaded")
                    expect(nojs.locator("#share-message")).to_contain_text("requires JavaScript")
                    expect(nojs.locator("article .daily-curve svg")).to_have_count(2)
                    nojs.close()
                    restored.screenshot(path=str(SHOTS / f"m1-immutable-share-{width}.png"),
                                        full_page=False)
                    restored.close()
                # Standalone offline download: moving one self-contained file
                # into an m1/ folder must not manufacture nonexistent archives.
                offline_dir = root / "offline" / "m1"
                offline_dir.mkdir(parents=True)
                offline_html = offline_dir / "index.html"
                shutil.copyfile(root / "preview/index.html", offline_html)
                assert not (offline_dir / "archives").exists()
                for width in (320, 390):
                    offline_page = browser.new_page(viewport={"width": width, "height": 760},
                                                    java_script_enabled=True)
                    offline_page.goto(offline_html.as_uri(), wait_until="domcontentloaded")
                    expect(offline_page.locator("#atlas-filters")).to_be_visible()
                    topic = offline_page.locator(".share-action a").first.get_attribute("href")
                    assert topic.startswith("?df_dataset="), topic
                    filtered = offline_page.locator("#atlas-filter-link").get_attribute("href")
                    assert filtered.startswith(offline_html.as_uri() + "?af_dataset="), filtered
                    offline_page.locator("#pair-left").select_option("detail-en-wikipedia-1234")
                    offline_page.locator("#pair-right").select_option("detail-ru-wikipedia-5678")
                    pair = offline_page.locator("#pair-share").get_attribute("href")
                    assert pair.startswith(offline_html.as_uri() + "?af_dataset="), pair
                    assert "af_left=detail-en-wikipedia-1234" in pair
                    assert "af_right=detail-ru-wikipedia-5678" in pair
                    topic_url = offline_page.evaluate(
                        "(href) => new URL(href, window.location.href).href", topic)
                    offline_page.goto(topic_url, wait_until="domcontentloaded")
                    expect(offline_page.locator("#share-message")).to_contain_text(
                        "Shared history verified")
                    assert offline_page.url.startswith(offline_html.as_uri() + "?df_dataset=")
                    assert "/archives/" not in offline_page.url
                    offline_page.close()
                browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
    print("PASS: synthetic-source rolling atlas, Chromium local HTTP 1280/390/320, "
          "no-JS evidence + JS filters/CSV download/formula guard, keyboard and no overflow")
    print("VISUAL: inspect retained actual-runtime screenshots in", SHOTS)
    print("NOT_RUN: Wikipedia upstream provenance, deployed GitHub Pages URL")


if __name__ == "__main__":
    main()
