"""Real Chromium: the comparison exposes both exact 35-day series side by side.

Uses the SHA-verified retained archive and a controlled DOM transport because
browser HTTP navigation is unavailable; never counts synthetic pages as real data.
"""
from __future__ import annotations

import base64
import hashlib
import faulthandler
import sys
import time
from pathlib import Path
from zipfile import ZipFile

from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = (ROOT/'evidence/d02-20261018/source.zip').read_bytes()
assert hashlib.sha256(ARCHIVE).hexdigest() == '3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631'
SHA_BY_LENGTH = {str(len(ARCHIVE)): hashlib.sha256(ARCHIVE).hexdigest()}
with ZipFile(ROOT/'evidence/d02-20261018/source.zip') as zip_file:
    for member in ('sample.json', 'receipt.json'):
        data=zip_file.read(member)
        SHA_BY_LENGTH[str(len(data))] = hashlib.sha256(data).hexdigest()
HTML = (ROOT/'site/index.html').read_text(encoding='utf8')
CSS = (ROOT/'site/styles.css').read_text(encoding='utf8')
JS = (ROOT/'site/app.js').read_text(encoding='utf8')
B64 = base64.b64encode(ARCHIVE).decode('ascii')

STARTED = time.monotonic()


def phase(width, step):
    """Flush the last observable step before any potentially blocking browser call."""
    print(f'COMPARE_PHASE {width}px {step} elapsed={time.monotonic() - STARTED:.1f}s', flush=True)


# If Chromium/Playwright deadlocks, retain the blocked Python stack in hosted
# CI rather than merely printing a global 45-second process timeout.
faulthandler.dump_traceback_later(30, repeat=False, file=sys.stderr)

with sync_playwright() as playwright:
    phase('setup', 'browser-launch')
    browser = launch_chromium(playwright)
    for width in (320, 390, 1280):
        page = browser.new_page(viewport={'width':width, 'height':840}, reduced_motion='reduce')
        page.set_default_timeout(12_000)
        phase(width, 'set-content')
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content(HTML, wait_until='domcontentloaded')
        page.add_style_tag(content=CSS)
        page.evaluate('''([encoded, hashes]) => {
          const bytes=Uint8Array.from(atob(encoded), c=>c.charCodeAt(0));
          window.fetch=async()=>new Response(bytes, {status:200});
          Object.defineProperty(window,'crypto',{configurable:true,value:{subtle:{digest:async (_,raw)=>{
            const hash=hashes[raw.byteLength];
            if(!hash)throw Error('unexpected fixture length');
            return Uint8Array.from(hash.match(/.{2}/g),part=>parseInt(part,16)).buffer;
          }}}});
        }''', [B64, SHA_BY_LENGTH])
        phase(width, 'app-script')
        page.add_script_tag(content=JS)
        phase(width, 'wait-six-cards')
        page.wait_for_function("document.querySelectorAll('.card').length===6")
        # Different local pages/editions: compare their counts without claiming
        # identity equivalence between EN Chess and RU Шахматы.
        phase(width, 'open-detail')
        page.locator('.card').nth(2).click()
        assert page.locator('#history th[scope="row"]').count()==35, 'topic history must expose dates as row headers'
        phase(width, 'select-comparison')
        page.locator('#compare-select').select_option('5')
        assert page.locator('#compare-table tbody tr').count()==5
        assert page.locator('#compare-table tbody th[scope="row"]').count()==5, 'weekly windows need row headers'
        weekly = page.locator('#compare-table')
        assert weekly.get_attribute('tabindex')=='0' and weekly.get_attribute('role')=='region'
        phase(width, 'keyboard-navigation')
        page.locator('#copy').focus()
        page.keyboard.press('Tab')
        assert page.evaluate('document.activeElement.id')=='compare-table'
        assert page.evaluate('getComputedStyle(document.activeElement).outlineStyle')!='none'
        if width==320:
            assert weekly.evaluate('(el)=>el.scrollWidth>el.clientWidth'), 'weekly count table should scroll at 320px'
            page.keyboard.press('ArrowRight')
            page.wait_for_timeout(200)
            assert weekly.evaluate('(el)=>el.scrollLeft>0'), 'keyboard must reveal offscreen weekly totals'
        disclosure = page.locator('#compare-daily details')
        assert disclosure.count()==1, 'missing exact daily comparison disclosure'
        assert not disclosure.get_attribute('open'), '35-day table should be collapsed by default'
        phase(width, 'open-daily-disclosure')
        disclosure.locator('summary').focus()
        page.keyboard.press('Enter')
        assert disclosure.get_attribute('open') is not None, 'keyboard must open comparison'
        phase(width, 'check-daily-counts')
        rows=disclosure.locator('tbody tr')
        assert rows.count()==35
        assert rows.nth(0).locator('th[scope="row"]').inner_text()=='2026-08-11'
        assert rows.nth(0).locator('td').all_inner_texts()==['2,367', '372']
        assert rows.nth(34).locator('th[scope="row"]').inner_text()=='2026-09-14'
        assert '2026-08-11' in disclosure.locator('caption').inner_text()
        assert page.evaluate("getComputedStyle(document.querySelector('#compare-daily tbody th[scope=row]')).whiteSpace")=='nowrap'
        assert disclosure.locator('[role="region"][tabindex="0"]').count()==1
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),width
        if width in (390,1280):
            phase(width, 'comparison-screenshot')
            page.locator('#comparison').screenshot(path=str(ROOT/f'compare-daily-{width}.png'))
        # An unselected comparison or incompatible link may never retain the
        # previous two-series evidence on screen (including the open details).
        phase(width, 'clear-comparison')
        page.locator('#compare-select').select_option('')
        assert page.locator('#compare-daily table').count()==0
        page.locator('#compare-select').select_option('5')
        phase(width, 'invalid-link-recovery')
        page.evaluate('''() => {
          const u=new URL(location.href);u.searchParams.set('ds','incompatible');
          history.pushState({},'',u.toString());dispatchEvent(new PopStateEvent('popstate'));
        }''')
        assert page.locator('#compare-daily table').count()==0
        assert page.locator('#status').inner_text().find('different dataset')>=0
        assert not errors,errors
        phase(width, 'passed')
        print(f'PASS {width}px: exact 35-day count comparison, keyboard, clearing, incompatible link, overflow')
        page.close()
    browser.close()
faulthandler.cancel_dump_traceback_later()
print('PASS controlled DOM only; hosted CI and public HTTP NOT_VERIFIED')
