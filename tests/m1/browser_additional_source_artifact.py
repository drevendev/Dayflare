"""Verify the retained #359 cohort and exercise its archived and rebuilt readers.
No provider requests, release promotion, or live-site claim.
"""
import csv
from functools import partial
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import parse_qs, urljoin, urlsplit
from zipfile import ZipFile

SOURCE = '47f789ce1d09c7597ab27f71a936233c35daea770e8f914301c1925b60a10c42'
PREVIEW = '4b7e2d56d7261339b69c0ca2b63fb905f5cfb697d60f7966df61d1189962ef7e'
DATASET = '4cde167a050fdb0a9d50a1804137f0a0b848f9e3d6ad3cff5f47531c61cac149'
HTML = 'b0703ae3efb6c4c2880aa88fca2a6e177a437d1952063a6d999fc99db0f56305'
IDS = {'en.wikipedia': (6644, 23579, 48193, 333987, 7239234),
       'ru.wikipedia': (7817, 36225, 83471, 149670, 1016844)}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def unpack(path, pin, names, target):
    assert digest(path) == pin
    with ZipFile(path) as archive:
        entries = archive.infolist()
        assert len(entries) == len(names) and {e.filename for e in entries} == names
        assert sum(e.file_size for e in entries) < 2_000_000
        assert archive.testzip() is None
        target.mkdir(parents=True, exist_ok=False)
        for name in sorted(names):
            dest = target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.read(name))


def prepare(root):
    unpack(root / 'source.zip', SOURCE, {'candidate.json', 'seeds.json', 'source-receipt.json'} |
           {f'raw/{p}.{i}.json' for p, ids in IDS.items() for i in ids}, root / 'source')
    unpack(root / 'preview.zip', PREVIEW, {'index.html', 'preview-manifest.json'}, root / 'archived')
    assert digest(root / 'source/candidate.json') == DATASET
    assert digest(root / 'archived/index.html') == HTML
    assert json.loads((root / 'archived/preview-manifest.json').read_bytes())['candidate_sha256'] == DATASET
    assert len(signals(root)) == 10
    print('PASS pinned original source and preview, 10 exact IDs and 350 daily values')


def signals(root):
    candidate = json.loads((root / 'source/candidate.json').read_bytes())
    assert candidate['observation_end'] == '2026-11-24'
    assert candidate['retrieved_at'] == '2026-11-27T17:20:31Z'
    rows = {}
    for row in candidate['series']:
        p, i = row['project'], row['page_id']
        assert i in IDS[p] and row['access'] == 'all-access' and row['agent'] == 'user'
        daily = [d['views'] for d in row['daily']]
        assert len(daily) == 35 and all(type(x) is int and x >= 0 for x in daily)
        weeks = [sum(daily[j:j+7]) for j in range(0, 35, 7)]
        ordered = sorted(weeks[:4])
        key = f'detail-{p.replace(".", "-")}-{i}'
        assert key not in rows
        rows[key] = (weeks, 2*weeks[-1]-ordered[1]-ordered[2], weeks[-1]-weeks[-2])
    assert len(rows) == 10
    assert {k for k, (_, d, s) in rows.items() if d*s < 0} == {'detail-ru-wikipedia-36225'}
    return rows


