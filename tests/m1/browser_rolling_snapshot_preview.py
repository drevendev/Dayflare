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
                    expect(page.locator("article .daily-curve svg[role=img]")).to_have_count(2)
                    assert "peak 35 requests; zero-origin" in page.locator("article .daily-curve svg").first.get_attribute("aria-label")
                    assert "peak 0 requests; zero-origin" in page.locator("article .daily-curve svg").last.get_attribute("aria-label")
                    assert page.locator("article .daily-curve .daily-line").first.get_attribute("points").startswith("12,88 22,86")
                    assert page.locator("article .daily-curve .daily-line").last.get_attribute("points").startswith("12,90 22,90")
                    expect(page.locator("#atlas-filters")).to_be_hidden()
                    expect(page.locator(".card-pair")).to_have_count(2)
                    expect(page.locator("#compare-csv")).to_be_hidden()
                    expect(page.locator("#compare-daily-csv")).to_be_hidden()
                    expect(page.locator("#pair-csv")).to_be_hidden()
                    expect(page.locator("#pair-daily-charts")).to_be_hidden()
                    expect(page.locator(".detail-daily-csv")).to_have_count(2)
                    expect(page.locator(".detail-daily-csv").first).to_be_hidden()
                    share_link = page.locator("#atlas-filter-link")
                    expect(share_link).to_be_hidden()
                    assert share_link.evaluate("(el) => getComputedStyle(el).display") == "none"
                    expect(page.locator("article")).to_have_count(2)
                    expect(page.locator(".warning")).to_contain_text("SYNTHETIC TEST DATA")
                    expect(page.locator("tbody tr")).to_have_count(2 + 2 * 35)
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
                    source_summary = page.locator("#detail-en-wikipedia-1234 summary")
                    source_summary.focus()
                    page.keyboard.press("Enter")
                    assert page.locator("#detail-en-wikipedia-1234 details").evaluate("el => el.open")
                    expect(page.locator("#detail-en-wikipedia-1234 code")).to_have_count(1)
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
                expect(page.locator("#pair-share")).to_be_hidden()
                expect(page.locator("#pair-csv")).to_be_hidden()
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
                expect(page.locator("#pair-daily-charts")).to_contain_text(
                    "Daily charts unavailable")
                expect(page.locator(".pair-daily-line")).to_have_count(0)
                expect(page.locator("#pair-table tbody tr")).to_have_count(2)
                daily_cell.evaluate("(el, value) => el.textContent = value",
                                    preserved_daily)
                page.locator("#pair-right").select_option("")
                page.locator("#pair-right").select_option("detail-ru-wikipedia-5678")
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
                expect(daily_export).to_be_visible()
                with page.expect_download() as filtered_daily_download:
                    daily_export.click()
                with Path(filtered_daily_download.value.path()).open(
                        "r", encoding="utf-8-sig", newline="") as handle:
                    assert list(csv.reader(handle)) == daily_csv
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
                    for order_mode in ("editorial", "increase", "decrease",
                                       "relative-increase", "relative-decrease"):
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
                # Exact measured sign, not a heuristic lifecycle classification.
                sign = page.locator("#atlas-change")
                expect(sign).to_have_value("all")
                sign.select_option("positive")
                expect(page.locator(".card:visible")).to_have_count(1)
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
                expect(page.locator('.card[data-series="detail-ru-wikipedia-5678"]')).to_be_visible()
                sign.select_option("negative")
                expect(page.locator(".card:visible")).to_have_count(0)
                expect(page.locator("#compare-empty")).to_be_visible()
                expect(export_button).to_be_disabled()
                # Synthetic negative counterexample, without changing source data.
                ru_card.evaluate('(el) => el.dataset.delta2 = "-1"')
                sign.select_option("all")
                sign.select_option("negative")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator('.card[data-series="detail-ru-wikipedia-5678"]')).to_be_visible()
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(1)
                ru_card.evaluate('(el) => el.dataset.delta2 = "0"')
                sign.select_option("all")
                page.locator("#atlas-query").fill("ШАХ")
                expect(page.locator(".card:visible")).to_have_count(1)
                expect(page.locator("#atlas-results")).to_contain_text("Showing 1 of 2")
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
                expect(page.locator("tbody tr")).to_have_count(72)
                page.get_by_role("button", name="Show all").click()
                expect(page.locator(".card:visible")).to_have_count(2)
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
                expect(page.locator("tbody tr")).to_have_count(72)

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
