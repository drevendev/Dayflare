"""Real Chromium checks of the offline, single-file M0 atlas in controlled DOM.

No remote server, data fetch, browser transport override, or digest shim is used:
the generated HTML carries the evidence already checked by build_portable.py.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'Dayflare-M0-portable-historical-UNPUBLISHED.html').read_text(encoding='utf-8')

with sync_playwright() as p:
    browser = launch_chromium(p)
    for width in (320,390,1280):
        page = browser.new_page(viewport={'width':width,'height':900}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content(HTML, wait_until='load')
        page.wait_for_function('document.querySelectorAll(".card").length===6')
        assert page.locator('#status').inner_text().startswith('6 of 6 measured series')
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),width
        assert page.locator('#offline-method').is_visible()
        assert page.locator('#offline-provenance').count()==1
        page.locator('#offline-provenance summary').click()
        assert 'd02-20261018-084126' in page.locator('#offline-provenance pre').inner_text()
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(width,'provenance overflow')
        page.locator('#offline-provenance summary').click()
        # Global button:hover must not turn dark while card labels remain dark.
        page.locator('.card').first.hover()
        colors=page.locator('.card').first.evaluate('el => {const x=getComputedStyle(el);return [x.backgroundColor,x.color]}')
        assert colors==['rgb(255, 255, 255)','rgb(20, 26, 22)'],(width,colors)
        page.locator('.card').nth(2).focus()
        page.keyboard.press('Enter')
        assert page.locator('#detail-title').inner_text() == 'Chess'
        assert page.locator('#history tr').count() == 35
        assert '19,804' in page.locator('#detail-summary').inner_text()
        assert page.evaluate('document.activeElement.id') == 'detail-title'
        page.locator('#compare-select').select_option('5')
        assert page.locator('#compare-table tbody tr').count() == 5
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(width,'detail overflow')
        if width==390:
            page.screenshot(path=str(ROOT/'portable-detail-390.png'),full_page=True)
        assert 'ds=d02-20261018-084126' in page.url and 'm=v0-empirical-35d' in page.url
        # A mismatched deep link must hide all previously displayed detail and comparison.
        page.evaluate('() => { const u=new URL(location.href); u.searchParams.set("ds","unknown"); history.pushState({},"",u.toString()); dispatchEvent(new PopStateEvent("popstate")); }')
        assert page.locator('#retry').is_visible()
        assert page.locator('#edition').is_disabled()
        assert page.locator('.card').count() == 0
        assert not page.locator('#detail').is_visible()
        assert not page.locator('#comparison').is_visible()
        page.locator('#retry').click()
        assert page.locator('.card').count() == 6
        assert page.locator('#detail').is_hidden()
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),width
        assert not errors,errors
        if width==390:
            page.screenshot(path=str(ROOT/'portable-interactive-390.png'),full_page=True)
        print(f'PASS interactive {width}px: 6 real series, keyboard detail, 35-day history, compare, version-bound link, recovery')
        page.close()
        nojs = browser.new_page(viewport={'width':width,'height':900}, java_script_enabled=False)
        nojs.set_content(HTML, wait_until='load')
        assert nojs.locator('.nojs-topic').count() == 6
        assert nojs.locator('.nojs-topic tbody tr').count() == 210
        nojs.locator('.nojs-topic summary').nth(2).focus()
        nojs.keyboard.press('Enter')
        assert nojs.locator('.nojs-topic').nth(2).get_attribute('open') is not None
        assert not nojs.evaluate('document.documentElement.scrollWidth > innerWidth'),width
        if width==390:
            nojs.screenshot(path=str(ROOT/'portable-nojs-390.png'),full_page=True)
        print(f'PASS no-JS {width}px: 6 native disclosures, 210 dated values, keyboard activation')
        nojs.close()
    browser.close()
print('PASS real Chromium DOM preview; not file://, HTTP or Pages verification')
