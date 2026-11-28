"""Real browser gate for the staged Pages entry, not a public deployment."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qs, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from browser_m0_http import server
from browser_runner import launch_chromium
from tools.build_static_release import (NICHE_ROUTE, NICHE_SHA256, NICHE_RECEIPT,
                                        bundle_files, build_zip, digest)
from tools.stage_pages import stage
from tools.m1_niche_replay import replay

OUT = ROOT / "artifacts/m0-http/dated-niche"


def journey(browser, address, width):
    context = browser.new_context(viewport={"width": width, "height": 844},
                                  reduced_motion="reduce", service_workers="block")
    errors, requests = [], []
    page = context.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("request", lambda request: requests.append(request.url))

    def no_overflow():
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    def capture(name):
        path = OUT / f"{width}-{name}.png"
        page.screenshot(path=str(path))
        return {"name": path.name, "sha256": digest(path.read_bytes())}

    shots = []
    try:
        response = page.goto(address, wait_until="load")
        assert response and response.status == 200
        entry = page.locator("#open-niche-atlas")
        assert entry.is_visible() and entry.get_attribute("href") == NICHE_ROUTE
        assert entry.bounding_box()["height"] >= 44
        title = entry.locator("strong")
        window = entry.locator(".niche-window")
        scope = entry.locator(".niche-scope")
        assert title.inner_text() == "Open the 19-title atlas"
        assert window.inner_text() == "20 Oct–23 Nov 2026 UTC · 665 daily counts"
        assert "historical, not live" in scope.inner_text()
        # The title, date and scope must be separate readable rows, not
        # adjacent inline text or a stranded decorative arrow.
        boxes = [item.bounding_box() for item in (title, window, scope)]
        outer = entry.bounding_box()
        for box in boxes:
            assert box and outer["x"] <= box["x"]
            assert box["x"] + box["width"] <= outer["x"] + outer["width"] + 1
        for above, below in zip(boxes, boxes[1:]):
            assert above["y"] + above["height"] + 3 <= below["y"]
        assert entry.evaluate("(el) => el.scrollWidth <= el.clientWidth")
        entry.focus()
        assert entry.evaluate("(el) => document.activeElement === el")
        no_overflow()
        shots.append(capture("root-entry"))
        with page.expect_navigation(wait_until="load") as navigation:
            page.keyboard.press("Enter")
        response = navigation.value
        assert response and response.status == 200
        assert response.headers["content-type"].startswith("text/html")
        assert digest(response.body()) == NICHE_SHA256
        assert page.url == urljoin(address, NICHE_ROUTE)
        assert page.locator(".cards > .card").count() == 19
        assert page.locator("#share-restore").get_attribute("data-dataset") == NICHE_RECEIPT["dataset_fingerprint"]
        assert "gains 6" in page.locator("#atlas-results").inner_text()
        no_overflow()
        shots.append(capture("reader"))
        page.locator("#atlas-step-direction").select_option("opposite")
        assert page.locator(".cards > .card:visible").count() == 4
        summary = page.locator("#atlas-results")
        assert "gains 3" in summary.inner_text() and "opposite nonzero signs 4" in summary.inner_text()
        summary.scroll_into_view_if_needed()
        no_overflow()
        shots.append(capture("opposite"))
        page.locator("#atlas-step-direction").select_option("all")
        left = "detail-en-wikipedia-21489"
        # Find exact OpenTTD ID from the already pinned visible selection.
        options = page.locator("#pair-right option").all()
        right = next(opt.get_attribute("value") for opt in options if opt.inner_text() == "EN · OpenTTD")
        page.locator("#pair-left").select_option(left)
        page.locator("#pair-right").select_option(right)
        # Two selected-title rows; five aligned UTC-week change rows.
        assert page.locator("#pair-table tbody tr").count() == 2
        assert page.locator("#pair-changes-table tbody tr").count() == 5
        assert page.locator("#pair-daily-charts svg").count() >= 2
        link = page.locator("#pair-share")
        assert link.is_visible()
        shared = urljoin(page.url, link.get_attribute("href"))
        assert urlsplit(shared).path == "/Dayflare/" + NICHE_ROUTE
        query = parse_qs(urlsplit(shared).query)
        assert query["af_dataset"] == [NICHE_RECEIPT["dataset_fingerprint"]]
        assert query["af_left"] == [left] and query["af_right"] == [right]
        response = page.goto(shared, wait_until="load")
        assert response and response.status == 200 and digest(response.body()) == NICHE_SHA256
        assert page.locator("#pair-left").input_value() == left
        assert page.locator("#pair-right").input_value() == right
        # Two selected-title rows; five aligned UTC-week change rows.
        assert page.locator("#pair-table tbody tr").count() == 2
        assert page.locator("#pair-changes-table tbody tr").count() == 5
        assert page.locator("#pair-daily-charts svg").count() >= 2
        page.locator("#pair-daily-charts").scroll_into_view_if_needed()
        no_overflow()
        shots.append(capture("shared-pair"))
        assert not errors, errors
        assert all(urlsplit(url).netloc == urlsplit(address).netloc for url in requests), requests
        return {"width": width, "shared_query": query, "screenshots": shots}
    finally:
        context.close()



def candidate_journey(browser, address, width, html_sha):
    """Exercise newly rendered real data, separately from immutable reader."""
    context = browser.new_context(viewport={"width": width, "height": 844},
                                  reduced_motion="reduce", service_workers="block",
                                  accept_downloads=True)
    page = context.new_page()
    errors, requests, shots = [], [], []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("request", lambda request: requests.append(request.url))
    candidate_url = urljoin(address, "candidate/index.html")
    history_url = urljoin(address, NICHE_ROUTE)
    expected = {"Zoetrope", "Foucault pendulum", "Цианотипия", "Плутовской роман"}

    def visit(url, sha):
        response = page.goto(url, wait_until="load")
        assert response and response.status == 200
        assert response.headers["content-type"].startswith("text/html")
        assert digest(response.body()) == sha
        assert page.locator(".cards > .card").count() == 19
        assert page.locator("#share-restore").get_attribute("data-dataset") == NICHE_RECEIPT["dataset_fingerprint"]

    def export(button):
        with page.expect_download() as download:
            page.locator(button).click()
        return download.value.path().read_bytes()

    def capture(name, locator):
        locator.evaluate("(el) => el.scrollIntoView({block:'center'})")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        path = OUT / f"candidate-{width}-{name}.png"
        page.screenshot(path=str(path))
        shots.append({"name": path.name, "sha256": digest(path.read_bytes())})

    expected_ids = {
        ("en.wikipedia", "34526"), ("en.wikipedia", "72839"),
        ("ru.wikipedia", "24522"), ("ru.wikipedia", "787715"),
    }

    def matching():
        cards = page.locator(".cards > .card:visible")
        rows = cards.evaluate_all(
            "(els) => els.map(el => [el.dataset.edition, el.dataset.pageId, el.dataset.title])")
        identities = {(edition, page_id) for edition, page_id, _ in rows}
        titles = {title for _, _, title in rows}
        assert len(rows) == cards.count() == len(identities), rows
        assert all(edition in {"en.wikipedia", "ru.wikipedia"} and
                   page_id.isascii() and page_id.isdecimal() and int(page_id) > 0
                   for edition, page_id in identities), identities
        return identities, titles

    def assert_opposite():
        identities, titles = matching()
        assert identities == expected_ids, identities
        assert titles == expected, titles

    try:
        # Immutable historical reader is an independent byte-parity control.
        visit(history_url, NICHE_SHA256)
        page.locator("#atlas-step-direction").select_option("opposite")
        assert_opposite()
        historical_csv = export("#compare-week-changes-csv")
        visit(candidate_url, html_sha)
        select = page.locator("#atlas-step-direction")
        assert select.input_value() == "all"
        identities, titles = matching()
        assert len(identities) == 19
        assert len(titles) == 17  # NetHack and OpenTTD occur in both editions.
        assert {("en.wikipedia", "21489"), ("ru.wikipedia", "72002"),
                ("en.wikipedia", "703297"), ("ru.wikipedia", "280643")} <= identities
        assert "gains 6" in page.locator("#atlas-results").inner_text()

        def label_fit(label):
            result = select.evaluate("""el => {
                const style = getComputedStyle(el);
                const ctx = document.createElement('canvas').getContext('2d');
                ctx.font = [style.fontStyle, style.fontWeight, style.fontSize, style.fontFamily].join(' ');
                const text = el.selectedOptions[0].textContent;
                const available = el.clientWidth - parseFloat(style.paddingLeft) -
                    parseFloat(style.paddingRight) - 24;
                return {text, measured:ctx.measureText(text).width, available,
                    focused:document.activeElement === el};
            }""")
            assert result["text"] == label and result["focused"], result
            assert result["measured"] <= result["available"], result
            return result

        select.focus()
        all_fit = label_fit("All directions")
        capture("all", select)
        # Native keyboard selection (not a synthetic change event).
        select.press("End")
        assert select.input_value() == "opposite"
        opposite_fit = label_fit("Opposite signs")
        assert_opposite()
        summary = page.locator("#atlas-results")
        assert "gains 3" in summary.inner_text() and "opposite nonzero signs 4" in summary.inner_text()
        assert page.locator(".step-direction-hint").is_visible()
        capture("opposite", select)
        capture("results", summary)
        candidate_csv = export("#compare-week-changes-csv")
        assert candidate_csv == historical_csv
        rows = list(csv.reader(io.StringIO(candidate_csv.decode("utf-8-sig"))))
        assert len(rows) == 21, len(rows)
        filter_url = urljoin(page.url, page.locator("#atlas-filter-link").get_attribute("href"))
        assert parse_qs(urlsplit(filter_url).query)["af_step"] == ["opposite"]
        visit(filter_url, html_sha)
        assert_opposite()
        page.locator("#atlas-step-direction").select_option("all")
        left = "detail-en-wikipedia-21489"
        right = next(opt.get_attribute("value") for opt in page.locator("#pair-right option").all()
                     if opt.inner_text() == "EN · OpenTTD")
        page.locator("#pair-left").select_option(left)
        page.locator("#pair-right").select_option(right)
        assert page.locator("#pair-table tbody tr").count() == 2
        assert page.locator("#pair-changes-table tbody tr").count() == 5
        assert page.locator("#pair-daily-charts svg").count() >= 2
        shared = urljoin(page.url, page.locator("#pair-share").get_attribute("href"))
        query = parse_qs(urlsplit(shared).query)
        assert urlsplit(shared).path == urlsplit(candidate_url).path
        assert query["af_dataset"] == [NICHE_RECEIPT["dataset_fingerprint"]]
        assert query["af_left"] == [left] and query["af_right"] == [right]
        visit(shared, html_sha)
        assert page.locator("#pair-left").input_value() == left
        assert page.locator("#pair-right").input_value() == right
        assert page.locator("#pair-table tbody tr").count() == 2
        assert page.locator("#pair-changes-table tbody tr").count() == 5
        assert page.locator("#pair-daily-charts svg").count() >= 2
        capture("shared-pair", page.locator("#pair-daily-charts"))
        assert not errors, errors
        assert all(urlsplit(url).netloc == urlsplit(address).netloc or
                   url.startswith("blob:" + address.split("/Dayflare/")[0] + "/")
                   for url in requests), requests
        return {"width": width, "all_fit": all_fit, "opposite_fit": opposite_fit,
                "opposite_titles": sorted(expected), "opposite_identities": sorted(expected_ids),
                "csv_sha256": digest(candidate_csv),
                "csv_data_rows": len(rows) - 1, "shared_query": query, "screenshots": shots}
    finally:
        context.close()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = bundle_files()
    receipt = {"status": "INCOMPLETE", "transport": "LOCAL_HTTP_NOT_PAGES",
               "html_sha256": NICHE_SHA256,
               "manifest_sha256": digest(files["release-manifest.json"]), "journeys": []}
    try:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stage(build_zip(files), root / "Dayflare", receipt["manifest_sha256"], files)
            candidate = root / "Dayflare/candidate"
            receipt["candidate_replay"] = replay(candidate)
            candidate_html = (candidate / "index.html").read_bytes()
            repeat = root / "repeat"
            receipt["candidate_repeat"] = replay(repeat)
            assert (repeat / "index.html").read_bytes() == candidate_html
            receipt["candidate_html_sha256"] = digest(candidate_html)
            assert receipt["candidate_html_sha256"] != NICHE_SHA256
            (OUT / "candidate-index.html").write_bytes(candidate_html)
            receipt["candidate_journeys"] = []
            with server(root) as address, sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                try:
                    for width in (390, 1280):
                        receipt["journeys"].append(journey(browser, address, width))
                    for width in (320, 390, 1280):
                        receipt["candidate_journeys"].append(candidate_journey(
                            browser, address, width, receipt["candidate_html_sha256"]))
                finally:
                    browser.close()
        receipt["status"] = "PASS"
        print("PASS staged same-origin root, dated reader and share replay; not public Pages")
    finally:
        (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
