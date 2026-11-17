"""Check actual 30-title source-derived HTML in Chromium before retaining it.

This is bounded local-HTTP visitor acceptance, NOT independent Wikimedia origin
verification, public deployment, a release approval, or a universal pageview ranking.
"""
from __future__ import annotations

import argparse
from functools import partial
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def check(preview: Path, screenshots: Path, *, render_only: bool = False) -> None:
    html = (preview / "index.html").read_bytes()
    manifest = json.loads((preview / "preview-manifest.json").read_bytes())
    if (manifest.get("html_sha256") != sha256(html).hexdigest()
            or manifest.get("series") != 30
            or manifest.get("publication_status") != "LOCAL_PREVIEW_NOT_PUBLISHED"
            or len(html) > 2_000_000):
        raise AssertionError("30-title preview manifest or HTML integrity mismatch")
    screenshots.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0),
        partial(QuietHandler, directory=str(preview.parent)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    receipts = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True,
                executable_path=os.environ.get("CHROMIUM_EXECUTABLE") or None,
                args=["--no-sandbox"] if os.environ.get("CHROMIUM_EXECUTABLE") else [])
            try:
                for width, javascript in ((320, False), (390, True), (1280, False)):
                    page = browser.new_page(viewport={"width": width, "height": 820},
                        java_script_enabled=javascript, reduced_motion="reduce")
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    try:
                        if render_only:
                            page.set_content(html.decode("utf-8"), wait_until="domcontentloaded")
                        else:
                            page.goto(f"http://127.0.0.1:{server.server_port}/{preview.name}/",
                                wait_until="domcontentloaded", timeout=30000)
                        page.locator("article .scroll tbody tr").first.wait_for()
                        assert page.locator(".card").count() == 30
                        assert page.locator("article").count() == 30
                        assert page.locator("article .scroll tbody tr").count() == 1050
                        assert page.locator(".warning").inner_text().startswith("LOCAL EVIDENCE")
                        assert page.locator(".save-snapshot").get_attribute("href") == ""
                        assert page.locator('a[href="#overview"]').count() >= 1
                        geometry = page.evaluate("""() => ({
                            viewport: innerWidth,
                            document: document.documentElement.scrollWidth,
                            overflowingTitles: [...document.querySelectorAll('article h3')]
                                .filter(el => el.scrollWidth > el.clientWidth)
                                .map(el => ({title: el.textContent,
                                             actual: el.scrollWidth, available: el.clientWidth}))
                        })""")
                        assert geometry["document"] <= geometry["viewport"], geometry
                        assert not geometry["overflowingTitles"], geometry
                        assert not errors, errors
                        filename = f"30-title-{width}-{'js' if javascript else 'nojs'}.png"
                        image = screenshots / filename
                        page.screenshot(path=str(image), full_page=False)
                        receipts.append({"width": width, "javascript": javascript,
                            "screenshot": filename, "sha256": sha256(image.read_bytes()).hexdigest(),
                            "document_width": geometry["document"]})
                        print(f"PASS {width}px {'JS' if javascript else 'NO-JS'}: "
                              "30 cards, 1050 daily rows, evidence, no overflow")
                    finally:
                        page.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    (screenshots / "receipt.json").write_text(json.dumps({
        "schema_version": "dayflare.m1-30-real-output-browser.v1",
        "html_sha256": sha256(html).hexdigest(),
        "mode": "RENDER_ONLY_NOT_HTTP" if render_only else "LOCAL_HTTP_NOT_PUBLIC",
        "screenshots": receipts,
        "status": "NOT_PUBLISHED_NOT_LIVE_VERIFIED",
    }, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("preview", type=Path)
    parser.add_argument("screenshots", type=Path)
    parser.add_argument("--render-only", action="store_true", help="CSS/DOM only; NOT HTTP acceptance")
    args = parser.parse_args()
    check(args.preview, args.screenshots, render_only=args.render_only)
