"""Real Chromium DOM regression: history is discoverable but does not bury comparison.

Uses verified embedded real historical observations. Not a live HTTP/Pages test.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'Dayflare-M0-portable-historical-UNPUBLISHED.html').read_text(encoding='utf-8')

with sync_playwright() as playwright:
    browser = launch_chromium(playwright)
    for width in (320, 390, 1280):
        page = browser.new_page(viewport={'width': width, 'height': 850}, reduced_motion='reduce')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content(HTML, wait_until='load')
        page.wait_for_function('document.querySelectorAll(".card").length===6')
        page.locator('.card').nth(2).click()
        assert page.locator('#detail-title').inner_text() == 'Chess'
        history = page.locator('#history-disclosure')
        assert history.is_visible() and not history.evaluate('(node)=>node.open')
        assert page.locator('#history tr').count() == 35
        assert not page.locator('#history').is_visible(), 'Collapsed historical table still occupies visual space'
        distance = page.evaluate('document.querySelector("#comparison").getBoundingClientRect().top - document.querySelector("#detail").getBoundingClientRect().top')
        assert distance < 1100, (width, distance)
        summary = page.locator('#history-disclosure summary')
        summary.focus()
        page.keyboard.press('Enter')
        assert history.evaluate('(node)=>node.open') and page.locator('#history').is_visible()
        assert page.locator('#history tr').count() == 35
        assert page.locator('#history tr').first.inner_text().startswith('2026-08-11')
        page.keyboard.press('Enter')
        assert not history.evaluate('(node)=>node.open')
        page.locator('#compare-select').select_option('5')
        assert page.locator('#compare-table tbody tr').count() == 5
        assert page.locator('#comparison').is_visible()
        page.locator('.card').first.click()
        assert not history.evaluate('(node)=>node.open'), 'New topic must start with its long table collapsed'
        assert page.locator('#history tr').count() == 35
        assert not errors, (width, errors)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        if width == 390:
            page.screenshot(path=str(ROOT / 'history-collapsed-390-UNPUBLISHED.png'), full_page=True)
        print(f'PASS {width}px: keyboard-disclosed 35 exact values; comparison within {distance:.0f}px of detail')
        page.close()
    browser.close()
