"""M0 visitor regression: discover/filter recovery persists a versioned URL.

Uses real retained D02 readings embedded in a deterministic HTML build and
real Chromium DOM execution. This is not a live HTTP/Pages check.
"""
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
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
        # A filter-only overview is a first-class shareable finding: it must
        # not require or invent a detail selection. Force the real UI fallback
        # when Clipboard API is unavailable and inspect its exact URL.
        page.evaluate("Object.defineProperty(navigator, 'clipboard', {configurable: true, value: undefined})")
        assert page.locator('#copy-discover').is_enabled()
        assert page.locator('#copy').is_disabled()
        page.locator('#copy-discover').click()
        assert page.locator('#discover-share-fallback').is_visible()
        discovery_url = page.locator('#discover-share-url').input_value()
        discovery_query = parse_qs(urlsplit(discovery_url).query)
        assert urlsplit(discovery_url).fragment == 'discover'
        assert [discovery_query.get(k) for k in ('ds', 'm', 'w', 'e')] == [
            ['d02-20261018-084126'], ['v0-empirical-35d'],
            ['20260811-20260914'], ['ru.wikipedia.org']]
        assert 's' not in discovery_query and 'c' not in discovery_query
        assert page.evaluate('document.activeElement.id') == 'discover-share-url'
        # Changing a filter invalidates the previously copied overview.
        page.locator('#order').select_option('volume')
        assert page.locator('#discover-share-fallback').is_hidden()
        assert page.locator('#discover-share-url').input_value() == ''
        assert 'o=volume' in page.url
        page.locator('#order').select_option('magnitude')

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
        # Even while a detail and comparison are open, the discovery
        # share button must copy the current filtered overview, not the pair.
        page.locator('#copy-discover').click()
        discovery_with_detail = page.locator('#discover-share-url').input_value()
        parameters = parse_qs(urlsplit(discovery_with_detail).query)
        assert 's' not in parameters and 'c' not in parameters
        assert parameters['e'] == ['ru.wikipedia.org']
        assert urlsplit(discovery_with_detail).fragment == 'discover'
        assert page.locator('#detail').is_visible()
        assert page.locator('#comparison').is_visible()

        # Changing discovery filters must remove a now-hidden selection,
        # including its history and comparison, from the browser and URL.
        page.locator('#query').fill('not-present-in-this-sample')
        assert page.locator('#empty').is_visible()
        assert page.locator('#detail').is_hidden()
        assert page.locator('#comparison').is_hidden()
        assert page.locator('#history tr').count() == 0
        assert page.locator('#compare-table tr').count() == 0
        active_params = parse_qs(urlsplit(page.url).query, keep_blank_values=True)
        assert 's' not in active_params and 'c' not in active_params, f'{width}px invisible selection retained: {page.url}'
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
        assert page.locator('#copy-discover').is_disabled()
        page.locator('#retry').click()
        assert page.locator('#cards .card').count() == 6
        assert page.locator('#retry').is_hidden()
        assert page.locator('#copy-discover').is_enabled()
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
