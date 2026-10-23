"""Run real Chromium on the synthetic M1 fixture (not a public atlas)."""
import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
URL = 'http://127.0.0.1:{port}/site/m1-preview/'
SHOTS = ROOT / 'evidence/local-m1-browser'


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = URL.format(port=server.server_port)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get("CHROMIUM_EXECUTABLE"))
            for width, height in [(1280, 850), (390, 844), (320, 700)]:
                page = browser.new_page(viewport={'width':width,'height':height}, device_scale_factor=1)
                exceptions=[]
                page.on('pageerror', lambda e: exceptions.append(str(e)))
                page.goto(url, wait_until='networkidle')
                expect(page.locator('#count')).to_have_text('6')
                expect(page.locator('#intended')).to_have_text('7')
                expect(page.locator('#unresolved')).to_have_text('1')
                expect(page.locator('.card')).to_have_count(6)
                expect(page.locator('.flags strong')).to_have_text('SYNTHETIC DEMONSTRATION')
                assert not exceptions, exceptions
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), f'horizontal overflow at {width}px'
                if width in (1280,390):
                    page.screenshot(path=str(SHOTS / f'm1-identity-{width}-overview.png'), full_page=True)
                page.get_by_label('Wikipedia edition').select_option('ru.wikipedia')
                expect(page.locator('.card')).to_have_count(2)
                page.locator('.card').first.click()
                expect(page.locator('#detail-help')).to_contain_text('stable page ID')
                assert page.evaluate('document.activeElement.id') == 'details'
                share=page.locator('#share-url').input_value()
                assert 'page=ru.wikipedia%3A' in share and 'panel=synthetic.identity-journey' in share
                page.goto(share, wait_until='networkidle')
                expect(page.locator('.card')).to_have_count(2)
                assert page.locator('.card[aria-pressed="true"]').count() == 1
                page.get_by_label('Find an identity').fill('impossible xyz 000')
                expect(page.locator('#empty')).to_be_visible()
                expect(page.locator('.card')).to_have_count(0)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(SHOTS / f'm1-identity-{width}-empty.png'), full_page=width == 390)
                if width==390:
                    page.get_by_label('Find an identity').fill('')
                    page.locator('.card').first.click()
                    expect(page.locator('#detail-help')).to_contain_text('stable page ID')
                    page.screenshot(path=str(SHOTS / 'm1-identity-390-detail.png'), full_page=True)
                page.close()
            bad=browser.new_page(viewport={'width':390,'height':844})
            bad.goto(url+'?schema=dayflare.identity-panel.v99&panel=synthetic.identity-journey',wait_until='networkidle')
            expect(bad.locator('#compat')).to_be_visible()
            expect(bad.locator('#status')).to_contain_text('no fallback identity')
            bad.locator('#reset').click()
            expect(bad.locator('.card')).to_have_count(6)
            bad.close()
            err=browser.new_page(viewport={'width':390,'height':844})
            err.route('**/site/m1-preview/panel.json',lambda route: route.fulfill(status=200,content_type='application/json',body='{"bad":"tampered"}'))
            err.goto(url,wait_until='networkidle')
            expect(err.locator('#status')).to_contain_text('SHA-256 mismatch')
            expect(err.locator('#retry')).to_be_visible()
            assert err.locator('.card').count()==0
            err.unroute('**/site/m1-preview/panel.json')
            err.locator('#retry').click()
            expect(err.locator('.card')).to_have_count(6)
            err.close()
            nojs=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844}).new_page()
            nojs.goto(url,wait_until='domcontentloaded')
            # Playwright's text matcher intentionally excludes the noscript wrapper.
            # Assert the rendered child paragraph, including visibility and text.
            expect(nojs.locator('noscript > p.noscript')).to_be_visible()
            expect(nojs.locator('noscript > p.noscript')).to_contain_text('optional synthetic identity laboratory needs JavaScript')
            nojs.screenshot(path=str(SHOTS / 'm1-identity-390-nojs.png'), full_page=True)
            nojs.close()
            browser.close()
    finally:
        server.shutdown()
    print('PASS: Chromium 1280/390/320; filters, detail keyboard focus, stable share restore, empty, incompatible, tamper+retry, no-JS; no overflow.')
    print('VISUAL: local source fixture screenshots in', SHOTS)
    print('NOT_RUN: actual M0 source/Pages, real Wikimedia HTTP, and public live-site verification')


if __name__ == '__main__':
    main()
