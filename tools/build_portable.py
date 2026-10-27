"""Generate a single-file historical Dayflare M0 preview from retained D02 evidence.

Local integration artifact for review only; NOT a Pages publishing/deployment tool.
No collection, network access or mutation of the source archive.
"""
from __future__ import annotations

import argparse
from html import escape
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "evidence/d02-20261018/source.zip"
EXPECTED = {
    "source.zip": "3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631",
    "sample.json": "98880f706c0d8b5433f0fbb46bcad0cb9a2d515ea894752dcd971326e5805a8e",
    "receipt.json": "298c6ade24ec911502f4e2bee23e4c3ac012eecc8192b56071210d3cf94adb21",
}
DESTINATION = ROOT / "Dayflare-M0-portable-historical-UNPUBLISHED.html"
PROVENANCE_SHA256 = "d7265c3e246302e670c107cf9f7c7679fb9c2190e911505a2c9ec3402f386881"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_evidence() -> dict:
    archive = ARCHIVE.read_bytes()
    if sha256(archive) != EXPECTED["source.zip"]:
        raise ValueError("Retained archive does not match recorded SHA-256")
    with ZipFile(ARCHIVE) as z:
        if set(z.namelist()) != {"sample.json", "receipt.json"}:
            raise ValueError("Unexpected retained ZIP members")
        files = {}
        for name in ("sample.json", "receipt.json"):
            info = z.getinfo(name)
            if info.file_size > 128 * 1024 or info.compress_size > 128 * 1024:
                raise ValueError("Unexpected ZIP member size")
            member = z.read(name)
            if sha256(member) != EXPECTED[name]:
                raise ValueError(f"Retained member {name} does not match SHA-256")
            files[name] = json.loads(member)
    receipt, sample = files["receipt.json"], files["sample.json"]
    if (receipt.get("schema_version") != 1
            or receipt.get("method_version") != "v0-empirical-35d"
            or not receipt.get("success")
            or receipt.get("request_count") != 6
            or receipt.get("observation_window") != {"start": "20260811", "end": "20260914", "expected_days": 35}
            or not isinstance(sample, list) or len(sample) != 6
            or any(len(series.get("items", [])) != 35 for series in sample)):
        raise ValueError("Unexpected source coverage, method or readiness")
    return files


