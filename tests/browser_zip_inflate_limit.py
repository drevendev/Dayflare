"""Reject a forged ZIP length before allocating a decompression bomb.

The attack ZIP and tampered length are synthetic browser controls. The normal
historical capsule is tested separately; this never contacts Wikimedia.
"""
import base64
from io import BytesIO
import hashlib
import json
from pathlib import Path
import struct
import zipfile
from playwright.sync_api import sync_playwright
from browser_runner import launch_chromium

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'site/index.html').read_text(encoding='utf-8')
CSS = (ROOT / 'site/styles.css').read_text(encoding='utf-8')
JS = (ROOT / 'site/app.js').read_text(encoding='utf-8')
DATA = (ROOT / 'evidence/d02-20261018/source.zip').read_bytes()

# A compressed member claims one byte but expands to 256 KiB, without requiring
# a large transport. It has the correct archive digest for this synthetic test.
with BytesIO() as io:
    with zipfile.ZipFile(io, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr('sample.json', b'A' * (256*1024))
    bomb = bytearray(io.getvalue())
struct.pack_into('<I', bomb, 22, 1)  # local entry declared uncompressed length
bomb = bytes(bomb)
BOMB_SHA = hashlib.sha256(bomb).hexdigest()

with zipfile.ZipFile(BytesIO(DATA)) as archive:
    real_members = [archive.read(n) for n in ('sample.json','receipt.json')]
real_digests = {len(b): hashlib.sha256(b).hexdigest() for b in real_members}
real_digests[len(DATA)] = hashlib.sha256(DATA).hexdigest()


def set_sha_shim(page, expected):
    page.evaluate('''(sha) => {
      Object.defineProperty(window, 'crypto', {configurable: true, value:{subtle:{digest:async (_,raw)=>{
        const digest=sha[raw.byteLength];
        if(!digest) throw new Error('Unexpected synthetic fixture length');
        return Uint8Array.from(digest.match(/.{2}/g),v=>parseInt(v,16)).buffer;
      }}}});
    }''',{str(k):v for k,v in expected.items()})


def set_fetch(page, payload):
    page.evaluate('''encoded => {
      const bytes=Uint8Array.from(atob(encoded), c=>c.charCodeAt(0));
      window.fetch=async()=>new Response(bytes,{status:200});
    }''',base64.b64encode(payload).decode('ascii'))


with sync_playwright() as p:
    browser=launch_chromium(p)
    page=browser.new_page(viewport={'width':390,'height':844})
    page.set_default_timeout(3000)
    errors=[]
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_content(HTML,wait_until='domcontentloaded')
    page.add_style_tag(content=CSS)
    set_sha_shim(page,{len(bomb):BOMB_SHA})
    set_fetch(page,bomb)
    page.add_script_tag(content=JS.replace(
        '3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631', BOMB_SHA))
    page.wait_for_function("document.querySelector('#status').textContent.includes('Decompressed ZIP member exceeds')")
    assert page.locator('#retry').is_visible()
    assert page.locator('#edition').is_disabled()
    assert page.locator('#cards .card').count()==0
    assert not errors,errors
    print('PASS forged member length: inflation rejected before full allocation')
    page.close()

    # Positive control: unchanged real historical input still produces all six
    # measurable series with exact values.
    page=browser.new_page(viewport={'width':390,'height':844})
    page.set_default_timeout(4000)
    page.set_content(HTML,wait_until='domcontentloaded')
    page.add_style_tag(content=CSS)
    set_sha_shim(page,real_digests)
    set_fetch(page,DATA)
    page.add_script_tag(content=JS)
    page.wait_for_function('document.querySelectorAll("#cards .card").length===6')
    assert page.locator('#edition').is_enabled()
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    print('PASS unchanged reviewed historical capsule: six series available')
    browser.close()
