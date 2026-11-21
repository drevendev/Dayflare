"""Real Nov 18 EN/RU atlas: Chromium local-HTTP mobile and no-JS acceptance.

Executes original retained-source HTML, not synthetic fixtures or deployed Pages.
"""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
import tempfile
from threading import Thread

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.m1_20_local_atlas import build

SHOTS = ROOT / "artifacts/m1-20-real-browser"


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        root = Path(work)
        manifest = build(root / "atlas")
        assert manifest["series"] == 20
        handler = partial(SimpleHTTPRequestHandler, directory=str(root))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/atlas/"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True, executable_path=os.environ.get("CHROMIUM_EXECUTABLE"))
                try:
                    for width, height, javascript in [
                            (320, 700, False), (390, 844, True), (1280, 850, True)]:
                        page = browser.new_page(
                            viewport={"width": width, "height": height},
                            java_script_enabled=javascript)
                        page.goto(url, wait_until="domcontentloaded")
                        expect(page.locator("h1")).to_have_text("Where did attention change?")
                        expect(page.locator(".card")).to_have_count(20)
                        expect(page.locator("article")).to_have_count(20)
                        expect(page.locator("#compare-table tbody tr")).to_have_count(20)
                        expect(page.locator(".metadata")).to_contain_text("2026-11-18")
                        expect(page.locator(".warning")).to_contain_text("not")
                        expect(page.locator(".save-snapshot")).to_be_visible()
                        expect(page.locator("article .daily-curve svg")).to_have_count(20)
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"), (
                            f"horizontal overflow at {width}px")
                        page.screenshot(
                            path=str(SHOTS / f"real-{width}-{'js' if javascript else 'nojs'}.png"))
                        if not javascript:
                            expect(page.locator("#atlas-filters")).to_be_hidden()
                            page.keyboard.press("Tab")
                            assert page.evaluate(
                                "document.activeElement.className") == "skip"
                            page.locator(".hero-action").click()
                            assert page.evaluate("location.hash") == "#overview"
                            expect(page.locator("article .scroll table")).to_have_count(20)
                        else:
                            expect(page.locator("#atlas-filters")).to_be_visible()
                            expect(page.locator("#pair-form")).to_be_visible()
                        page.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
