"""Real local-HTTP Chromium acceptance; synthetic identity history, not a deployment."""
from functools import partial
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from tools.m1_identity_history_demo import build_demo


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    screenshots = ROOT / "evidence/local-m1-browser"
    screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        parent = root / "Dayflare"
        parent.mkdir()
        bundle = parent / "identity-history"
        build_demo(bundle)
        manifest = json.loads((bundle / "manifest.json").read_text())
        for name, expected in manifest["files"].items():
            assert sha256((bundle / name).read_bytes()).hexdigest() == expected
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root)))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        url = base + "/Dayflare/identity-history/"
        try:
            with sync_playwright() as p:
                options = {"headless": True}
                executable = os.environ.get("DAYFLARE_BROWSER_EXECUTABLE")
                if executable:
                    options["executable_path"] = executable
                browser = p.chromium.launch(**options)
                try:
                    for javascript in (False, True):
                        for width in (320, 390, 1280):
                            context = browser.new_context(viewport={"width": width, "height": 900},
                                                          java_script_enabled=javascript, reduced_motion="reduce")
                            page = context.new_page()
                            errors, external = [], []
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            page.on("request", lambda request: external.append(request.url)
                                    if not request.url.startswith(base + "/") else None)
                            response = page.goto(url, wait_until="networkidle")
                            assert response.status == 200
                            assert "text/html" in response.headers["content-type"]
                            assert page.get_by_role("heading", name="What changed between observations?").is_visible()
                            assert page.locator(".banner").inner_text().startswith("SYNTHETIC DEMONSTRATION")
                            assert page.locator("article.card").count() == 7
                            # Retain the actual failure viewport before checking layout.
                            page.screenshot(path=str(screenshots / f"identity-history-{width}-{'js' if javascript else 'nojs'}.png"))
                            overflow = page.evaluate("""() => Array.from(document.querySelectorAll('body *'))
                                .filter(e => e.getBoundingClientRect().right > window.innerWidth)
                                .map(e => ({tag: e.tagName, className: e.className,
                                    text: e.textContent.slice(0, 100), right: e.getBoundingClientRect().right}))
                                .slice(0, 10)""")
                            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), overflow
                            page.keyboard.press("Tab")
                            assert page.locator("a.skip").evaluate("e => e === document.activeElement")
                            page.keyboard.press("Enter")
                            assert page.locator("#index").evaluate("e => e === document.activeElement")
                            page.keyboard.press("Tab")
                            first = page.locator("#index a").first
                            assert first.evaluate("e => e === document.activeElement")
                            anchor = first.get_attribute("href")
                            assert manifest["report_id"] in anchor
                            page.keyboard.press("Enter")
                            assert page.locator(anchor).evaluate("e => e === document.activeElement")
                            summary = page.locator(anchor + " summary")
                            summary.focus()
                            page.keyboard.press("Enter")
                            assert page.locator(anchor + " details").get_attribute("open") is not None
                            assert '"pageview_join_allowed": false' in page.locator(anchor + " pre").inner_text()
                            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                            page.screenshot(path=str(screenshots / f"identity-history-detail-{width}-{'js' if javascript else 'nojs'}.png"))
                            page.goto(url + anchor, wait_until="networkidle")
                            assert page.url.endswith(anchor)
                            data = page.request.get(url + "history.json")
                            assert data.ok and data.json()["report_id"] == manifest["report_id"]
                            assert not errors, errors
                            assert not external, external
                            context.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    print("PASS: 6 Chromium local-HTTP journeys at 320/390/1280, JS/no-JS, keyboard, exact evidence, deep links, no overflow or external requests")


if __name__ == "__main__":
    main()
