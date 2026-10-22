"""Browser acceptance: a shared state must carry an exact version triple.

Uses the independently hash-verified historical sample embedded in the local
single-file M0 preview. This is NOT public/HTTP deployment verification.
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
        # The unparameterized landing page is valid.
        assert page.locator('#retry').is_hidden()
        assert page.locator('#edition').is_enabled()
        for missing in (('ds',), ('m',), ('w',), ('ds','m','w')):
            page.locator('.card').nth(2).click()
            page.locator('#compare-select').select_option('5')
            assert page.locator('#history tr').count() == 35
            assert page.locator('#compare-table tbody tr').count() == 5
            page.evaluate("""missing => {
              const next = new URL(location.href);
              missing.forEach(key => next.searchParams.delete(key));
              history.pushState({}, '', next.toString());
              dispatchEvent(new PopStateEvent('popstate'));
            }""", list(missing))
            assert page.locator('#status.error').is_visible(), (width,missing,'not rejected')
            assert page.locator('#retry').is_visible()
            assert page.locator('.card').count() == 0
            assert page.locator('#history tr').count() == 0
            assert page.locator('#compare-table tr').count() == 0
            assert page.locator('#edition').is_disabled()
            assert page.locator('#copy').is_disabled()
            assert page.locator('#detail').is_hidden()
            if width == 390 and missing == ('ds','m','w'):
                page.screenshot(path=str(ROOT / 'unversioned-share-390.png'), full_page=True)
            page.locator('#retry').click()
            assert page.locator('.card').count() == 6
            assert page.locator('#edition').is_enabled()
        # A non-versioned filter-only bookmark also cannot pick the latest
        # available dataset without the visitor's knowledge.
        page.evaluate("""() => {
           const next=new URL(location.href);next.searchParams.set('q','Chess');
           history.pushState({},'',next.toString());dispatchEvent(new PopStateEvent('popstate'));
        }""")
        assert page.locator('#retry').is_visible()
        assert page.locator('.card').count() == 0
        page.locator('#retry').click()
        assert page.locator('.card').count() == 6
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), width
        assert not errors, errors
        print(f'PASS {width}px: unversioned saved views reject, valid landing and recovery work')
        page.close()
    browser.close()
