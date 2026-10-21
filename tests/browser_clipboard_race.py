"""Controlled Chromium regression for async clipboard navigation races.

A rejected or resolved clipboard promise must not resurrect a stale share URL
once filters/selection/version or a newer copy request changes. This checks the
retained D02 portable snapshot in a real browser DOM, not public HTTP/Pages.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'Dayflare-M0-portable-historical-UNPUBLISHED.html').read_text(encoding='utf-8')

with sync_playwright() as playwright:
    browser = launch_chromium(playwright)
    for width in (320, 390, 1280):
        page = browser.new_page(viewport={'width': width, 'height': 820}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content(HTML, wait_until='load')
        page.wait_for_function("document.querySelectorAll('.card').length===6")
        page.locator('.card').nth(2).click()
        page.locator('#compare-select').select_option('5')
        stale_url = page.url
        page.evaluate("""() => {
          window.copyRequests = [];
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {writeText: url => new Promise((resolve, reject) => {
              window.copyRequests.push({url, resolve, reject});
            })}
          });
        }""")
        # Case 1: failure from a comparison URL after that comparison was removed.
        page.locator('#copy').click()
        page.wait_for_function('copyRequests.length===1')
        page.locator('#compare-select').select_option('')
        assert page.url != stale_url+        page.evaluate("copyRequests[0].reject(new Error('permission denied'))")
        page.wait_for_timeout(70)
        assert page.locator('#share-fallback').is_hidden(), (width, 'stale rejected link')
        assert page.locator('#share-url').input_value() == ''
        assert 'Clipboard unavailable' not in page.locator('#share-state').inner_text()

        # Case 2: a late success must not claim to have copied a *new* URL.
        page.locator('#copy').click()
        page.wait_for_function('copyRequests.length===2')
        page.locator('#compare-select').select_option('4')
        page.evaluate('copyRequests[1].resolve()')
        page.wait_for_timeout(70)
        assert page.locator('#share-fallback').is_hidden()
        assert 'link copied' not in page.locator('#share-state').inner_text()

        # Case 3: two overlapping requests; only the latest result has authority.
        current_url = page.url
        page.locator('#copy').click()
        page.locator('#copy').click()
        page.wait_for_function('copyRequests.length===4')
        page.evaluate("copyRequests[2].reject(new Error('stale clipboard rejection'))")
        page.wait_for_timeout(70)
        assert page.locator('#share-fallback').is_hidden()
        page.evaluate("copyRequests[3].reject(new Error('current clipboard rejection'))")
        page.wait_for_function("!document.querySelector('#share-fallback').hidden")
        assert page.locator('#share-url').input_value() == current_url
        assert page.evaluate("document.activeElement?.id") == 'share-url'

        # Case 4: changing a filter clears the visible fallback (and its value).
        page.locator('#query').fill('Chess')
        assert page.locator('#share-fallback').is_hidden()
        assert page.locator('#share-url').input_value() == ''
        assert 'Clipboard unavailable' not in page.locator('#share-state').inner_text(), (width, 'orphaned fallback advice')

        # Case 5: pending rejection after a version mismatch must not restore UI.
        page.locator('#copy').click()
        page.wait_for_function('copyRequests.length===5')
        page.evaluate("""() => {
          const url = new URL(location.href);
          url.searchParams.set('m', 'wrong-method');
          history.pushState({}, '', url.toString());
          dispatchEvent(new PopStateEvent('popstate'));
          copyRequests[4].reject(new Error('late clipboard rejection'));
        }""")
        page.wait_for_timeout(70)
        assert page.locator('#copy').is_disabled()
        assert page.locator('#detail').is_hidden()
        assert page.locator('#share-fallback').is_hidden()
        assert page.locator('#share-url').input_value() == ''
        assert page.locator('#status.error').is_visible()
        assert not errors, (width, errors)
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), width
        print(f'PASS {width}px: stale clipboard success/failure, overlapping copy, filters and incompatible links')
        page.close()
    browser.close()
