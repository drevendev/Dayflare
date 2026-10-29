"""Chromium visitor acceptance of independently pinned gh-pages M1 *branch bytes*.

This serves a checked-out branch on numeric loopback; PASS is never public
HTTP/Pages deployment evidence. The sibling manifest gate must run first.
"""
from __future__ import annotations

import argparse
import csv
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit, urlunsplit, urlencode, urljoin

from playwright.sync_api import expect, sync_playwright


def rows(download):
    with Path(download.path()).open('r', encoding='utf-8-sig', newline='') as stream:
        return list(csv.reader(stream))


def geometry(page, width):
    actual = page.evaluate('document.documentElement.scrollWidth')
    assert actual <= width, f'Horizontal page overflow {actual}px > viewport {width}px'


def run(root: Path, screenshots: Path):
    screenshots.mkdir(parents=True, exist_ok=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(root.resolve()))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}/m1/'
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for width, height in ((1280, 850), (390, 844), (320, 700)):
                # Data/evidence must stay usable without JS or interactions.
                page = browser.new_page(viewport={'width':width, 'height':height},
                                        java_script_enabled=False, reduced_motion='reduce')
                response = page.goto(url, wait_until='domcontentloaded')
                assert response and response.status == 200
                expect(page.locator('h1')).to_have_text('Where did attention change?')
                expect(page.locator('.card')).to_have_count(20)
                expect(page.locator('article')).to_have_count(20)
                expect(page.locator('#compare-table tbody tr')).to_have_count(20)
                expect(page.locator('tbody tr')).to_have_count(720)
                expect(page.locator('#atlas-filters')).to_be_hidden()
                expect(page.locator('#compare-csv')).to_be_hidden()
                assert 'DATED SOURCE EVIDENCE' in page.locator('header').inner_text()
                geometry(page, width)
                page.keyboard.press('Tab')
                assert page.evaluate('document.activeElement.classList.contains("skip")')
                assert page.locator('.skip').evaluate('(el) => getComputedStyle(el).outlineStyle') != 'none'
                page.screenshot(path=str(screenshots / f'm1-release-nojs-{width}.png'),
                                full_page=False)
                page.close()

            page = browser.new_page(viewport={'width':390, 'height':844},
                                    accept_downloads=True, reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            response = page.goto(url, wait_until='domcontentloaded')
            assert response and response.status == 200
            expect(page.locator('#atlas-filters')).to_be_visible()
            expect(page.locator('.card:visible')).to_have_count(20)
            expect(page.locator('#compare-table tbody tr:visible')).to_have_count(20)
            csv_button = page.get_by_role('button', name='Download visible weekly CSV')
            expect(csv_button).to_be_enabled()
            with page.expect_download() as all_download:
                csv_button.click()
            all_rows = rows(all_download.value)
            assert len(all_rows) == 21 and len(all_rows[0]) == 13, '20 data rows + exact schema required'
            assert all_rows[0][0] == 'dataset_sha256' and all_rows[0][6] == 'subject'
            assert all_rows[0][7].endswith('_requests') and all_rows[0][11].endswith('_requests')
            dataset = page.locator('#share-restore').get_attribute('data-dataset')
            assert all(row[0] == dataset for row in all_rows[1:])
            assert {row[4] for row in all_rows[1:]} == {'en.wikipedia', 'ru.wikipedia'}

            page.locator('#atlas-edition').select_option('ru.wikipedia')
            expect(page.locator('.card:visible')).to_have_count(10)
            expect(page.locator('#compare-table tbody tr:visible')).to_have_count(10)
            russian = page.locator('.card:visible').first.get_attribute('data-title')
            assert russian
            page.locator('#atlas-query').fill(russian)
            selected = page.locator('.card:visible').count()
            assert 1 <= selected <= 10
            expect(page.locator('#compare-table tbody tr:visible')).to_have_count(selected)
            with page.expect_download() as ru_download:
                csv_button.click()
            selected_rows = rows(ru_download.value)
            assert len(selected_rows) == selected + 1
            assert all(row[4] == 'ru.wikipedia' and russian.casefold() in row[5].casefold()
                       for row in selected_rows[1:])
            assert any(ord(c) > 127 for c in russian), 'test an actual Cyrillic title'
            filtered_url = page.locator('#atlas-filter-link').get_attribute('href')
            assert filtered_url and 'af_dataset=' in filtered_url
            page.goto(filtered_url, wait_until='domcontentloaded')
            expect(page.locator('#atlas-edition')).to_have_value('ru.wikipedia')
            expect(page.locator('#atlas-query')).to_have_value(russian)
            expect(page.locator('.card:visible')).to_have_count(selected)
            expect(page.locator('#compare-table tbody tr:visible')).to_have_count(selected)
            page.screenshot(path=str(screenshots / 'm1-release-filtered-390.png'), full_page=False)

            parts = urlsplit(filtered_url)
            fields = parse_qs(parts.query)
            fields['af_dataset'] = ['0' * 64]
            wrong = urlunsplit((parts.scheme, parts.netloc, parts.path,
                                urlencode(fields, doseq=True), parts.fragment))
            page.goto(wrong, wait_until='domcontentloaded')
            expect(page.locator('#atlas-filter-warning')).to_be_visible()
            expect(page.locator('.card:visible')).to_have_count(20)
            expect(page.locator('#compare-table tbody tr:visible')).to_have_count(20)

            page.locator('#atlas-query').fill('impossible-dayflare-no-result-00000')
            expect(page.locator('.card:visible')).to_have_count(0)
            expect(page.locator('#atlas-empty')).to_be_visible()
            expect(page.locator('#compare-empty')).to_be_visible()
            expect(csv_button).to_be_disabled()
            expect(page.locator('article')).to_have_count(20)
            page.get_by_role('button', name='Show all').click()
            expect(csv_button).to_be_enabled()
            expect(page.locator('.card:visible')).to_have_count(20)

            share_href = page.locator('a[href*="df_dataset="]').first.get_attribute('href')
            assert share_href and dataset in share_href
            page.goto(urljoin(page.url, share_href), wait_until='domcontentloaded')
            expect(page.locator('#share-restore')).to_be_visible()
            assert urlsplit(page.url).fragment == 'share-restore'

            page.goto(url, wait_until='domcontentloaded')
            title = page.locator('#compare-table tbody tr:first-child th a')
            title.evaluate('(el) => { el.textContent = "=HYPERLINK(\\"x\\",\\"y\\")"; }')
            with page.expect_download() as guarded:
                csv_button.click()
            export_rows = rows(guarded.value)
            assert export_rows[1][5].startswith("'=HYPERLINK("), export_rows[1][5]
            page.locator('#compare-table tbody tr:first-child td').first.evaluate(
                '(el) => { el.textContent = "not-a-count"; }')
            csv_button.click()
            expect(page.locator('#compare-csv-status')).to_contain_text('CSV unavailable')
            geometry(page, 390)
            assert not errors, f'Browser JavaScript errors: {errors}'
            page.screenshot(path=str(screenshots / 'm1-release-csv-error-390.png'), full_page=False)
            page.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
    print('PASS: branch-served Chromium M1 release, 1280/390/320 no-JS, '
          '20/700 evidence, RU filters/CSV, share restore, incompatible/empty/invalid paths')
    print('BRANCH_TEST_ONLY: not deployed Pages HTTP or independently reviewed visual screenshots')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--site-root', type=Path, required=True)
    ap.add_argument('--screenshots', type=Path, required=True)
    args = ap.parse_args()
    run(args.site_root, args.screenshots)


if __name__ == '__main__':
    main()
