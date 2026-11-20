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

        # Preserve offline default order; discover signed weekly gains and losses.
        order = page.get_by_label('Order by requests or measured change')
        def deltas():
            return page.locator('.tile').evaluate_all(
                '(nodes) => nodes.map(n => Number(n.dataset.delta))')
        original = deltas()
        assert len(original) == 30
        assert original == sorted(original, key=lambda d: -abs(d))
        assert any(d > 0 for d in original) and any(d < 0 for d in original)
        order.select_option('increase')
        assert deltas() == sorted(original, reverse=True)
        assert_no_horizontal_overflow(page, 'increase-sorted', width)
        order.select_option('decrease')
        assert deltas() == sorted(original)
        assert_no_horizontal_overflow(page, 'decrease-sorted', width)
        order.select_option('volume')
        volumes = page.locator('.tile').evaluate_all(
            '(nodes) => nodes.map(n => Number(n.dataset.volume))')
        assert len(volumes) == 30 and all(v >= 0 for v in volumes)
        assert volumes == sorted(volumes, reverse=True)
        exact_volumes = page.locator('.tile').evaluate_all(
            '(nodes) => nodes.map(n => Number(n.querySelector(".metrics strong").textContent.replaceAll(",", "")))')
        assert volumes == exact_volumes, (volumes, exact_volumes)
        assert_no_horizontal_overflow(page, 'volume-sorted', width)
        order.select_option('magnitude')
        assert deltas() == original

        # Exact filtered export follows the rendered, sorted stable-ID cards.
        visible_export = page.locator('#download-visible')
        assert visible_export.is_visible()
        def visible_records():
            csv_href = visible_export.get_attribute('href')
            assert csv_href and csv_href.startswith('data:text/csv;charset=utf-8,')
            return list(csv.reader(StringIO(unquote(csv_href.split(',', 1)[1]))))
        source = page.locator('script#dataset').evaluate('(e) => JSON.parse(e.textContent)')
        all_records = visible_records()
        assert len(all_records) == 30 * 35 + 1
        assert all_records[0] == ['utc_date', 'project_page_id', 'requests',
                                  'dataset_id', 'method_version']
        first_id = page.locator('.tile').first.get_attribute('data-page-id')
        assert all_records[1] == [source['dates'][0], first_id,
                                  str(source['rows'][first_id]['values'][0]), dataset, method]
        with page.expect_download(timeout=10000) as downloaded:
            visible_export.click()
        assert downloaded.value.suggested_filename == 'dayflare-30-visible.csv'
        assert_no_horizontal_overflow(page, 'full-visible-export', width)

        search = page.get_by_role('searchbox', name='Search selected articles')
        search.fill('this-text-should-match-no-real-topic-12345')
        assert page.locator('.tile:visible').count() == 0
        assert page.locator('#no-results').is_visible()
        assert page.locator('#result-count').inner_text() == '0 of 30 histories'
        assert visible_export.is_hidden() and visible_export.get_attribute('href') == ''
        screenshot(page, width, 'empty')
        search.fill('')
        assert page.locator('#no-results').is_hidden()
        page.get_by_label('Wikipedia edition').select_option('RU')
        visible = page.locator('.tile:visible')
        assert 0 < visible.count() < 30
        assert all(e == 'RU' for e in visible.evaluate_all('(nodes) => nodes.map(n => n.dataset.edition)'))
        ru_records = visible_records()
        assert len(ru_records) == 15 * 35 + 1
        selected = set(visible.evaluate_all('(nodes) => nodes.map(n => n.dataset.pageId)'))
        assert all(row[1] in selected and row[1].startswith('ru.wikipedia:')
                   for row in ru_records[1:])
        assert ru_records[1][2] == str(source['rows'][ru_records[1][1]]['values'][0])
        page.get_by_label('Wikipedia edition').select_option('')
        assert page.locator('.tile:visible').count() == 30
        assert len(visible_records()) == 1051

        # A Russian Cyrillic ё title remains discoverable when the keyboard types е.
        # Search equivalence is never used as evidence for changing page identity.
        assert page.locator('#search-hint').is_visible()
        yo_candidates = page.locator('.tile[data-edition="RU"]').evaluate_all(
            "(nodes) => nodes.filter(n => /ё/i.test(n.dataset.text)).map(n => n.id)")
        assert yo_candidates, 'The retained RU cohort must contain a ё spelling example'
        yo_tile = page.locator('#' + yo_candidates[0])
        source_title = yo_tile.locator('h3').inner_text()
        query = source_title.replace('ё', 'е').replace('Ё', 'Е')
        search.fill(query)
        assert search.input_value() == query
        assert yo_tile.is_visible()
        assert yo_tile.locator('h3').inner_text() == source_title
        page.get_by_label('Wikipedia edition').select_option('EN')
        assert yo_tile.is_hidden()
        page.get_by_label('Wikipedia edition').select_option('RU')
        assert yo_tile.is_visible()
        assert_no_horizontal_overflow(page, 'russian-yo-search', width)
        search.fill('')
        page.get_by_label('Wikipedia edition').select_option('')
        assert page.locator('.tile:visible').count() == 30

        # Real card-to-pair journey: preserve a stable ID, navigate and focus the second field.
        shortcut = page.locator('.tile').first.locator('.compare-jump')
        target_id = shortcut.get_attribute('data-compare-id')
        if width == 390:
            shortcut.focus()
            page.keyboard.press('Enter')
        else:
            shortcut.click()
        assert page.url.endswith('#compare')
        assert page.locator('#left').input_value() == target_id
        assert page.locator('#right').input_value() == ''
        assert page.locator('#right').evaluate('(e) => document.activeElement === e')
        assert page.locator('#download-csv').is_hidden()
        assert 'Choose a second article' in page.locator('#compare-message').inner_text()
        assert_no_horizontal_overflow(page, 'card-to-comparison', width)

        article = page.locator('.tile').first
        article.locator('summary').click()
        assert article.locator('details').evaluate('(e) => e.open')
        assert article.locator('.tables table').count() == 2
        assert article.locator('.tables table').nth(1).locator('tbody tr').count() == 35
        assert article.locator('.links a').count() == 3
        single = article.locator('.article-csv')
        assert single.is_visible()
        single_href = single.get_attribute('href')
        assert single_href and single_href.startswith('data:text/csv;charset=utf-8,')
        single_records = list(csv.reader(StringIO(unquote(single_href.split(',', 1)[1]))))
        single_id = article.get_attribute('data-page-id')
        assert len(single_records) == 36
        assert single_records[0] == ['utc_date', 'project_page_id', 'requests',
                                     'dataset_id', 'method_version']
        assert single_records[1] == [source['dates'][0], single_id,
                                     str(source['rows'][single_id]['values'][0]), dataset, method]
        assert single_records[-1] == [source['dates'][-1], single_id,
                                      str(source['rows'][single_id]['values'][-1]), dataset, method]
        with page.expect_download(timeout=10000) as downloaded_single:
            single.click()
        assert downloaded_single.value.suggested_filename.startswith('dayflare-')
        assert downloaded_single.value.suggested_filename.endswith('-35day.csv')
        screenshot(page, width, 'detail')
        assert_no_horizontal_overflow(page, 'detail', width)

        left = page.locator('#left')
        right = page.locator('#right')
        options = left.locator('option').evaluate_all('(nodes) => nodes.map(n => n.value).filter(Boolean)')
        assert len(options) == 30 and options[0] != options[1]
        left.select_option(options[0])
        right.select_option(options[0])
        assert page.locator('#download-csv').is_hidden()
        assert page.locator('#share-summary').is_hidden()
        assert page.locator('#copy-summary').is_hidden()
        right.select_option(options[1])
        assert page.locator('#comparison > table tbody tr').count() == 5
        chart = page.locator('#comparison .pair-chart')
        assert chart.is_visible()
        assert 'One shared zero-based scale' in chart.locator('figcaption').inner_text()
        assert chart.locator('.pair-week').count() == 5
        assert chart.locator('.pair-weeks').get_attribute('aria-hidden') == 'true'
        bars = chart.locator('.pair-bar').evaluate_all('(nodes) => nodes.map(n => parseFloat(n.style.height))')
        assert len(bars) == 10 and all(0 <= h <= 112 for h in bars)
        assert abs(max(bars) - 112) < 0.00001
        export = page.locator('#download-csv')
        assert export.is_visible()
        href = export.get_attribute('href')
        assert href and href.startswith('data:text/csv;charset=utf-8,')
        records = list(csv.reader(StringIO(unquote(href.split(',', 1)[1]))))
        assert len(records) == 36
        assert records[0] == ['utc_date', 'left_page_id', 'left_requests', 'right_page_id',
                              'right_requests', 'dataset_id', 'method_version']
        observed = page.locator('script#dataset').evaluate('(e) => JSON.parse(e.textContent)')
        text_summary = page.locator('#share-summary')
        assert text_summary.is_visible()
        assert page.locator('#copy-summary').is_visible()
        evidence = text_summary.input_value()
        assert observed['dataset'] in evidence and observed['method'] in evidence
        assert observed['retrieved'] in evidence
        assert options[0] in evidence and options[1] in evidence
        assert observed['rows'][options[0]]['source_url'] in evidence
        assert observed['rows'][options[1]]['body_sha256'] in evidence
        for pos, identity in enumerate((options[0], options[1])):
            entry = observed['rows'][identity]
            totals = [sum(entry['values'][i:i + 7]) for i in (0, 7, 14, 21, 28)]
            baseline = sorted(totals[:4])
            middle = (baseline[1] + baseline[2]) / 2
            delta = totals[4] - middle
            label = ('A' if pos == 0 else 'B') + ': '
            assert label + entry['edition'] + ' Wikipedia' in evidence
            for i, n in enumerate(totals):
                assert (f'W{i + 1} {observed["dates"][i * 7]}–'
                        f'{observed["dates"][i * 7 + 6]} UTC: {n:,} requests') in evidence
            signed = ('+' if delta > 0 else '') + f'{delta:,.1f}'.rstrip('0').rstrip('.')
            assert f'W5 minus median: {signed} requests' in evidence
        assert 'not unique people' in evidence
        page.locator('#copy-summary').click()
        page.wait_for_function("document.getElementById('compare-message').textContent.toLowerCase().includes('summary')")
        daily = chart.locator('details.pair-daily')
        assert daily.count() == 1 and not daily.evaluate('(e) => e.open')
        daily.locator('summary').focus()
        page.keyboard.press('Enter')
        assert daily.evaluate('(e) => e.open')
        daily_rows = daily.locator('table tbody tr')
        assert daily_rows.count() == 35
        assert daily.locator('table thead th').all_inner_texts() == ['UTC date', 'A · EN' if observed['rows'][options[0]]['edition'] == 'EN' else 'A · RU',
                                                                    'B · EN' if observed['rows'][options[1]]['edition'] == 'EN' else 'B · RU']
        for index in (0, 17, 34):
            cells = daily_rows.nth(index).locator('th,td').all_inner_texts()
            assert cells == [observed['dates'][index],
                             f"{observed['rows'][options[0]]['values'][index]:,}",
                             f"{observed['rows'][options[1]]['values'][index]:,}"], (width, index, cells)
        screenshot(page, width, 'comparison-daily')
        assert_no_horizontal_overflow(page, 'comparison-daily', width)
        daily.locator('summary').click()
        assert not daily.evaluate('(e) => e.open')
        for week in range(5):
            exact = f"{observed['dates'][week * 7]}–{observed['dates'][week * 7 + 6]} UTC"
            static_label = page.locator('.tile').first.locator('.tables table').first.locator('tbody th').nth(week)
            compare_label = page.locator('#comparison > table tbody th').nth(week)
            assert exact in static_label.inner_text(), (week, static_label.inner_text())
            assert exact in compare_label.inner_text(), (week, compare_label.inner_text())
            assert f'W{week + 1}' in compare_label.inner_text()
        assert 'W1–W5 map to inclusive UTC date ranges' in chart.locator('figcaption').inner_text()
        for index, record in enumerate(records[1:]):
            assert record == [observed['dates'][index], options[0],
                              str(observed['rows'][options[0]]['values'][index]), options[1],
                              str(observed['rows'][options[1]]['values'][index]),
                              dataset, method]
        with page.expect_download(timeout=10000) as downloaded:
            export.click()
        assert downloaded.value.suggested_filename == 'dayflare-30-pair.csv'
        assert page.locator('#invalid-link').is_hidden()
        # Type rather than fill: live input must retain the word separator and caret.
        search.fill('')
        search.press_sequentially('Black hole', delay=10)
        assert search.input_value() == 'Black hole'
        assert page.locator('.tile:visible').count() >= 1
        page.get_by_label('Wikipedia edition').select_option('EN')
        order.select_option('volume')
        assert page.locator('.tile:visible').count() >= 1
        share = page.locator('#share-field').input_value()
        params = dict(parse_qsl(urlsplit(share).query, keep_blank_values=True))
        assert params == {'dataset': dataset, 'method': method, 'left': options[0], 'right': options[1],
                          'q': 'Black hole', 'ed': 'EN', 'order': 'volume'}
        screenshot(page, width, 'comparison')
        assert_no_horizontal_overflow(page, 'comparison', width)

        restored = page.goto(share, wait_until='load', timeout=18000)
        assert restored and restored.status == 200
        assert page.locator('#comparison > table tbody tr').count() == 5
        assert page.locator('#left').input_value() == options[0]
        assert page.locator('#right').input_value() == options[1]
        assert page.locator('#invalid-link').is_hidden()
        assert page.locator('#search').input_value() == 'Black hole'
        assert page.locator('#edition').input_value() == 'EN'
        assert page.locator('#sort').input_value() == 'volume'
        assert page.locator('.tile:visible').count() >= 1
        assert_no_horizontal_overflow(page, 'rich-share-restored', width)

        # Existing four-key URLs remain valid and restore default discovery controls.
        parts = urlsplit(share)
        legacy_keys = {'dataset', 'method', 'left', 'right'}
        legacy = urlunsplit(parts._replace(query=urlencode(
            [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key in legacy_keys])))
        legacy_response = page.goto(legacy, wait_until='load', timeout=18000)
        assert legacy_response and legacy_response.status == 200
        assert page.locator('#comparison > table tbody tr').count() == 5
        assert page.locator('#search').input_value() == ''
        assert page.locator('#edition').input_value() == ''
        assert page.locator('#sort').input_value() == 'magnitude'
        assert page.locator('#invalid-link').is_hidden()

        invalid = page.goto(stale_dataset_url(share), wait_until='load', timeout=18000)
        assert invalid and invalid.status == 200
        assert page.locator('#invalid-link').is_visible()
        assert page.locator('#download-csv').is_hidden()
        assert page.locator('#share-summary').is_hidden()
        assert page.locator('#copy-summary').is_hidden()
        assert 'Incompatible' in page.locator('#compare-message').inner_text()
        screenshot(page, width, 'incompatible')
        page.locator('#left').select_option(options[0])
        page.locator('#right').select_option(options[1])
        assert page.locator('#comparison > table tbody tr').count() == 5
        assert page.locator('#invalid-link').is_hidden()
        assert page.locator('#download-csv').is_visible()
        assert page.locator('#share-summary').is_visible()
        assert 'no-longer-this-dataset' not in page.locator('#share-field').input_value()
        screenshot(page, width, 'recovered')
        assert_no_horizontal_overflow(page, 'recovered', width)
        # Switching from an existing pair to its selected second card must clear the duplicate.
        page.locator('.compare-jump[data-compare-id="' + options[1] + '"]').click()
        assert page.locator('#left').input_value() == options[1]
        assert page.locator('#right').input_value() == ''
        assert page.locator('#comparison').locator('table').count() == 0
        assert page.locator('#download-csv').is_hidden()
        assert page.locator('#share-summary').is_hidden()
        assert page.locator('#copy-summary').is_hidden()
        assert page.locator('#invalid-link').is_hidden()
        assert not errors, errors
        assert requests and all(urlsplit(request).hostname == '127.0.0.1' for request in requests), requests
    finally:
        context.close()


