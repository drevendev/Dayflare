"""Chromium local HTTP acceptance of the actual retained Nov 4–5 EN/RU report."""
from functools import partial
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.m1_real_pair import build
from playwright.sync_api import sync_playwright

SHOTS = ROOT / 'evidence/local-m1-real-pair-browser'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='dayflare-real-pair-http-') as tmp:
        root = Path(tmp)
        parent = root / 'Dayflare'
        parent.mkdir()
        target = parent / 'real-identity-history'
        report = build(target)
        manifest = json.loads((target / 'manifest.json').read_bytes())
        for name, digest in manifest['files'].items():
            assert sha256((target / name).read_bytes()).hexdigest() == digest
        assert report['summary']['change_counts'] == {'unchanged_observation': 20}
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(root)))
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        url = base + '/Dayflare/real-identity-history/'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    for width in (320, 390, 1280):
                        for js in (False, True):
                            context = browser.new_context(
                                viewport={'width': width, 'height': 900},
                                java_script_enabled=js, reduced_motion='reduce')
                            page = context.new_page()
                            page.set_default_timeout(10000)
                            errors, external = [], []
                            page.on('pageerror', lambda e: errors.append(str(e)))
                            page.on('request', lambda request: external.append(request.url)
                                    if not request.url.startswith(base + '/') else None)
                            response = page.goto(url, wait_until='networkidle', timeout=25000)
                            assert response and response.status == 200
                            assert page.locator('article.card').count() == 20
                            assert page.locator('.banner').inner_text().startswith('REPORTED METADATA')
                            assert '2026-11-04 → 2026-11-05 UTC' in page.locator('header').inner_text()
                            assert 'not a live feed' in page.locator('header').inner_text()
                            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                            page.screenshot(path=str(SHOTS / f'real-pair-{width}-js{int(js)}.png'))
                            page.keyboard.press('Tab')
                            assert page.locator('a.skip').evaluate('e => document.activeElement === e')
                            page.keyboard.press('Enter')
                            assert page.locator('#index').evaluate('e => document.activeElement === e')
                            first = page.locator('#index a').first
                            page.keyboard.press('Tab')
                            assert first.evaluate('e => document.activeElement === e')
                            href = first.get_attribute('href')
                            assert manifest['report_id'] in href
                            page.keyboard.press('Enter')
                            assert page.locator(href).evaluate('e => document.activeElement === e')
                            detail = page.locator(href + ' details')
                            detail.locator('summary').focus()
                            page.keyboard.press('Enter')
                            assert detail.get_attribute('open') is not None
                            assert '"pageview_join_allowed": false' in detail.locator('pre').inner_text()
                            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                            page.screenshot(path=str(SHOTS / f'real-pair-detail-{width}-js{int(js)}.png'))
                            page.goto(url + href, wait_until='networkidle')
                            assert page.url.endswith(href)
                            fetch = page.request.get(url + 'history.json')
                            assert fetch.ok and fetch.body() == (target / 'history.json').read_bytes()
                            assert fetch.json()['summary']['change_counts'] == {'unchanged_observation': 20}
                            assert not errors and not external, (errors, external)
                            context.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
    print('PASS: real 4–5 Nov EN/RU data, 320/390/1280 HTTP Chromium, keyboard, JS/no-JS, evidence, anchors, exact JSON, no overflow')
    print('NOT VERIFIED: upstream transport authenticity, uninterrupted identity or public Pages')


if __name__ == '__main__':
    main()
