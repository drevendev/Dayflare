"""Render the self-contained evidence page in real Chromium DOM.

Navigation from the browser to a local/public HTTP origin is not exercised here;
actual HTTP requests and the /Dayflare/ root are separately tested in Python.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium
from tools.build_static_release import bundle_files

files = bundle_files()
css = files['styles.css'].decode()
html = files['evidence.html'].decode().replace('<link rel="stylesheet" href="styles.css">', '<style>'+css+'</style>')  # inline CSS to avoid external browser navigation
with sync_playwright() as p:
    browser = launch_chromium(p)
    for width in (320, 390, 1280):
        page = browser.new_page(viewport={'width':width, 'height':850}, java_script_enabled=False)
        page.set_content(html, wait_until='domcontentloaded')
        assert page.locator('#evidence-title').inner_text() == 'Follow the evidence.'
        assert page.locator('#method').is_visible()
        assert page.locator('#provenance').is_visible()
        assert page.locator('a[href="evidence/d02-20261018/provenance.json"]').count()==1
        assert page.locator('a[href="evidence/d02-20261018/README.md"]').count()==1
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'overflow: {width}'
        page.screenshot(path=str(ROOT / f'evidence-release-{width}.png'), full_page=True)
        page.keyboard.press('Tab')
        assert page.evaluate('document.activeElement.className')=='skip', 'first keyboard target should be skip link'
        assert page.evaluate('getComputedStyle(document.activeElement).outlineStyle')!='none'
        print(f'PASS {width}px: source page readable without JS, exact links, focus visible, no overflow')
        page.close()
    browser.close()
print('VISUAL DOM verified; hosted HTTP browser navigation and public Pages NOT_VERIFIED')