def browser(root):
    from playwright.sync_api import sync_playwright, expect
    rows = signals(root)
    opposite = 'detail-ru-wikipedia-36225'
    left, right = 'detail-en-wikipedia-6644', 'detail-en-wikipedia-23579'
    output = root / 'browser'; output.mkdir(exist_ok=False)
    receipts = []
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            for edition in ('archived', 'rebuilt'):
                pin = digest(root / edition / 'index.html')
                manifest = json.loads((root / edition / 'preview-manifest.json').read_bytes())
                assert manifest['html_sha256'] == pin and manifest['candidate_sha256'] == DATASET
                assert manifest['series'] == 10 and manifest['publication_status'] == 'LOCAL_PREVIEW_NOT_PUBLISHED'
                url = f'{origin}/{edition}/index.html'
                for width in (320, 390, 1280):
                    context = b.new_context(viewport={'width': width, 'height': 844}, reduced_motion='reduce', service_workers='block')
                    page = context.new_page(); errors = []; external = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.on('request', lambda r: external.append(r.url) if not r.url.startswith(origin + '/') else None)
                    def visit(address):
                        res = page.goto(address, wait_until='load'); assert res and res.status == 200
                        assert sha256(res.body()).hexdigest() == pin
                    def visible(selector):
                        return set(page.locator(selector).evaluate_all('es => es.map(e => e.dataset.series)'))
                    def shot(name):
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                        file = output / f'{edition}-{width}-{name}.png'; page.screenshot(path=str(file))
                        receipts.append({'file': file.name, 'sha256': digest(file)})
                    visit(url)
                    assert visible('.card:not([hidden])') == set(rows)
                    expect(page.locator('article .scroll tbody tr')).to_have_count(350)
                    expect(page.locator('.warning')).to_contain_text('LOCAL EVIDENCE')
                    actual = page.locator('.card').evaluate_all('es => es.map(e => ({...e.dataset}))')
                    assert {x['series']: (int(x['delta2']), int(x['weekStep'])) for x in actual} == {k:(d,s) for k,(_,d,s) in rows.items()}
                    page.keyboard.press('Tab'); expect(page.locator('a.skip')).to_be_focused()
                    page.keyboard.press('Enter'); expect(page).to_have_url(url+'#main')
                    shot('all')
                    page.locator('#atlas-query').fill('no-matching-additional-test-123')
                    expect(page.locator('#atlas-empty')).to_be_visible(); shot('empty')
                    page.locator('#atlas-filters button[type=reset]').click()
                    selector = page.locator('#atlas-step-direction'); selector.focus(); selector.press('End')
                    expect(selector).to_have_value('opposite')
                    assert visible('.card:not([hidden])') == visible('#compare-table tbody tr:not([hidden])') == {opposite}
                    fit = selector.evaluate('''el => {const s=getComputedStyle(el), c=document.createElement('canvas').getContext('2d'); c.font=[s.fontStyle,s.fontWeight,s.fontSize,s.fontFamily].join(' '); return {text:el.selectedOptions[0].textContent, measured:c.measureText(el.selectedOptions[0].textContent).width, available:el.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight)-24};}''')
                    print(edition, width, 'label', fit)
                    if edition == 'rebuilt':
                        assert fit['measured'] <= fit['available'], fit
                    selector.scroll_into_view_if_needed(); shot('opposite')
                    with page.expect_download() as download:
                        page.locator('#compare-week-changes-csv').click()
                    with download.value.path().open(encoding='utf-8-sig', newline='') as stream:
                        exported = list(csv.DictReader(stream))
                    assert len(exported) == 5 and {r['snapshot_series_key'] for r in exported} == {opposite}
                    assert [int(r['weekly_requests']) for r in exported] == rows[opposite][0]
                    assert all(r['dataset_sha256'] == DATASET for r in exported)
                    shared = urljoin(page.url, page.locator('#atlas-filter-link').get_attribute('href'))
                    assert parse_qs(urlsplit(shared).query)['af_step'] == ['opposite']; visit(shared)
                    assert visible('.card:not([hidden])') == {opposite}
                    page.locator('#atlas-filters button[type=reset]').click()
                    page.locator('#pair-left').select_option(left); page.locator('#pair-right').select_option(right)
                    def pair():
                        table = page.locator('#pair-table tbody tr'); expect(table).to_have_count(2)
                        for i,k in enumerate((left,right)):
                            assert table.nth(i).get_attribute('data-series') == k
                            assert [int(s.replace(',','')) for s in table.nth(i).locator('td').all_inner_texts()[:5]] == rows[k][0]
                        expect(page.locator('#pair-changes-table tbody tr')).to_have_count(5)
                        expect(page.locator('#pair-daily-charts svg')).to_have_count(2)
                    pair(); page.locator('#pair-output').scroll_into_view_if_needed(); shot('pair')
                    shared = urljoin(page.url, page.locator('#pair-share').get_attribute('href'))
                    assert parse_qs(urlsplit(shared).query)['af_dataset'] == [DATASET]; visit(shared); pair()
                    visit(shared.replace(DATASET, '0'*64)); expect(page.locator('#pair-output')).to_be_hidden()
                    assert not errors and not external, (errors,external); context.close()
            b.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    (output/'receipt.json').write_text(json.dumps({'status':'LOCAL_HTTP_NOT_PUBLISHED','source_zip_sha256':SOURCE,'archived_html_sha256':HTML,'rebuilt_html_sha256':digest(root/'rebuilt/index.html'),'dataset_sha256':DATASET,'screenshots':receipts},sort_keys=True)+'\n')


if __name__ == '__main__':
    assert len(sys.argv) == 3 and sys.argv[1] in ('prepare','browser')
    (prepare if sys.argv[1]=='prepare' else browser)(Path(sys.argv[2]).resolve())
