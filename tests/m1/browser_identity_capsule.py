"""Native HTTP Chromium acceptance; synthetic fixture or pinned historical replay."""
from __future__ import annotations

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.m1_identity_capsule import build_capsule, digest, unpack_capsule
from tools.m1_identity_capsule_demo import fixture_bundle, SYNTHETIC_REVISION
from playwright.sync_api import sync_playwright
from check_identity_capsule_real import check as check_real


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-source', type=Path, help='accepted 4-Nov baseline source directory')
    args = parser.parse_args()
    kind = 'real' if args.real_source else 'synthetic'
    screenshots = ROOT / 'evidence' / ('local-capsule-' + kind + '-browser')
    screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        if args.real_source:
            check_real(args.real_source, root / 'replay')
            raw = (root / 'replay/identity-evidence-20261104.zip').read_bytes()
            count, date = 20, '2026-11-04'
            badge = 'REPORTED RETRIEVAL'
        else:
            bundle = fixture_bundle(root / 'source')
            raw = build_capsule(bundle, source_revision=SYNTHETIC_REVISION,
                                evidence_kind='synthetic_test_fixture')
            count, date = 19, '2026-10-01'
            badge = 'SYNTHETIC TEST FIXTURE'
        unpack_capsule(raw, digest(raw), root / 'Dayflare')
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as playwright:
                executable = os.environ.get('DAYFLARE_BROWSER_EXECUTABLE')
                browser = playwright.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
                try:
                    for width in (1280, 390, 320):
                        for javascript in (True, False):
                            context = browser.new_context(viewport={'width': width, 'height': 900},
                                                          java_script_enabled=javascript, reduced_motion='reduce')
                            page = context.new_page()
                            page.set_default_timeout(10000)
                            external, errors = [], []
                            page.on('request', lambda req: external.append(req.url) if not req.url.startswith(origin + '/') else None)
                            page.on('pageerror', lambda exc: errors.append(str(exc)))
                            response = page.goto(origin + '/Dayflare/', wait_until='load')
                            assert response and response.status == 200
                            assert page.locator('h1').inner_text() == 'Inspect the evidence behind a page identity.'
                            assert badge in page.locator('.notice').first.inner_text()
                            assert date in page.locator('.notice').first.inner_text()
                            assert 'Retrieval completion time: unavailable' in page.locator('main').inner_text()
                            assert page.locator('article').count() == count
                            assert f'{count} / 20' in page.locator('.stats').inner_text()
                            if not args.real_source:
                                assert page.locator('section').filter(has_text='Unavailable selected identities').count() >= 1
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                            label = f'capsule-{kind}-{width}-' + ('js' if javascript else 'nojs')
                            page.screenshot(path=str(screenshots / (label + '-overview.png')))
                            page.keyboard.press('Tab')
                            assert page.evaluate('document.activeElement.className') == 'skip'
                            page.keyboard.press('Enter')
                            assert page.evaluate('document.activeElement.id') == 'identities'
                            first = page.locator('article').first
                            summary = first.locator('summary')
                            summary.focus()
                            page.keyboard.press('Enter')
                            assert first.locator('details').get_attribute('open') is not None
                            assert 'batchcomplete' in first.locator('pre').inner_text()
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                            first.screenshot(path=str(screenshots / (label + '-source.png')))
                            link = first.get_by_role('link', name='Link to this identity')
                            anchor = link.get_attribute('href')
                            link.click()
                            page.reload(wait_until='load')
                            assert page.url.endswith(anchor)
                            # Project IDs contain dots: a URL fragment is not a CSS selector.
                            target = page.locator('article[id=' + json.dumps(anchor[1:]) + ']')
                            assert target.count() == 1
                            assert target.get_attribute('id') == first.get_attribute('id')
                            assert 0 <= target.bounding_box()['y'] < 90
                            raw_href = first.get_by_role('link', name='Retained source JSON').get_attribute('href')
                            source = context.request.get(origin + '/Dayflare/' + raw_href)
                            assert source.status == 200
                            assert source.body() == (root / 'Dayflare' / raw_href).read_bytes()
                            assert context.request.get(origin + '/Dayflare/missing-source.json').status == 404
                            assert not external, external
                            assert not errors, errors
                            context.close()
                    print(f'PASS ({kind}): 6 native HTTP Chromium journeys; 320/390/1280; JS/no-JS; keyboard, source bytes, anchors, unknown mappings and no overflow.')
                    print('VISUAL: 12 actual-runtime screenshots at ' + str(screenshots))
                    print('NOT VERIFIED: new Wikimedia acquisition, network origin or public Pages.')
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
