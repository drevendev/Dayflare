"""Read-only real Chromium HTTP acceptance of the *unpublished* 30-title reader.

Exercises repository-retained, exact-byte data; not an M0 mock, GitHub Pages
deployment, or an external Wikimedia request.
"""
from __future__ import annotations

import csv
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from browser_m0_http import server
from browser_runner import launch_chromium
from tools.m1_30_reader import render
from tools.m1_30_retained_candidate import read_candidate

WIDTHS = (320, 390, 1280)
OUT = ROOT / 'artifacts' / 'm0-http' / '30-reader'


def screenshot(page, width: int, state: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f'{width}-{state}.png'), full_page=True)


def assert_no_horizontal_overflow(page, state: str, width: int) -> None:
    actual = page.evaluate('({viewport: innerWidth, document: document.documentElement.scrollWidth})')
    assert actual['document'] <= actual['viewport'], (width, state, actual)


def stale_dataset_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(key, 'no-longer-this-dataset' if key == 'dataset' else value)
             for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit(parts._replace(query=urlencode(query)))


def visitor(browser, url: str, width: int, dataset: str, method: str) -> None:
    context = browser.new_context(viewport={'width': width, 'height': 840},
                                  reduced_motion='reduce', accept_downloads=True)
    errors, requests = [], []
    try:
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: requests.append(r.url))
        response = page.goto(url, wait_until='load', timeout=18000)
        assert response and response.status == 200
        assert page.locator('h1').count() == 1
        assert page.locator('.tile').count() == 30
        assert 'OFFLINE' in page.locator('body').inner_text()
        assert page.locator('script#dataset').count() == 1
        assert page.locator('script#dataset').evaluate('(e) => JSON.parse(e.textContent).dataset') == dataset
        assert page.locator('#result-count').inner_text() == '30 of 30 histories'
        screenshot(page, width, 'overview')
        assert_no_horizontal_overflow(page, 'overview', width)

        if width == 390:
            page.keyboard.press('Tab')
            assert page.locator('.skip').evaluate('(e) => document.activeElement === e')
            page.keyboard.press('Enter')
            assert page.url.endswith('#discover')
            page.get_by_role('searchbox', name='Search selected articles').focus()
            assert page.get_by_role('searchbox').evaluate('(e) => document.activeElement === e')

        search = page.get_by_role('searchbox', name='Search selected articles')
        search.fill('this-text-should-match-no-real-topic-12345')
        assert page.locator('.tile:visible').count() == 0
        assert page.locator('#no-results').is_visible()
        assert page.locator('#result-count').inner_text() == '0 of 30 histories'
        screenshot(page, width, 'empty')
        search.fill('')
        assert page.locator('#no-results').is_hidden()
        page.get_by_label('Wikipedia edition').select_option('RU')
        visible = page.locator('.tile:visible')
        assert 0 < visible.count() < 30
        assert all(e == 'RU' for e in visible.evaluate_all('(nodes) => nodes.map(n => n.dataset.edition)'))
        page.get_by_label('Wikipedia edition').select_option('')
        assert page.locator('.tile:visible').count() == 30

        article = page.locator('.tile').first
        article.locator('summary').click()
        assert article.locator('details').evaluate('(e) => e.open')
        assert article.locator('.tables table').count() == 2
        assert article.locator('.tables table').nth(1).locator('tbody tr').count() == 35
        assert article.locator('.links a').count() == 3
        screenshot(page, width, 'detail')
        assert_no_horizontal_overflow(page, 'detail', width)

        left = page.locator('#left')
        right = page.locator('#right')
        options = left.locator('option').evaluate_all('(nodes) => nodes.map(n => n.value).filter(Boolean)')
        assert len(options) == 30 and options[0] != options[1]
        left.select_option(options[0])
        right.select_option(options[0])
        assert page.locator('#download-csv').is_hidden()
        right.select_option(options[1])
        assert page.locator('#comparison table tbody tr').count() == 5
        export = page.locator('#download-csv')
        assert export.is_visible()
        href = export.get_attribute('href')
        assert href and href.startswith('data:text/csv;charset=utf-8,')
        records = list(csv.reader(StringIO(unquote(href.split(',', 1)[1]))))
        assert len(records) == 36
        assert records[0] == ['utc_date', 'left_page_id', 'left_requests', 'right_page_id',
                              'right_requests', 'dataset_id', 'method_version']
        observed = page.locator('script#dataset').evaluate('(e) => JSON.parse(e.textContent)')
        for index, record in enumerate(records[1:]):
            assert record == [observed['dates'][index], options[0],
                              str(observed['rows'][options[0]]['values'][index]), options[1],
                              str(observed['rows'][options[1]]['values'][index]),
                              dataset, method]
        with page.expect_download(timeout=10000) as downloaded:
            export.click()
        assert downloaded.value.suggested_filename == 'dayflare-30-pair.csv'
        assert page.locator('#invalid-link').is_hidden()
        share = page.locator('#share-field').input_value()
        params = dict(parse_qsl(urlsplit(share).query))
        assert params == {'dataset': dataset, 'method': method, 'left': options[0], 'right': options[1]}
        screenshot(page, width, 'comparison')
        assert_no_horizontal_overflow(page, 'comparison', width)

        restored = page.goto(share, wait_until='load', timeout=18000)
        assert restored and restored.status == 200
        assert page.locator('#comparison table tbody tr').count() == 5
        assert page.locator('#left').input_value() == options[0]
        assert page.locator('#right').input_value() == options[1]
        assert page.locator('#invalid-link').is_hidden()

        invalid = page.goto(stale_dataset_url(share), wait_until='load', timeout=18000)
        assert invalid and invalid.status == 200
        assert page.locator('#invalid-link').is_visible()
        assert page.locator('#download-csv').is_hidden()
        assert 'Incompatible' in page.locator('#compare-message').inner_text()
        screenshot(page, width, 'incompatible')
        page.locator('#left').select_option(options[0])
        page.locator('#right').select_option(options[1])
        assert page.locator('#comparison table tbody tr').count() == 5
        assert page.locator('#invalid-link').is_hidden()
        assert page.locator('#download-csv').is_visible()
        assert 'no-longer-this-dataset' not in page.locator('#share-field').input_value()
        screenshot(page, width, 'recovered')
        assert_no_horizontal_overflow(page, 'recovered', width)
        assert not errors, errors
        assert requests and all(urlsplit(request).hostname == '127.0.0.1' for request in requests), requests
    finally:
        context.close()


