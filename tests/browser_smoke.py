"""Offline DOM-browser smoke; browser navigation is policy-blocked in this environment.
The digest shim only substitutes browser WebCrypto unavailable on about:blank; archive
and member hashes are independently checked using real hashlib before this smoke.
"""
import base64, hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]
ZIP=(ROOT/'evidence/d02-20261018/source.zip').read_bytes()
EXPECTED={'source.zip':'3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631','sample.json':'98880f706c0d8b5433f0fbb46bcad0cb9a2d515ea894752dcd971326e5805a8e','receipt.json':'298c6ade24ec911502f4e2bee23e4c3ac012eecc8192b56071210d3cf94adb21'}
assert hashlib.sha256(ZIP).hexdigest()==EXPECTED['source.zip']
with ZipFile(ROOT/'evidence/d02-20261018/source.zip') as z:
 for name in ('sample.json','receipt.json'): assert hashlib.sha256(z.read(name)).hexdigest()==EXPECTED[name]
INIT="""(base64) => {
  const binary=atob(base64);const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
  window.fetch=async()=>new Response(bytes, {status:200,headers:{'Content-Type':'application/zip'}});
  const shaByLength = {4311:'3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631',42711:'98880f706c0d8b5433f0fbb46bcad0cb9a2d515ea894752dcd971326e5805a8e',13453:'298c6ade24ec911502f4e2bee23e4c3ac012eecc8192b56071210d3cf94adb21'};
  Object.defineProperty(window,'crypto',{configurable:true,value:{subtle:{digest: async(type,raw)=>{
    const h=shaByLength[raw.byteLength];if(!h)throw new Error('unmapped test input');
    return Uint8Array.from(h.match(/.{2}/g),x=>parseInt(x,16)).buffer;
  }}}});
}"""
HTML=(ROOT/'site/index.html').read_text(encoding='utf8')
CSS=(ROOT/'site/styles.css').read_text(encoding='utf8')
JS=(ROOT/'site/app.js').read_text(encoding='utf8')
with sync_playwright() as p:
 browser=launch_chromium(p)
 for width in (320,390,1280):
  page=browser.new_page(viewport={'width':width,'height':850})
  errs=[];page.on('pageerror',lambda err:errs.append(str(err)))
  page.set_content(HTML,wait_until='domcontentloaded');page.add_style_tag(content=CSS)
  page.evaluate(INIT,base64.b64encode(ZIP).decode())
  page.add_script_tag(content=JS)
  page.wait_for_function('document.querySelectorAll(".card").length===6',timeout=10000)
  assert not errs,errs
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  assert page.locator('#copy').is_disabled() and page.locator('#compare-select').is_disabled()
  page.locator('.card').nth(2).focus();page.keyboard.press('Enter')
  assert page.locator('#detail-title').inner_text()=='Chess'
  assert page.evaluate('document.activeElement.id')=='detail-title'
  assert page.locator('#copy').is_enabled()
  assert page.locator('#history tr').count()==35
  assert '+7.8%' in page.locator('#detail-summary').inner_text()
  page.locator('#compare-select').select_option('5')
  assert page.locator('#compare-table tbody tr').count()==5
  u=page.url;assert 'ds=d02-20261018-084126' in u and 's=2' in u and 'c=5' in u
  page.set_content(HTML);page.add_style_tag(content=CSS);page.evaluate(INIT,base64.b64encode(ZIP).decode());page.add_script_tag(content=JS)
  page.wait_for_function('document.querySelector("#detail-title").textContent==="Chess"')
  assert page.locator('#compare-select').input_value()=='5'
  page.locator('#subject').select_option('science/technology')
  assert page.locator('.card').count()==2
  page.locator('#query').fill('not a topic in this sample')
  assert page.locator('.card').count()==0 and page.locator('#empty').is_visible()
  page.locator('#clear').click()
  assert page.locator('.card').count()==6
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'overflow after detail/compare'
  page.screenshot(path=str(ROOT/f'ui-{width}.png'),full_page=True)
  print(f'PASS {width}px: real 210-observation ZIP, six cards, detail, table, compare, versioned link; overflow={page.evaluate("document.documentElement.scrollWidth > innerWidth")}')
  page.close()
 # Error state while loading; no fake data or enabled controls
 page=browser.new_page()
 page.set_content(HTML);page.add_style_tag(content=CSS)
 page.evaluate(INIT,base64.b64encode(ZIP).decode())
 page.evaluate("window.fetch=async()=>new Response('failure',{status:503})")
 page.add_script_tag(content=JS)
 page.wait_for_function('document.querySelector("#status").textContent.includes("HTTP 503")')
 assert page.locator('.card').count()==0 and page.locator('#edition').is_disabled() and page.locator('#retry').is_visible()
 print('PASS HTTP failure: no data, controls disabled, retry visible')
 page.evaluate(INIT,base64.b64encode(ZIP).decode())
 page.locator('#retry').click()
 page.wait_for_function('document.querySelectorAll(".card").length===6')
 print('PASS retry: verified data returns and filters re-enabled')
 page.close()
 mismatch=browser.new_page()
 mismatch.set_content(HTML);mismatch.add_style_tag(content=CSS)
 mismatch.evaluate("history.replaceState({},'', 'about:blank?ds=wrong&m=v0-empirical-35d&w=20260811-20260914&s=2')")
 mismatch.evaluate(INIT,base64.b64encode(ZIP).decode());mismatch.add_script_tag(content=JS)
 mismatch.wait_for_function('document.querySelector("#status").textContent.includes("different dataset")')
 assert mismatch.locator('.card').count()==0 and mismatch.locator('#edition').is_disabled()
 print('PASS incompatible dataset link: fail-closed, controls disabled')
 mismatch.close()
 browser.close()
print('PASS: offline DOM smoke only; HTTP navigation unavailable under browser policy')
