"""Actual Chromium local-HTTP acceptance of the synthetic rolling-source atlas."""
from __future__ import annotations

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
                    expect(page.locator("article")).to_have_count(2)
                    expect(page.locator(".warning")).to_contain_text("SYNTHETIC TEST DATA")
                    expect(page.locator("tbody tr")).to_have_count(2 + 2 * 35)
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
                browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
    print("PASS: synthetic-source rolling atlas, Chromium local HTTP 1280/390/320, "
          "no-JS cards/details/source, keyboard and no document overflow")
    print("VISUAL: inspect retained actual-runtime screenshots in", SHOTS)
    print("NOT_RUN: Wikipedia upstream provenance, deployed GitHub Pages URL")


if __name__ == "__main__":
    main()
