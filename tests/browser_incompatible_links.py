"""Actual Chromium browser regression for stale M0 state after malformed permalink.

Uses the unchanged, independently hash-verified 210-observation ZIP. WebCrypto is
replaced only in the insecure about:blank test DOM (see browser_smoke.py); this is
not public HTTP/Pages or end-to-end source retrieval evidence.
"""
import ast
import base64
import hashlib
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from zipfile import ZipFile
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'evidence/d02-20261018/source.zip'
raw=BASE.read_bytes()
expected={'source.zip':'3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631',
          'sample.json':'98880f706c0d8b5433f0fbb46bcad0cb9a2d515ea894752dcd971326e5805a8e',
          'receipt.json':'298c6ade24ec911502f4e2bee23e4c3ac012eecc8192b56071210d3cf94adb21'}
assert hashlib.sha256(raw).hexdigest()==expected['source.zip']
with ZipFile(BASE) as z:
    for key in ('sample.json','receipt.json'):
        assert hashlib.sha256(z.read(key)).hexdigest()==expected[key]
# Reuse exactly the previously accepted controlled-DOM initialization, not a
# different snapshot or a new browser/network privilege path.
tree=ast.parse((ROOT/'tests/browser_smoke.py').read_text())
INIT=next(n.value.value for n in tree.body if isinstance(n,ast.Assign) and
          any(isinstance(t,ast.Name) and t.id=='INIT' for t in n.targets))
HTML=(ROOT/'site/index.html').read_text()
CSS=(ROOT/'site/styles.css').read_text()
JS=(ROOT/'site/app.js').read_text()

def replace(url, key, value):
    chunks=urlsplit(url)
    params=parse_qs(chunks.query, keep_blank_values=True)
    params[key]=[value]
    return urlunsplit((chunks.scheme,chunks.netloc,chunks.path,urlencode(params,doseq=True),chunks.fragment))

with sync_playwright() as p:
    browser=launch_chromium(p)
    for width in (320,390,1280):
        page=browser.new_page(viewport={'width':width,'height':900})
        errors=[]
        page.on('pageerror',lambda e: errors.append(str(e)))
        page.set_content(HTML)
        page.add_style_tag(content=CSS)
        page.evaluate(INIT,base64.b64encode(raw).decode('ascii'))
        page.add_script_tag(content=JS)
        page.wait_for_function('document.querySelectorAll(".card").length===6',timeout=15000)
        scenarios=[
            ('ds','wrong-snapshot'),('m','incompatible-method'),('w','20260601-20260701'),
            ('s','10'),('ed','ru.wikipedia.org'),('c','2'),
            ('e','unknown.wikipedia.org'),('sub','fictional-subject'),
            # A permalink with repeated meaning-bearing parameters is ambiguous,
            # even when the first value passes validation or both are identical.
            ('dup:ds','wrong-snapshot'),('dup:s','5'),('dup:m','v0-empirical-35d'),('dup:c','5')]
        for field,value in scenarios:
            # Make the stale data fully visible first, including compare totals.
            page.locator('.card').nth(2).click()
            page.locator('#compare-select').select_option('5')
            assert page.locator('#detail').is_visible()
            assert page.locator('#comparison').is_visible()
            assert page.locator('#history tr').count()==35
            if field.startswith('dup:'):
                link=page.evaluate('''arg => {const u=new URL(location.href);
                  u.searchParams.append(arg.key,arg.value);return u.toString();}''',
                  {'key':field[4:],'value':value})
            else:
                link=replace(page.url,field,value)
            page.evaluate('url => {history.pushState({},"",url); dispatchEvent(new PopStateEvent("popstate"));}',link)
            assert page.locator('#retry').is_visible(),(width,field,'missing recovery button')
            assert page.locator('#edition').is_disabled(),(width,field,'filters not disabled')
            assert page.locator('#copy').is_disabled(),(width,field,'share still enabled')
            assert not page.locator('#detail').is_visible(),(width,field,'STALE DETAIL VISIBLE')
            assert not page.locator('#comparison').is_visible(),(width,field,'STALE COMPARISON VISIBLE')
            assert page.locator('#history tr').count()==0,(width,field,'stale history retained')
            assert page.locator('#compare-table tr').count()==0,(width,field,'stale comparison retained')
            assert page.locator('.card').count()==0,(width,field,'stale cards retained')
            assert page.locator('#status').get_attribute('class')=='error'
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(width,field,'overflow')
            if width==390 and field=='s':
                page.screenshot(path=str(ROOT/'shared-link-error-390.png'),full_page=True)
            if field=='dup:ds' and width in (390, 1280):
                page.screenshot(path=str(ROOT/f'shared-link-duplicate-{width}.png'),full_page=True)
            # Recover cleanly and reselect a topic in the *same* document.
            page.locator('#retry').click()
            assert page.locator('.card').count()==6,(width,field,'recovery failed',page.url,page.locator('#status').inner_text())
            assert page.locator('#edition').is_enabled(),(width,field,'filters not restored')
            assert not page.locator('#detail').is_visible(),(width,field,'old selection returned')
        assert not errors,(width,errors)
        print(f'PASS {width}px: 12 invalid permalink states hide all stale values and recover')
        page.close()
    browser.close()
print('PASS: controlled DOM Chromium only; no hosted/public HTTP check')
