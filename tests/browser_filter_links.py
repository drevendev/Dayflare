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
        page.locator('#query').fill('not-present-in-this-sample')
        assert page.locator('#empty').is_visible()
        assert 'q=not-present-in-this-sample' in page.url, f'{width}px empty query URL not preserved'
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
