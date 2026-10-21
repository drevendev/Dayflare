"""Chromium regression: bounded, abortable M0 snapshot download.

Runs application JavaScript in a controlled DOM because the browser sandbox blocks
loopback navigation. Produces synthetic transports, never Wikimedia evidence.
"""
import base64
import hashlib
from pathlib import Path
from zipfile import ZipFile
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = (ROOT / 'evidence/d02-20261018/source.zip').read_bytes()
assert hashlib.sha256(ARCHIVE).hexdigest() == '3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631'
HTML = (ROOT / 'site/index.html').read_text(encoding='utf-8')
CSS = (ROOT / 'site/styles.css').read_text(encoding='utf-8')
JS = (ROOT / 'site/app.js').read_text(encoding='utf-8')
MEMBER_HEX = {}
with ZipFile(ROOT / 'evidence/d02-20261018/source.zip') as z:
    for member in ('sample.json', 'receipt.json'):
        b = z.read(member)
        MEMBER_HEX[len(b)] = hashlib.sha256(b).hexdigest()

DIGEST_SHIM = '''() => {
  const expected = %(json)s;
  Object.defineProperty(window,'crypto',{configurable:true,value:{subtle:{digest:async (_,raw)=>{
    const sha=expected[raw.byteLength];
    if(!sha)throw new Error('Unexpected test fixture length');
    return Uint8Array.from(sha.match(/.{2}/g),v=>parseInt(v,16)).buffer;
  }}}});
}'''

import json
DIGEST_SHIM = DIGEST_SHIM % {'json': json.dumps({len(ARCHIVE): hashlib.sha256(ARCHIVE).hexdigest(), **MEMBER_HEX})}

with sync_playwright() as p:
    browser = launch_chromium(p)
    for width in (320, 390, 1280):
        page = browser.new_page(viewport={'width':width, 'height':800}, reduced_motion='reduce')
        page.set_default_timeout(2500)
        errors=[]
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.set_content(HTML,wait_until='domcontentloaded')
        page.add_style_tag(content=CSS)
        page.evaluate(DIGEST_SHIM)
        page.evaluate('''() => {
          window.produced=0;window.cancelled=false;
          window.fetch=async () => new Response(new ReadableStream({
            pull(controller) {
              if(++window.produced<=12) controller.enqueue(new Uint8Array(65536));
              else controller.close();
            },
            cancel(){window.cancelled=true;}
          }),{status:200});
        }''')
        page.add_script_tag(content=JS)
        page.wait_for_function("document.querySelector('#status').textContent.includes('allowed')")
        assert page.evaluate('window.cancelled'), ('unbounded response was not cancelled', width)
        assert page.evaluate('window.produced') <= 10, ('unbounded response was read before detection',width)
        assert page.locator('#retry').is_visible()
        assert page.locator('#edition').is_disabled()
        assert page.locator('#cards .card').count()==0
        if width==390:
            page.screenshot(path=str(ROOT/'stream-too-large-390-DOM-UNPUBLISHED.png'),full_page=True)
        assert not errors,errors
        print(f'PASS {width}px: streamed-size cap, cancellation, inaccessible data controls')
        page.close()

    # An otherwise valid API endpoint may hang forever: the visitor must get Retry.
    page=browser.new_page(viewport={'width':390,'height':800})
    page.set_default_timeout(2500)
    page.set_content(HTML,wait_until='domcontentloaded')
    page.add_style_tag(content=CSS)
    page.evaluate(DIGEST_SHIM)
    page.evaluate('''() => {
      const nativeSetTimeout=window.setTimeout.bind(window);
      window.setTimeout=(cb,ms,...args)=>nativeSetTimeout(cb,ms===12000?80:ms,...args);
      window.aborted=false;
      window.fetch=(_url,opts)=>new Promise((resolve,reject)=>{
        opts.signal.addEventListener('abort',()=>{
          window.aborted=true;reject(new DOMException('Aborted','AbortError'));
        },{once:true});
      });
    }''')
    page.add_script_tag(content=JS)
    page.wait_for_function("document.querySelector('#status').textContent.includes('time limit')")
    assert page.evaluate('window.aborted')
    assert page.locator('#retry').is_visible()
    assert page.locator('#edition').is_disabled()
    assert page.locator('#cards .card').count()==0
    page.evaluate('''encoded => {
      const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
      window.fetch=async()=>new Response(bytes,{status:200});
    }''',base64.b64encode(ARCHIVE).decode('ascii'))
    page.locator('#retry').click()
    page.wait_for_function('document.querySelectorAll(".card").length===6')
    assert page.locator('#edition').is_enabled()
    assert page.locator('#status').inner_text().startswith('6 of 6 measured series')
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    print('PASS timeout abort, disabled error state, user-controlled retry, real retained evidence restored')
    browser.close()
print('PASS real Chromium controlled-DOM transport regressions; public Pages NOT_VERIFIED')