def no_javascript(browser, url: str) -> None:
    context = browser.new_context(viewport={'width': 390, 'height': 840},
                                  java_script_enabled=False, reduced_motion='reduce',
                                  accept_downloads=True)
    try:
        page = context.new_page()
        response = page.goto(url, wait_until='load', timeout=18000)
        assert response and response.status == 200
        assert page.locator('.tile').count() == 30
        # No-JS pages have all measured tables, but no dead search/compare buttons.
        assert page.locator('.controls').is_hidden()
        assert page.locator('#compare').is_hidden()
        assert page.locator('.compare-jump').first.is_hidden()
        # Playwright text selectors skip <noscript> even when the browser renders it.
        note = page.locator('noscript p.warning[role="note"]')
        assert note.is_visible()
        assert note.locator('strong').inner_text() == 'JavaScript is disabled.'
        assert 'All 30 selected articles' in note.inner_text()
        article = page.locator('.tile').first
        article.locator('summary').click()
        assert article.locator('.tables table').nth(1).locator('tbody tr').count() == 35
        assert article.locator('.tables table').first.locator('tbody .week-date').count() == 5
        static_csv = article.locator('.article-csv')
        assert static_csv.is_visible(), 'No-JS article export must remain usable'
        csv_href = static_csv.get_attribute('href')
        assert csv_href and csv_href.startswith('data:text/csv;charset=utf-8,')
        csv_rows = list(csv.reader(StringIO(unquote(csv_href.split(',', 1)[1]))))
        assert len(csv_rows) == 36
        assert csv_rows[0] == ['utc_date', 'project_page_id', 'requests',
                               'dataset_id', 'method_version']
        assert all(record[1] == article.get_attribute('data-page-id') for record in csv_rows[1:])
        static_csv.focus()
        assert static_csv.evaluate('(e) => document.activeElement === e')
        with page.expect_download(timeout=10000) as downloaded_static:
            page.keyboard.press('Enter')
        assert downloaded_static.value.suggested_filename.endswith('-35day.csv')
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
    expected = {f'{width}-{state}.png' for width in WIDTHS
                for state in ('overview', 'empty', 'detail', 'comparison-daily',
                              'comparison', 'incompatible', 'recovered')}
    expected.add('390-nojs.png')
    assert {p.name for p in images} == expected, [p.name for p in images]
    print(json.dumps({'status': 'LOCAL_HTTP_CHROMIUM_PASS_UNPUBLISHED',
                      'screenshots': len(images), 'widths': WIDTHS,
                      'dataset': candidate['dataset_id']}, sort_keys=True))


if __name__ == '__main__':
    main()
