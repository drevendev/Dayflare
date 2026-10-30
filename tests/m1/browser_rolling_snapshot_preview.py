"""Actual Chromium local-HTTP acceptance of the synthetic rolling-source atlas."""
from __future__ import annotations

import csv

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
                    expect(page.locator(".card")).to_have_count(2)
                    expect(page.locator("#atlas-filters")).to_be_hidden()
                    expect(page.locator("#compare-csv")).to_be_hidden()
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
                # Progressive enhancement: discovery filters scope the weekly
                # comparison rows, but never remove the exact daily evidence.
                page = browser.new_page(viewport={"width": 390, "height": 844},
                                        device_scale_factor=1, java_script_enabled=True)
                errors = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.goto(url, wait_until="domcontentloaded")
                expect(page.locator("#atlas-filters")).to_be_visible()
                expect(page.locator(".card:visible")).to_have_count(2)
                expect(page.locator("#compare-table tbody tr:visible")).to_have_count(2)
                # Native <select> hides part of long values on narrow phones even
                # when the page itself has no horizontal overflow. Measure the
                # currently selected text, allowing room for the platform arrow.
                for viewport_width in (390, 320):
                    page.set_viewport_size({"width": viewport_width, "height": 844})
                    for order_mode in ("editorial", "increase", "decrease"):
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
                # Adjacent integers beyond Number.MAX_SAFE_INTEGER must remain distinct.
                ru_card = page.locator('.card[data-series="detail-ru-wikipedia-5678"]')
                en_card = page.locator('.card[data-series="detail-en-wikipedia-1234"]')
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
