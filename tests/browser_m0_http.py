"""Native Chromium HTTP acceptance of the bounded, retained M0 visitor atlas.

This checks the real release bytes under /Dayflare/ without browser API shims.
It is NOT a GitHub Pages deployment or public-site verification.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from threading import Thread
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARCHIVE = "evidence/d02-20261018/source.zip"
WIDTHS = (320, 390, 1280)
IMAGES = {f"{w}-{s}.png" for w in WIDTHS for s in
          ("overview", "detail", "comparison", "recovery")}
IMAGES |= {"390-nojs.png", "390-missing-data.png", "390-identity.png", "1280-identity.png"}


def stage(members, root):
    root.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(members.items()):
        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts or not p.parts:
            raise ValueError("Unsafe release path")
        target = root.joinpath(*p.parts)
        if not target.resolve().is_relative_to(root.resolve()):
            raise ValueError("Escaping release root")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as out:
            out.write(payload)


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


@contextmanager
def server(root):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(root)))
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/Dayflare/"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def changed_query(url, key, value):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != key]
    query.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(query)))


def cards(page):
    page.locator("#cards .card").first.wait_for(timeout=18000)
    assert page.locator("#cards .card").count() == 6


def no_overflow(page):
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")


def visitor(browser, address, width, pictures):
    context = browser.new_context(viewport={"width": width, "height": 820},
                                  reduced_motion="reduce")
    try:
        page = context.new_page()
        errors, requests = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: requests.append(r.url))
        response = page.goto(address, wait_until="load", timeout=16000)
        assert response and response.status == 200
        assert urlsplit(page.url).path == "/Dayflare/"
        cards(page)
        assert "ARCHIVED SNAPSHOT" in page.locator(".notice[aria-label='Coverage and freshness']").inner_text()
        assert "14 September 2026" in page.locator(".notice[aria-label='Coverage and freshness']").inner_text()
        # Independent source-observation route remains distinct from M0 pageviews.
        assert page.locator(".notice[aria-label='Additional observed identity evidence'] a").get_attribute("href") == "identities-m1-20261024.html"
        assert page.evaluate('typeof crypto.subtle === "object"')
        assert page.evaluate('typeof DecompressionStream === "function"')
        assert requests and all(urlsplit(u).hostname == "127.0.0.1" for u in requests)
        no_overflow(page)
        page.screenshot(path=str(pictures / f"{width}-overview.png"), full_page=True)

        page.keyboard.press("Tab")
        assert page.evaluate('document.activeElement.classList.contains("skip")')
        for _ in range(20):
            page.keyboard.press("Tab")
            if page.evaluate('document.activeElement.classList.contains("card")'):
                break
        else:
            raise AssertionError("No keyboard discovery")
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        assert "Chess" in page.evaluate("document.activeElement.innerText")
        page.keyboard.press("Enter")
        assert page.locator("#detail-title").inner_text() == "Chess"
        assert page.locator("#history tr").count() == 35
        assert "19,804" in page.locator("#detail-summary").inner_text()
        assert page.evaluate("document.activeElement.id") == "detail-title"
        no_overflow(page)
        page.screenshot(path=str(pictures / f"{width}-detail.png"), full_page=True)

        page.locator("#compare-select").select_option("5")
        assert page.locator("#compare-table tbody tr").count() == 5
        shared = page.url
        q = dict(parse_qsl(urlsplit(shared).query))
        assert (q.get("ds"), q.get("m"), q.get("w")) == (
            "d02-20261018-084126", "v0-empirical-35d", "20260811-20260914")
        assert (q.get("ed"), q.get("s"), q.get("c")) == (
            "en.wikipedia.org", "2", "5")
        assert urlsplit(shared).path == "/Dayflare/" and shared.endswith("#comparison")
        page.locator("#copy").click()
        page.wait_for_function(
            "!document.querySelector('#share-fallback').hidden || "
            "document.querySelector('#share-state').textContent.includes('link copied')",
            timeout=6500)
        if page.locator("#share-fallback").is_visible():
            assert page.locator("#share-url").input_value() == shared
        no_overflow(page)
        page.screenshot(path=str(pictures / f"{width}-comparison.png"), full_page=True)
        page.reload(wait_until="load", timeout=16000)
        page.locator("#comparison").wait_for(timeout=18000)
        assert page.locator("#detail-title").inner_text() == "Chess"
        assert page.locator("#compare-select").input_value() == "5"
        assert page.locator("#compare-table tbody tr").count() == 5
        assert page.url == shared

        page.goto(changed_query(shared, "ds", "unknown-dataset"), wait_until="load")
        page.locator("#retry").wait_for(timeout=18000)
        assert page.locator("#status.error").is_visible()
        assert page.locator(".card").count() == 0 and page.locator("#copy").is_disabled()
        page.locator("#retry").click()
        cards(page)
        page.locator("#query").fill("unavailable-subject")
        assert page.locator("#empty").is_visible() and page.locator(".card").count() == 0
        page.locator("#clear").click()
        cards(page)
        no_overflow(page)
        assert not errors, errors
        page.screenshot(path=str(pictures / f"{width}-recovery.png"), full_page=True)
        print(f"PASS real HTTP {width}px: keyboard/detail/compare/share/empty/retry", flush=True)
    finally:
        context.close()


def identity_view(browser, address, width, pictures):
    # This is an archived current-page identity slice, not M0 pageview history.
    context = browser.new_context(viewport={"width": width, "height": 820},
                                  reduced_motion="reduce", java_script_enabled=False)
    try:
        page = context.new_page()
        response = page.goto(address + "identities-m1-20261024.html",
                             wait_until="load", timeout=16000)
        assert response and response.status == 200
        assert page.locator("article[data-page-ref]").count() == 20
        assert page.locator(".different").count() == 2
        assert page.locator("a[href='identities-m1-20261024.json']").count() == 1
        page.locator("#en-5134 summary").focus()
        page.keyboard.press("Enter")
        assert page.locator("#en-5134 details").get_attribute("open") is not None
        assert page.locator("#en-5134").get_by_text("Q718", exact=False).count() >= 1
        no_overflow(page)
        page.screenshot(path=str(pictures / f"{width}-identity.png"), full_page=True)
        print(f"PASS real local HTTP {width}px: 20 IDs, no-JS, keyboard evidence and no overflow", flush=True)
    finally:
        context.close()


def extra_states(browser, address, root, pictures):
    nojs = browser.new_context(viewport={"width": 390, "height": 820},
                               java_script_enabled=False, reduced_motion="reduce")
    try:
        page = nojs.new_page()
        page.goto(address, wait_until="load", timeout=16000)
        assert page.locator(".nojs-topic").count() == 6
        assert page.locator(".nojs-topic tbody tr").count() == 210
        page.locator(".nojs-topic summary").nth(2).focus()
        page.keyboard.press("Enter")
        assert page.locator(".nojs-topic").nth(2).get_attribute("open") is not None
        no_overflow(page)
        page.screenshot(path=str(pictures / "390-nojs.png"), full_page=True)
    finally:
        nojs.close()

    # Fault injection only against the disposable staged source.
    file = root / "Dayflare" / ARCHIVE
    parked = file.with_suffix(".zip.staged-404")
    context = browser.new_context(viewport={"width": 390, "height": 820}, reduced_motion="reduce")
    try:
        file.rename(parked)
        try:
            page = context.new_page()
            page.goto(address, wait_until="load", timeout=16000)
            page.locator("#retry").wait_for(timeout=18000)
            assert page.locator("#status.error").is_visible()
            assert page.locator(".card").count() == 0 and page.locator("#edition").is_disabled()
            page.screenshot(path=str(pictures / "390-missing-data.png"), full_page=True)
        finally:
            parked.rename(file)
        page.locator("#retry").click()
        cards(page)
    finally:
        context.close()


def screenshot_evidence(folder):
    images = {p.name: p for p in folder.glob("*.png")}
    if images.keys() != IMAGES:
        raise AssertionError(f"Bad screenshot inventory: missing={IMAGES-images.keys()}")
    receipts, total = {}, 0
    for name, path in sorted(images.items()):
        data = path.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 8_000_000:
            raise AssertionError(f"Invalid PNG: {name}")
        offset, width, data_seen = 8, None, False
        while offset < len(data):
            if len(data)-offset < 12:
                raise AssertionError(f"Truncated PNG: {name}")
            length = int.from_bytes(data[offset:offset+4], "big")
            end = offset+12+length
            if end > len(data):
                raise AssertionError(f"Truncated PNG chunk: {name}")
            kind, payload = data[offset+4:offset+8], data[offset+8:end-4]
            if zlib.crc32(kind+payload) & 0xffffffff != int.from_bytes(data[end-4:end], "big"):
                raise AssertionError(f"Corrupted PNG: {name}")
            if offset == 8 and (kind != b"IHDR" or length != 13):
                raise AssertionError(f"Missing PNG IHDR: {name}")
            if kind == b"IHDR":
                if width is not None:
                    raise AssertionError(f"Duplicate IHDR: {name}")
                width = int.from_bytes(payload[:4], "big")
            if kind == b"IDAT":
                data_seen = True
            if kind == b"IEND":
                if length or end != len(data) or not data_seen:
                    raise AssertionError(f"Incomplete PNG: {name}")
                break
            offset = end
        else:
            raise AssertionError(f"Missing PNG end: {name}")
        if width != int(name.split("-")[0]):
            raise AssertionError(f"Wrong viewport screenshot: {name}")
        total += len(data)
        receipts[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                          "width": width}
    if total > 32_000_000:
        raise AssertionError("Screenshot collection exceeds 32MB")
    return receipts


def main():
    from playwright.sync_api import sync_playwright
    from browser_runner import launch_chromium
    from tools.build_static_release import bundle_files

    members = bundle_files(ROOT)
    manifest = json.loads(members["release-manifest.json"])
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   text=True, timeout=5).strip()
    folder = ROOT / "artifacts" / "m0-http"
    folder.mkdir(parents=True, exist_ok=True)
    pictures = Path(tempfile.mkdtemp(prefix="run-", dir=folder))
    receipt = {"status": "INCOMPLETE", "head": head, "dataset": manifest["dataset_id"],
               "method": manifest["method_version"], "type": "LOCAL_HTTP_NOT_PAGES",
               "manifest_sha256": hashlib.sha256(members["release-manifest.json"]).hexdigest()}
    try:
        with tempfile.TemporaryDirectory(prefix="dayflare-http-") as tmp:
            root = Path(tmp)
            stage(members, root / "Dayflare")
            with server(root) as address:
                for name in ("index.html", "app.js", "styles.css", ARCHIVE,
                             "evidence.html", "release-manifest.json"):
                    with urlopen(address + name, timeout=5) as response:
                        assert response.status == 200 and response.read() == members[name], name
                with sync_playwright() as playwright:
                    browser = launch_chromium(playwright)
                    try:
                        for width in WIDTHS:
                            visitor(browser, address, width, pictures)
                        for width in (390, 1280):
                            identity_view(browser, address, width, pictures)
                        extra_states(browser, address, root, pictures)
                    finally:
                        browser.close()
        receipt["screenshots"] = screenshot_evidence(pictures)
        receipt["status"] = "PASS"
        print("PASS local HTTP browser, not public Pages; inspect screenshots before acceptance")
    except Exception as exc:
        receipt["status"] = "FAIL"
        receipt["error"] = (type(exc).__name__ + ": " + str(exc))[:500]
        raise
    finally:
        (pictures / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n")


if __name__ == "__main__":
    main()
