"""M0 visitor regression: discover/filter recovery persists a versioned URL.

Uses real retained D02 readings embedded in a deterministic HTML build and
real Chromium DOM execution. This is not a live HTTP/Pages check.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'Dayflare-M0-portable-historical-UNPUBLISHED.html').read_text(encoding='utf-8')

with sync_playwright() as playwright:
    browser = launch_chromium(playwright)
    for width in (320, 390, 1280):
        page = browser.new_page(viewport={'width': width, 'height': 900}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda err: errors.append(str(err)))
        page.set_content(HTML, wait_until='load')
        page.wait_for_function("document.querySelectorAll('.card').length===6")
        assert page.locator('#cards .card').count() == 6
        page.locator('#edition').select_option('ru.wikipedia.org')
        assert page.locator('#cards .card').count() == 3
        u = page.url
        assert 'ds=d02-20261018-084126' in u and 'm=v0-empirical-35d' in u and 'w=20260811-20260914' in u, f'{width}px filter URL lost version triple: {u}'
        assert 'e=ru.wikipedia.org' in u, f'{width}px filter URL not updated: {u}'
        if width == 390:
            page.screenshot(path=str(ROOT / 'filtered-view-390.png'), full_page=True)
        # A valid RU discovery selection may compare against an EN series:
        # the second series is not constrained by the discovery filter.
        page.locator('#cards .card').first.click()
        assert page.locator('#detail').is_visible()
        page.locator('#compare-select').select_option('0')
        assert page.locator('#compare-table tr').count() > 0
        selected_url = page.url
        assert 's=' in selected_url and 'c=0' in selected_url
        # Changing discovery filters must remove a now-hidden selection,
        # including its history and comparison, from the browser and URL.
        page.locator('#query').fill('not-present-in-this-sample')
        assert page.locator('#empty').is_visible()
        assert page.locator('#detail').is_hidden()
        assert page.locator('#comparison').is_hidden()
        assert page.locator('#history tr').count() == 0
        assert page.locator('#compare-table tr').count() == 0
        assert 's=' not in page.url and 'c=' not in page.url, f'{width}px invisible selection retained: {page.url}'
        assert 'q=not-present-in-this-sample' in page.url, f'{width}px empty query URL not preserved'
        # An externally edited permalink is stricter: incompatible selection
        # and filters must fail closed rather than silently clear the evidence.
        page.evaluate("""prior => {
            const u = new URL(prior);
            u.searchParams.set('q', 'not-present-in-this-sample');
            history.pushState({}, '', u);
            dispatchEvent(new PopStateEvent('popstate'));
        }""", selected_url)
        assert page.locator('#retry').is_visible(), (width, 'incompatible share missing recovery')
        assert page.locator('#copy').is_disabled()
        assert page.locator('#cards .card').count() == 0
        assert page.locator('#detail').is_hidden()
        assert page.locator('#comparison').is_hidden()
        assert 'excluded by this shared link' in page.locator('#status').inner_text()
        page.locator('#retry').click()
        assert page.locator('#cards .card').count() == 6
        assert page.locator('#retry').is_hidden()
        page.locator('#clear').click()
        assert page.locator('#cards .card').count() == 6
        assert 'q=' not in page.url and 'e=ru.wikipedia.org' not in page.url, f'{width}px clear kept stale URL: {page.url}'
        # A fresh app startup on the resulting address must keep the recovered state.
        page.set_content(HTML, wait_until='load')
        page.wait_for_function("document.querySelectorAll('.card').length===6")
        assert page.locator('#query').input_value() == ''
        assert page.locator('#edition').input_value() == 'all'
        assert page.locator('#retry').is_hidden()
        # Filter-only permalink also survives an app restart.
        page.locator('#subject').select_option('culture/literature')
        before = page.locator('#cards .card').count()
        assert before > 0
        link = page.url
        assert 'sub=culture%2Fliterature' in link, f'{width}px subject URL missing: {link}'
        page.set_content(HTML, wait_until='load')
        page.wait_for_function("document.querySelectorAll('.card').length===2")
        assert page.locator('#subject').input_value() == 'culture/literature'
        assert page.locator('#cards .card').count() == before
        assert not errors, (width, errors)
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), width
        print(f'PASS {width}px: filter URLs versioned; empty-state clear persists; reload restores source filters')
        page.close()
    browser.close()
