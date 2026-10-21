"""Chromium visual/keyboard smoke for real statically rendered no-JS tables.

Runs using set_content because this runtime blocks HTTP and file navigation.
It does not claim live or Pages deployment verification.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'site/index.html').read_text(encoding='utf-8')
CSS = (ROOT / 'site/styles.css').read_text(encoding='utf-8')
# No JavaScript is enabled, so Playwright cannot inject a style tag after load.
HTML = HTML.replace('<link rel="stylesheet" href="styles.css">', '<style>' + CSS + '</style>')
HTML = HTML.replace('<script src="app.js" defer></script>', '')
with sync_playwright() as p:
    browser = launch_chromium(p)
    for width in (320, 390, 1280):
        context = browser.new_context(viewport={'width':width,'height':850}, java_script_enabled=False)
        page = context.new_page()
        page.set_default_timeout(8000)
        page.set_content(HTML, wait_until='domcontentloaded', timeout=12000)
        details = page.locator('.nojs-topic')
        assert details.count() == 6, f'Expected 6 no-JS disclosures, got {details.count()}'
        assert page.locator('#nojs-title').is_visible()
        assert page.locator('#status').is_hidden()
        assert page.locator('#edition').is_hidden()
        assert page.locator('.card').count() == 0
        assert page.locator('.nojs-topic[open]').count() == 0
        page.locator('.nojs-topic summary').nth(2).focus()
        page.keyboard.press('Enter')
        assert page.locator('.nojs-topic[open]').count() == 1
        assert 'Chess' in page.locator('.nojs-topic[open] summary').inner_text()
        assert page.locator('.nojs-topic[open] tbody tr').count() == 35
        assert page.locator('.nojs-topic[open]').inner_text().count('2026-') >= 35
        assert '19,804' in page.locator('.nojs-topic[open] summary').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'overflow width={width}'
        if width == 390:
            page.screenshot(path=str(ROOT/'nojs-390.png'), full_page=True)
        print(f'PASS no-JS {width}px: 6 source disclosures, keyboard, 35 exact Chess values, no overflow')
        context.close()
    browser.close()
