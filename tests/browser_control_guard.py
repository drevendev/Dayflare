"""Chromium regression: no data-dependent controls during pending/error/mismatch.

Controlled DOM on about:blank because direct localhost navigation is forbidden.
The response/digest shims are test-only; SHA-256 is independently rechecked in
Python against the exact retained input and both uncompressed members.
"""
import base64
import hashlib
from pathlib import Path
from zipfile import ZipFile
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = (ROOT / 'evidence/d02-20261018/source.zip').read_bytes()
EXPECTED = {
    'source.zip': '3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631',
    'sample.json': '98880f706c0d8b5433f0fbb46bcad0cb9a2d515ea894752dcd971326e5805a8e',
    'receipt.json': '298c6ade24ec911502f4e2bee23e4c3ac012eecc8192b56071210d3cf94adb21',
}
assert hashlib.sha256(ARCHIVE).hexdigest() == EXPECTED['source.zip']
with ZipFile(ROOT / 'evidence/d02-20261018/source.zip') as z:
    for member in ('sample.json', 'receipt.json'):
        assert hashlib.sha256(z.read(member)).hexdigest() == EXPECTED[member]

HTML = (ROOT / 'site/index.html').read_text(encoding='utf8')
CSS = (ROOT / 'site/styles.css').read_text(encoding='utf8')
JS = (ROOT / 'site/app.js').read_text(encoding='utf8')
READY_FETCH = """encoded => {
    const bytes=Uint8Array.from(atob(encoded), c=>c.charCodeAt(0));
    window.fetch = async () => new Response(bytes, {status:200});
    const hex={4311:'3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631',
               42711:'98880f706c0d8b5433f0fbb46bcad0cb9a2d515ea894752dcd971326e5805a8e',
               13453:'298c6ade24ec911502f4e2bee23e4c3ac012eecc8192b56071210d3cf94adb21'};
    Object.defineProperty(window,'crypto',{configurable:true,value:{subtle:{digest:async (_,raw)=>{
      const digest=hex[raw.byteLength]; if(!digest)throw new Error('unexpected archive length');
      return Uint8Array.from(digest.match(/.{2}/g),v=>parseInt(v,16)).buffer;
    }}}});
}"""

with sync_playwright() as p:
    browser = launch_chromium(p)
    for width in (320, 390, 1280):
        page = browser.new_page(viewport={'width':width, 'height':850})
        page.set_default_timeout(6500)
        errors=[]
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.set_content(HTML,wait_until='domcontentloaded',timeout=5000)
        page.add_style_tag(content=CSS)
        # Hold the initial request to assert the true *pending* state.
        page.evaluate('''() => { window.fetch = () => new Promise(resolve => { window.releaseFetch = resolve; }); return true; }''')
        page.add_script_tag(content=JS)
        page.wait_for_function("document.querySelector('#status').textContent.includes('Loading')")
        for key in ('edition','subject','query','compare-select','copy','clear'):
            assert page.locator('#'+key).is_disabled(), (width, 'pending', key)
        assert page.locator('#empty').is_hidden()
        page.evaluate("window.releaseFetch(new Response('source unavailable',{status:503}))")
        page.wait_for_function("document.querySelector('#status').textContent.includes('HTTP 503')")
        for key in ('edition','subject','query','compare-select','copy','clear'):
            assert page.locator('#'+key).is_disabled(), (width, 'error', key)
        assert page.locator('#retry').is_visible()
        assert page.locator('#empty').is_hidden()
        if width==390:
            page.screenshot(path=str(ROOT/'control-error-390.png'),full_page=True)
        page.evaluate(READY_FETCH,base64.b64encode(ARCHIVE).decode('ascii'))
        page.locator('#retry').click()
        page.wait_for_function("document.querySelectorAll('.card').length===6")
        for key in ('edition','subject','query','clear'):
            assert page.locator('#'+key).is_enabled(), (width, 'valid snapshot', key)
        page.locator('#query').fill('term that is missing')
        assert page.locator('#empty').is_visible()
        page.locator('#clear').click()
        assert page.locator('.card').count()==6
        # Simulate an incompatible browser-history entry; no stale controls.
        page.evaluate('''() => {
          const u=new URL(location.href);u.searchParams.set('ds','incompatible');
          history.pushState({},'',u.toString());dispatchEvent(new PopStateEvent('popstate'));
        }''')
        page.wait_for_function("document.querySelector('#status').textContent.includes('different dataset')")
        for key in ('edition','subject','query','compare-select','copy','clear'):
            assert page.locator('#'+key).is_disabled(), (width, 'mismatch', key)
        assert page.locator('#empty').is_hidden()
        if width==390:
            page.screenshot(path=str(ROOT/'control-mismatch-390.png'),full_page=True)
        page.locator('#retry').click()
        assert page.locator('.card').count()==6
        assert page.locator('#clear').is_enabled()
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        assert not errors,errors
        print(f'PASS {width}px: loading, HTTP 503, retry, empty search, clear, mismatch and recovery')
        page.close()
    browser.close()
print('PASS controlled-DOM browser checks; hosted Pages HTTP NOT_VERIFIED')
