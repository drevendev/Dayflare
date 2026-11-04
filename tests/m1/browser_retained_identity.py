"""Real retained metadata over ordinary local HTTP; not GitHub Pages acceptance."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.m1_retained_identity import build, SNAPSHOT
from playwright.sync_api import sync_playwright

SHOTS = ROOT / 'evidence/local-real-identity-browser'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='dayflare-real-identity-browser-') as scratch:
        parent = Path(scratch)
        (parent / 'Dayflare').mkdir()
        target = parent / 'Dayflare' / SNAPSHOT
        files = build(target)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(parent)))
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}/Dayflare/{SNAPSHOT}/'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                for width in (1280, 390, 320):
                    for js in (True, False):
                        context = browser.new_context(viewport={'width': width, 'height': 900},
                                                      java_script_enabled=js, reduced_motion='reduce')
                        page = context.new_page()
                        page.set_default_timeout(10000)
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        response = page.goto(base, wait_until='networkidle', timeout=20000)
                        assert response.status == 200
                        assert page.locator('article.card').count() == 20
                        assert '2026-11-04 UTC' in page.locator('.notice').inner_text()
                        assert 'not a live refresh' in page.locator('.notice').inner_text()
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                        page.keyboard.press('Tab')
                        assert page.locator(':focus').get_attribute('class') == 'skip'
                        page.keyboard.press('Enter')
                        assert page.locator(':focus').get_attribute('id') == 'records'
                        page.goto(base, wait_until='networkidle')
                        page.screenshot(path=str(SHOTS / f'real-identity-overview-{width}-js{int(js)}.png'))
                        page.get_by_role('navigation').get_by_role('link', name='Books', exact=True).click()
                        assert page.url.endswith('#books')
                        record = page.locator('#books article').first
                        summary = record.locator('summary')
                        summary.focus()
                        page.keyboard.press('Enter')
                        assert record.locator('details').get_attribute('open') is not None
                        assert '2026-11-04T10:31:' in record.locator('details').inner_text()
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                        record.screenshot(path=str(SHOTS / f'real-identity-evidence-{width}-js{int(js)}.png'))
                        permalink = record.get_by_role('link', name='Link to this dated record').get_attribute('href')
                        assert permalink.startswith('#' + SNAPSHOT)
                        page.goto(base + permalink, wait_until='networkidle')
                        assert page.locator(permalink).get_attribute('id') == permalink[1:]
                        assert page.locator(permalink).bounding_box()['y'] >= 0
                        # All same-origin evidence and download links must resolve byte-for-byte.
                        hrefs = set(page.locator('a[href]').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))'))
                        for href in hrefs:
                            if href.startswith('#'):
                                assert page.locator(href).count() == 1
                            elif not urlsplit(href).scheme:
                                reply = page.request.get(urljoin(base, href))
                                assert reply.status == 200
                                assert reply.body() == files[href]
                        assert page.request.get(base + 'source/raw/missing.json').status == 404
                        assert not errors, errors
                        context.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
    print('PASS real retained metadata: native HTTP /Dayflare/, 320/390/1280, JS/no-JS, keyboard, exact sources and no overflow')
    print('NOT VERIFIED: public Pages, second observation date or independent Wikimedia transport authenticity')


if __name__ == '__main__':
    main()
