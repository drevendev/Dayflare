"""Visitor regression: deep-linked topic/comparison restores the intended view.

Uses the deterministic retained-evidence portable preview and Chromium DOM
execution. Does not claim HTTP navigation or public Pages validation.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'Dayflare-M0-portable-historical-UNPUBLISHED.html').read_text(encoding='utf-8')

with sync_playwright() as p:
    browser = launch_chromium(p)
    for width in (320, 390, 1280):
        page = browser.new_page(viewport={'width': width, 'height': 760}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content(HTML, wait_until='load')
        page.wait_for_function("document.querySelectorAll('.card').length===6")
        page.locator('.card').nth(2).click()
        detail_url = page.url
        assert detail_url.endswith('#detail'), (width, detail_url)
        page.set_content(HTML, wait_until='load')
        page.wait_for_function("document.querySelector('#detail-title').textContent==='Chess'")
        page.wait_for_function("document.activeElement?.id==='detail-title'")
        assert page.locator('#history tr').count() == 35
        assert page.url == detail_url
        page.locator('#compare-select').select_option('5')
        compare_url = page.url
        assert compare_url.endswith('#comparison'), (width, compare_url)
        page.set_content(HTML, wait_until='load')
        page.wait_for_function("document.querySelector('#compare-table tbody')?.children.length===5")
        page.wait_for_function("document.activeElement?.id==='compare-title'")
        assert page.locator('#compare-select').input_value() == '5'
        assert page.url == compare_url
        # Clipboard permissions are not guaranteed on mobile or embedded views.
        # A failed copy must expose a labelled, keyboard-selectable exact URL,
        # not merely append an unselectable long string to a status paragraph.
        page.evaluate("""() => Object.defineProperty(navigator, 'clipboard', {
          configurable:true, value:{writeText:()=>Promise.reject(new Error('permission denied'))}
        })""")
        page.locator('#copy').click()
        page.wait_for_function("!document.querySelector('#share-fallback').hidden")
        field = page.locator('#share-url')
        assert field.input_value() == compare_url, (width, field.input_value())
        assert page.evaluate("document.activeElement?.id") == 'share-url'
        assert page.evaluate("document.querySelector('#share-url').selectionStart") == 0
        assert page.evaluate("document.querySelector('#share-url').selectionEnd") == len(compare_url)
        assert page.locator('label[for="share-url"]').is_visible()
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), width
        # The fallback must not show a stale comparison URL after changing state.
        page.locator('#compare-select').select_option('')
        assert page.locator('#share-fallback').is_hidden()
        assert field.input_value() == ''
        page.locator('#copy').click()
        page.wait_for_function("!document.querySelector('#share-fallback').hidden")
        assert field.input_value() == page.url
        # A subsequent successful clipboard permission removes the old fallback.
        page.evaluate("""() => Object.defineProperty(navigator, 'clipboard', {
          configurable:true, value:{writeText:async url => {window.copiedURL=url;}}
        })""")
        page.locator('#copy').click()
        page.wait_for_function("document.querySelector('#share-fallback').hidden")
        assert field.input_value() == ''
        assert page.evaluate('window.copiedURL') == page.url
        # The copied confirmation describes the *old* URL. Filtering creates a
        # different version-bound view and must restore the neutral share hint.
        copied_before_filter = page.url
        page.locator('#subject').select_option('games/sport')
        assert page.url != copied_before_filter
        assert 'link copied' not in page.locator('#share-state').inner_text(), (width, 'stale copied confirmation')
        assert 'Choose a second series' in page.locator('#share-state').inner_text()
        # Invalid restored versions hide the fallback and old topic/compare state.
        page.evaluate("""() => {
          const u=new URL(location.href);u.searchParams.set('ds','invalid');
          history.pushState({},'',u.toString());dispatchEvent(new PopStateEvent('popstate'));
        }""")
        assert page.locator('#share-fallback').is_hidden()
        assert page.locator('#copy').is_disabled()
        page.locator('#retry').click()
        assert page.locator('#share-fallback').is_hidden()
        assert page.locator('#cards .card').count() == 6
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), width
        assert not errors, (width, errors)
        print(f'PASS {width}px: deep-linked topic/comparison restores exact data and keyboard focus')
        page.close()
    browser.close()