def no_javascript(browser, url: str) -> None:
    context = browser.new_context(viewport={'width': 390, 'height': 840},
                                  java_script_enabled=False, reduced_motion='reduce')
    try:
        page = context.new_page()
        response = page.goto(url, wait_until='load', timeout=18000)
        assert response and response.status == 200
        assert page.locator('.tile').count() == 30
        # No-JS pages have all measured tables, but no dead search/compare buttons.
        assert page.locator('.controls').is_hidden()
        assert page.locator('#compare').is_hidden()
        # Playwright text selectors skip <noscript> even when the browser renders it.
        note = page.locator('noscript p.warning[role="note"]')
        assert note.is_visible()
        assert note.locator('strong').inner_text() == 'JavaScript is disabled.'
        assert 'All 30 selected articles' in note.inner_text()
        article = page.locator('.tile').first
        article.locator('summary').click()
        assert article.locator('.tables table').nth(1).locator('tbody tr').count() == 35
        assert_no_horizontal_overflow(page, 'nojs', 390)
        screenshot(page, 390, 'nojs')
    finally:
        context.close()


def main() -> None:
    _, candidate = read_candidate()
    html = render(candidate)
    assert html == render(candidate), 'nondeterministic reader build'
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dayflare-30-http-') as tmp:
        site = Path(tmp) / 'Dayflare'
        site.mkdir()
        (site / 'reader.html').write_bytes(html)
        with server(Path(tmp)) as root:
            with sync_playwright() as playwright:
                browser = launch_chromium(playwright)
                try:
                    for width in WIDTHS:
                        visitor(browser, root + 'reader.html', width,
                                candidate['dataset_id'], candidate['method_version'])
                    no_javascript(browser, root + 'reader.html')
                finally:
                    browser.close()
    images = sorted(OUT.glob('*.png'))
    assert len(images) == 19, [p.name for p in images]
    print(json.dumps({'status': 'LOCAL_HTTP_CHROMIUM_PASS_UNPUBLISHED',
                      'screenshots': len(images), 'widths': WIDTHS,
                      'dataset': candidate['dataset_id']}, sort_keys=True))


if __name__ == '__main__':
    main()
