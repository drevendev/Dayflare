"""Real browser gate for the staged Pages entry, not a public deployment."""
from __future__ import annotations

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
            with server(root) as address, sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                try:
                    for width in (390, 1280):
                        receipt["journeys"].append(journey(browser, address, width))
                finally:
                    browser.close()
        receipt["status"] = "PASS"
        print("PASS staged same-origin root, dated reader and share replay; not public Pages")
    finally:
        (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
