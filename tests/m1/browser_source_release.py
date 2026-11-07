"""Real-source Chromium acceptance of one exact M1 CI candidate, never a public URL.

No synthetic fixture, new Wikimedia requests, or deployment in this test.
"""
from __future__ import annotations
import argparse
import csv
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
import json
import os
from pathlib import Path
import threading
from playwright.sync_api import expect, sync_playwright


def rows(download):
    with Path(download.path()).open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.reader(stream))


def key(row):
    return "detail-" + row["project"].replace(".", "-") + "-" + str(row["page_id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path, required=True)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_bytes())
    manifest = json.loads((args.release / "release-manifest.json").read_bytes())
    indexed = {key(row): row for row in candidate["series"]}
    assert len(indexed) == len(candidate["series"]) == manifest["series"] == 20
    assert sum(len(row["daily"]) for row in indexed.values()) == manifest["daily_observations"] == 700
    for field in ("dataset_id", "method_version", "observation_end"):
        assert candidate[field] == manifest[field], field
    args.screenshots.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0),
        partial(SimpleHTTPRequestHandler, directory=str(args.release)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True,
                executable_path=os.environ.get("CHROMIUM_EXECUTABLE"))
            try:
                for width in (320, 390, 1280):
                    page = browser.new_page(viewport={"width": width, "height": 850},
                                            java_script_enabled=False)
                    page.goto(url, wait_until="domcontentloaded")
                    expect(page.locator(".cards > .card")).to_have_count(20)
                    expect(page.locator("article[id^='detail-']")).to_have_count(20)
                    expect(page.locator("article[id^='detail-'] .scroll table tbody tr")).to_have_count(700)
                    expect(page.locator(".detail-daily-csv").first).to_be_hidden()
                    expect(page.locator("#pair-form")).to_be_hidden()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
                    # Independently bind the rendered no-JS SVG geometry to all
                    # 700 retained real-source daily observations, not a fixture.
                    curves = page.locator("article[id^='detail-'] figure.daily-curve")
                    expect(curves).to_have_count(20)
                    for row in candidate["series"]:
                        curve = page.locator(f"#{key(row)} figure.daily-curve")
                        svg = curve.locator("svg[role='img']")
                        expect(svg).to_be_visible()
                        assert svg.get_attribute("viewBox") == "0 0 364 104"
                        label = svg.get_attribute("aria-label") or ""
                        caption = curve.locator("figcaption").inner_text()
                        first, last = row["daily"][0]["date"], row["daily"][-1]["date"]
                        peak = max(day["views"] for day in row["daily"])
                        assert first in label and last in label
                        assert first in caption and last in caption
                        assert f"{peak:,}" in label and f"{peak:,}" in caption
                        zero = svg.locator("line.daily-zero")
                        assert (zero.get_attribute("x1"), zero.get_attribute("y1"),
                                zero.get_attribute("x2"), zero.get_attribute("y2")) == (
                                    "12", "90", "352", "90")
                        points = (svg.locator("polyline.daily-line").get_attribute("points") or "").split()
                        assert len(points) == 35
                        for i, (point, day) in enumerate(zip(points, row["daily"])):
                            x, y = map(int, point.split(","))
                            expected_y = 90 - (
                                (day["views"] * 74 + peak // 2) // peak if peak else 0)
                            assert (x, y) == (12 + 10 * i, expected_y), (width, key(row), i)
                    # Capture a real graph in context. Earlier hero-only captures
                    # never showed the new timeline, so visual acceptance was incomplete.
                    first_history = page.locator(f"#{key(candidate['series'][0])} figure.daily-curve")
                    first_history.scroll_into_view_if_needed()
                    assert first_history.evaluate(
                        "el => el.getBoundingClientRect().left >= 0 && "
                        "el.getBoundingClientRect().right <= innerWidth")
                    page.screenshot(path=str(args.screenshots / f"real-history-nojs-{width}.png"),
                                    animations="disabled")
                    if width == 390:
                        russian = next(row for row in candidate["series"]
                                       if row["project"] == "ru.wikipedia")
                        ru_history = page.locator(f"#{key(russian)} figure.daily-curve")
                        ru_history.scroll_into_view_if_needed()
                        page.screenshot(path=str(args.screenshots / "real-history-ru-nojs-390.png"),
                                        animations="disabled")
                    page.keyboard.press("Tab")
                    assert page.evaluate("document.activeElement.className") == "skip"
                    page.screenshot(path=str(args.screenshots / f"real-nojs-{width}.png"),
                                    animations="disabled")
                    page.close()
                page = browser.new_page(viewport={"width": 390, "height": 850},
                                        accept_downloads=True)
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.goto(url, wait_until="domcontentloaded")
                expect(page.locator(".cards > .card")).to_have_count(20)
                expect(page.locator(".detail-daily-csv")).to_have_count(20)
                assert page.locator("#share-restore").get_attribute("data-dataset") == manifest["candidate_sha256"]
                assert page.locator("#share-restore").get_attribute("data-method") == manifest["method_version"]
                en = next(row for row in candidate["series"] if row["project"] == "en.wikipedia")
                ru = next(row for row in candidate["series"] if row["project"] == "ru.wikipedia")
                for row in (en, ru):
                    series = key(row)
                    button = page.locator(f"#{series} .detail-daily-csv")
                    expect(button).to_be_visible()
                    assert button.evaluate("el => el.getBoundingClientRect().height") >= 44
                    with page.expect_download() as event:
                        button.click()
                    data = rows(event.value)
                    assert len(data) == 36 and data[0][-2:] == ["utc_date", "daily_requests"]
                    assert all(line[:5] == [manifest["candidate_sha256"],
                        manifest["method_version"], manifest["observation_end"],
                        series, row["project"]] for line in data[1:])
                    assert [line[-2:] for line in data[1:]] == [
                        [day["date"], str(day["views"])] for day in row["daily"]]
                page.locator("#pair-left").select_option(key(en))
                page.locator("#pair-right").select_option(key(ru))
                expect(page.locator("#pair-output")).to_be_visible()
                with page.expect_download() as event:
                    page.locator("#pair-daily-csv").click()
                pair = rows(event.value)
                assert len(pair) == 71
                assert [line[-2:] for line in pair[1:36]] == [
                    [d["date"], str(d["views"])] for d in en["daily"]]
                assert [line[-2:] for line in pair[36:]] == [
                    [d["date"], str(d["views"])] for d in ru["daily"]]
                with page.expect_download() as event:
                    page.locator("#pair-csv").click()
                weekly = rows(event.value)
                assert len(weekly) == 3
                for output, row in zip(weekly[1:], (en, ru)):
                    assert [int(x) for x in output[7:12]] == [
                        sum(day["views"] for day in row["daily"][i:i + 7])
                        for i in range(0, 35, 7)]
                share = page.locator("#pair-share").get_attribute("href")
                assert all(x in share for x in ("af_dataset=", "af_left=", "af_right="))
                page.goto(share, wait_until="domcontentloaded")
                expect(page.locator("#pair-left")).to_have_value(key(en))
                expect(page.locator("#pair-right")).to_have_value(key(ru))
                page.locator("#atlas-query").fill("no title matches this")
                expect(page.locator(".card:visible")).to_have_count(0)
                expect(page.locator("#pair-daily-csv")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(args.screenshots / "real-pair-390.png"),
                                animations="disabled")
                assert not errors, errors
                page.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print("PASS real source-gated M1 candidate: 20 titles, 700 days, exact CSV, no-JS/mobile/share")


if __name__ == "__main__":
    main()