def build_html() -> bytes:
    files = read_evidence()
    html = (ROOT / "site/index.html").read_text(encoding="utf-8")
    css = (ROOT / "site/styles.css").read_text(encoding="utf-8")
    js = (ROOT / "site/app.js").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="styles.css">' in html
    assert '<script src="app.js" defer></script>' in html
    assert '</style' not in css.lower() and '</script' not in js.lower()
    html = html.replace('<link rel="stylesheet" href="styles.css">', '<style>\n' + css + '\n</style>', 1)
    html = html.replace('<script src="app.js" defer></script>', '', 1)
    # Source HTTP transport is bounded and abortable; the portable view is
    # separate and uses the validated embedded snapshot without any network.
    original = "const raw=await downloadZip();const data=await readZip(raw);"
    js = js.replace(original, "const data=JSON.parse(document.getElementById('dayflare-evidence').textContent);", 1)
    js = js.replace("'Retry loading the retained snapshot'", "'Recheck embedded historical evidence'")
    js = js.replace('Exact dataset- and method-bound link copied.', 'Local-only version-bound link copied; not a public URL.')
    payload = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    insertion = ("<script type=\"application/json\" id=\"dayflare-evidence\">"
                 + payload + "</script>\n<script>\n" + js + "\n</script>")
    if html.count('</body>') != 1:
        raise ValueError("Unexpected HTML document shape")
    html = html.replace('</body>', insertion + '\n</body>', 1)
    html = html.replace('Dayflare — an atlas of Wikipedia attention',
                        'Dayflare — historical atlas (offline, unpublished)')
    # The source homepage leads to a newer 20-title, file-backed atlas.
    # This ONE-FILE M0 preview embeds only the six older historical series.
    # Translate its first screen and navigation instead of offering dead
    # local links, implying 700 embedded observations, or hiding the fact
    # that the portable artifact is not a published site.
    offline_home = {
        'content="Explore 20 measured English and Russian Wikipedia title histories across five subjects with exact 35-day counts, source evidence and archived dates."':
            'content="Offline historical preview of six selected English and Russian Wikipedia pageview series, 11 August–14 September 2026; unpublished and not live."',
        'HISTORICAL EN/RU ATLAS · ARCHIVED':
            'HISTORICAL ATLAS · OFFLINE PREVIEW · NOT PUBLISHED',
        '20 REAL TITLE HISTORIES · FIVE SUBJECT AREAS':
            'ENGLISH + RUSSIAN WIKIPEDIA · SIX-SERIES OFFLINE PREVIEW',
        'Discover 20 measured English and Russian Wikipedia title histories across culture, books, games, science and sport. Inspect complete 35-day counts and source evidence; the earlier six-series experiment remains below.':
            'Explore six measured pageview histories across science, literature and chess. Exact daily counts and source evidence are embedded in this offline file.',
        '<a class="primary" href="m1-curated-20261023.html">Explore 20 measured histories <span aria-hidden="true">↗</span></a>':
            '<a class="primary" href="#discover">Explore six measured histories <span aria-hidden="true">↗</span></a>',
        '<div class="hero-foot"><strong>19 Sep – 23 Oct 2026</strong><span>700 exact daily values · retrieved 26 Oct 2026 · selected and archived, not live. <a href="#discover">Earlier six-series experiment ↘</a></span></div>':
            '<div class="hero-foot"><strong>11 Aug – 14 Sep 2026</strong><span>35 complete UTC days · 6 preselected series · not live</span></div>',
        'EARLIER SAMPLE / CHESS · EN': 'THE NUMBERS / CHESS · EN',
        'EARLIER SIX-SERIES SAMPLE': 'ARCHIVED SNAPSHOT',
        'Last observation in this sample': 'Last observation',
    }
    for before, after in offline_home.items():
        if html.count(before) != 1:
            raise ValueError(f'Unexpected portable home source: {before[:70]}')
        html = html.replace(before, after, 1)
    # Companion source pages are not bundled into portable M0 HTML.
    # Keep their original links in the multi-file Pages source only.
    for label in (
        '20 source-bound measured subject histories',
        'Additional observed identity evidence',
        'Additional measured culture and games evidence',
    ):
        pattern = r'<section class="notice" aria-label="' + re.escape(label) + r'">.*?</section>'
        html, removed = re.subn(pattern, '', html)
        if removed != 1:
            raise ValueError(f'Unexpected companion notice in portable source: {label}')
    html = html.replace('Counts are page requests, not unique people or approval.',
                        'Counts are page requests, not unique people or approval. Copied links work only with this local file; public sharing awaits publication.')
    # A standalone HTML is not a site directory. Point local evidence and
    # home links to actual sections, not files the reader does not have.
    link_rewrites = {
        'href="../evidence/d02-20261018/README.md"': ('href="#offline-method"', 1),
        'href="../evidence/d02-20261018/provenance.json"': ('href="#offline-provenance"', 2),
        'class="brand" href="./"': ('class="brand" href="#discover"', 1),
    }
    for before, (after, count) in link_rewrites.items():
        if html.count(before) != count:
            raise ValueError(f'Unexpected portable evidence link count: {before}')
        html = html.replace(before, after)
    provenance_raw = (ROOT / 'evidence/d02-20261018/provenance.json').read_bytes()
    if sha256(provenance_raw) != PROVENANCE_SHA256:
        raise ValueError('Retained provenance document does not match reviewed SHA-256')
    provenance = json.loads(provenance_raw)
    if (provenance.get('dataset_id') != 'd02-20261018-084126'
            or provenance.get('capsule', {}).get('sha256') != EXPECTED['source.zip']):
        raise ValueError('Portable source provenance does not match embedded evidence')
    provenance_text = escape(json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True))
    evidence_panel = ("""<section class="section detail" id="offline-method" aria-labelledby="offline-method-title">
<span class="eyebrow">04 / OFFLINE METHOD</span>
<h2 id="offline-method-title">Evidence and limits in this file</h2>
<p>This offline preview embeds a verified historical snapshot: six preselected English/Russian Wikipedia pageview series, 35 complete UTC days (11 August–14 September 2026), retrieved 18 October 2026. It is not live or representative of Wikipedia.</p>
<p>Latest week (8–14 September) is compared with the median of four earlier complete seven-day totals. Absolute difference is latest minus median; baseline-relative difference is undefined when that median is zero. Exact daily counts are available under each topic. The <code>user</code> traffic filter does not verify unique people or rule out automated requests.</p>
<p>The embedded <code>sample.json</code> and <code>receipt.json</code> are retained data, not freshly retrieved Wikipedia measurements. The original HTTP bodies, stable page IDs and independent cross-edition entity matches are unavailable. No claims about causes, approval, significance, or lifecycle stages are made. Source API data is CC0; no article text or images are bundled.</p>
<p>This single HTML contains normalized measurements as embedded JSON. It does <strong>not</strong> include the separate ZIP file or a public shareable URL; copied links refer only to your local copy.</p>
<details id="offline-provenance" class="history-disclosure"><summary>Inspect source provenance and SHA-256 receipts</summary>
<pre style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:.76rem">""" + provenance_text + """</pre></details>
</section>""")
    if html.count('</main>') != 1:
        raise ValueError('Unexpected portable main landmark')
    html = html.replace('</main>', evidence_panel + '\n</main>', 1)
    return (html.rstrip() + '\n').encode('utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check the generated HTML without altering it')
    args = parser.parse_args()
    expected = build_html()
    if args.check:
        if DESTINATION.read_bytes() != expected:
            raise SystemExit('PORTABLE_PREVIEW_OUT_OF_DATE')
        print(f'PASS deterministic portable preview: {len(expected):,} bytes; sha256={sha256(expected)}')
    else:
        DESTINATION.write_bytes(expected)
        print(f'WROTE {DESTINATION.name}: {len(expected):,} bytes; sha256={sha256(expected)}')

if __name__ == '__main__':
    main()
