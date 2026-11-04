"""Verify and browse the retained 4 November EN/RU identity baseline offline.

One historical metadata observation, not pageviews, a second date or a deployment.
Existing D03/source/bundle checks remain authoritative; this is their pinned archive
adapter and reproducible visitor presentation, not another identity validator.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from html import escape
from io import BytesIO
import json
from pathlib import Path
import re
import stat
import tempfile
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED, ZIP_STORED

from tools.m1_bundle_verify import verify_bundle
from tools.m1_identity_panel import PanelError, canonical_bytes, load_panel

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'evidence/m1-identity-20261104'
SNAPSHOT = 'm1-identity-20261104-41814628479'
CAPSULE_SHA256 = 'dc2af08e39296b901e323285793eb0c6268219dab6aac887f4596fc8d881765a'
PROVENANCE_SHA256 = '777e917a657a4f350434ab27a4ec8f61243b8591fff7bc44340a47c0320658b8'
MAX_ARCHIVE = 256 * 1024
MAX_MEMBER = 256 * 1024
MAX_TOTAL = 1024 * 1024
MAX_MEMBERS = 104
ROOT_FILES = {'panel.json', 'collection-report.json', 'internal-consistency.json', 'bundle-manifest.json'}
RAW_NAME = re.compile(r'raw/(?:en|ru)\.wikipedia\.[1-9][0-9]{0,15}\.json\Z')
SUBJECTS = ('culture', 'books', 'games', 'science', 'sport')
EDITIONS = ('en.wikipedia', 'ru.wikipedia')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_file(path: Path, limit: int) -> bytes:
    require(path.is_file() and not path.is_symlink(), f'Missing or linked file: {path.name}')
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    require(0 < len(value) <= limit, f'Empty or oversized file: {path.name}')
    return value


def strict_json(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON field')
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError('Non-finite JSON constant')

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Malformed or excessively nested UTF-8 JSON') from exc
    require(type(value) is dict, 'Expected JSON object')
    return value


def archive_members(raw: bytes) -> dict[str, bytes]:
    """Bound before decoding; never extract untrusted archive paths."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_ARCHIVE, 'Archive byte limit')
    result = {}
    total = 0
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            require(4 < len(infos) <= MAX_MEMBERS, 'Archive member count')
            for info in infos:
                name = info.filename
                require(name == info.orig_filename and name not in result, 'Duplicate or truncated ZIP name')
                require(name in ROOT_FILES or RAW_NAME.fullmatch(name) is not None, 'Unexpected ZIP path')
                mode = stat.S_IFMT(info.external_attr >> 16)
                require(not info.is_dir() and mode in (0, stat.S_IFREG), 'Non-regular ZIP member')
                require(not info.flag_bits & 1, 'Encrypted ZIP member')
                require(info.compress_type in (ZIP_STORED, ZIP_DEFLATED), 'Unsupported ZIP compression')
                require(0 < info.file_size <= MAX_MEMBER, 'ZIP member size limit')
                total += info.file_size
                require(total <= MAX_TOTAL, 'ZIP total size limit')
                with archive.open(info) as stream:
                    data = stream.read(MAX_MEMBER + 1)
                require(len(data) == info.file_size, 'ZIP decoded size mismatch')
                result[name] = data
    except (BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError('Invalid ZIP archive') from exc
    require(ROOT_FILES <= result.keys(), 'Missing required source member')
    return result


def verify_members(files: dict[str, bytes], provenance: dict) -> tuple[dict, dict]:
    """Run the accepted source verifier on exact bytes in a private scratch root."""
    with tempfile.TemporaryDirectory(prefix='dayflare-identity-verify-') as scratch:
        root = Path(scratch)
        for name, data in files.items():
            require(name in ROOT_FILES or RAW_NAME.fullmatch(name) is not None, 'Unexpected source path')
            target = root / name
            target.parent.mkdir(exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
        proof = verify_bundle(root)
        panel = load_panel(root / 'panel.json')
    require(panel['selection']['evidence_kind'] == 'reported_retrieval', 'Real source receipts required')
    days = {row['titles'][-1]['date'] for row in panel['pages']}
    require(days == {provenance['observation_date_utc']}, 'Observation date mismatch')
    times = sorted(row['source']['requested_at'] for row in panel['pages'])
    require(times and times[0] == provenance['retrieval_start_utc'] and
            times[-1] == provenance['retrieval_end_utc'], 'Retrieval window mismatch')
    require(panel['coverage']['obtained_count'] == provenance['obtained_count'] and
            panel['coverage']['intended_count'] == provenance['intended_count'], 'Coverage mismatch')
    require(proof['manifest_sha256'] == provenance['source_manifest_sha256'], 'Source manifest mismatch')
    return panel, proof


def load_retained(root: Path = DEFAULT) -> tuple[dict, dict, dict, dict[str, bytes]]:
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'Missing or linked retained source directory')
    raw = read_file(root / 'source.zip', MAX_ARCHIVE)
    provenance_bytes = read_file(root / 'provenance.json', 16 * 1024)
    require(sha256(raw).hexdigest() == CAPSULE_SHA256, 'Unreviewed retained source archive')
    require(sha256(provenance_bytes).hexdigest() == PROVENANCE_SHA256, 'Unreviewed retained provenance')
    provenance = strict_json(provenance_bytes)
    files = archive_members(raw)
    require(len(files) == provenance['capsule']['members'] and
            sum(map(len, files.values())) == provenance['capsule']['decoded_bytes'], 'Retained inventory mismatch')
    panel, proof = verify_members(files, provenance)
    return panel, proof, provenance, files


def page_anchor(row: dict) -> str:
    ref = row['page_ref']
    return f"{SNAPSHOT}-{ref['project'].split('.')[0]}-{ref['page_id']}"


def render(panel: dict, provenance: dict) -> bytes:
    """No scripts or remote assets; all source links work without JavaScript."""
    esc = lambda value: escape(str(value), quote=True)
    cells = panel['coverage']['observed_panel_counts_by_edition_subject']
    coverage = ''.join('<tr><th scope="row">' + esc(subject.title()) + '</th>' +
                       ''.join('<td>' + esc(cells.get(edition, {}).get(subject, 'Not observed')) + '</td>'
                               for edition in EDITIONS) + '</tr>' for subject in SUBJECTS)
    sections = []
    for subject in SUBJECTS:
        cards = []
        for row in panel['pages']:
            if row['subject'] != subject:
                continue
            ref, observed, source, mapping = row['page_ref'], row['titles'][-1], row['source'], row['wikidata']
            edition, pid = ref['project'], ref['page_id']
            name = f'raw/{edition}.{pid}.json'
            qid = mapping['observed_qid']
            qid_html = ('<a href="https://www.wikidata.org/wiki/' + esc(qid) + '">' + esc(qid) + '</a>') if qid else 'Not observed'
            cards.append(f'''<article class="card" id="{page_anchor(row)}" tabindex="-1">
<p class="eyebrow">{esc(edition)} · {esc(subject)}</p><h3>{esc(observed['title'])}</h3>
<dl><dt>Local page ID</dt><dd>{pid}</dd><dt>Observed Wikidata</dt><dd>{qid_html}</dd>
<dt>Resolved mapping</dt><dd>{esc(mapping['resolved_qid'] or 'Not resolved')}</dd>
<dt>Continuity</dt><dd>{esc(row['continuity'])}</dd></dl>
<p class="links"><a href="#{page_anchor(row)}">Link to this dated record</a>
<a href="https://{esc(edition)}.org/?curid={pid}">Current Wikipedia page</a></p>
<details><summary>Inspect exact source evidence</summary>
<dl><dt>Observed on (UTC)</dt><dd>{esc(observed['date'])}</dd>
<dt>Requested at (UTC)</dt><dd>{esc(source['requested_at'])}</dd>
<dt>HTTP status</dt><dd>{source['http_status']}</dd>
<dt>Decoded JSON bytes</dt><dd>{source['response_bytes']}</dd>
<dt>SHA-256</dt><dd><code>{esc(source['body_sha256'])}</code></dd></dl>
<p><a href="source/{name}">Retained raw JSON response</a> · <a href="{esc(source['endpoint'])}">Exact API request (current response)</a></p>
<p>These links do not verify historical moves, deletions or cross-edition equivalence.</p>
</details></article>''')
        sections.append(f'<section id="{subject}"><h2>{subject.title()}</h2><div class="cards">' + ''.join(cards) + '</div></section>')
    nav = ''.join(f'<a href="#{subject}">{subject.title()}</a>' for subject in SUBJECTS)
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><title>Dayflare · Observed identities · 4 November 2026</title>
<style>
:root{{color-scheme:light;--ink:#172c3b;--muted:#475c68;--paper:#f4f5ee;--line:#c5d1cc;--accent:#075e59}}
*{{box-sizing:border-box}}html{{scroll-padding-top:1rem}}body{{margin:0;background:var(--paper);color:var(--ink);font:1rem/1.6 system-ui,sans-serif;overflow-wrap:anywhere}}
main,header,footer{{max-width:1120px;margin:auto;padding:1.25rem}}header{{padding-top:2.5rem}}
h1{{font-size:clamp(2rem,6vw,3.8rem);line-height:1.1;max-width:18ch;margin:.6rem 0 1rem;letter-spacing:-.04em}}h2{{font-size:1.65rem;margin:2rem 0 1rem}}h3{{font-size:1.35rem;margin:.25rem 0 1rem;line-height:1.3}}
a{{color:var(--accent);text-underline-offset:.2em}}a:focus-visible,summary:focus-visible,[tabindex]:focus-visible{{outline:3px solid #8c3e12;outline-offset:4px}}
.skip{{position:absolute;left:1rem;top:-6rem;background:white;padding:1rem;z-index:1}}.skip:focus{{top:.5rem}}
.eyebrow{{font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:700}}
.lead{{max-width:65ch;font-size:1.15rem}}.notice{{border-left:4px solid var(--accent);padding:1rem;background:#e6efea;max-width:78ch}}
nav,.links{{display:flex;flex-wrap:wrap;gap:.5rem 1rem}}nav a,.links a{{display:inline-block;min-height:44px;padding:.55rem 0}}
.cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}}.card{{background:white;border:1px solid var(--line);border-radius:1rem;padding:1.25rem;min-width:0;scroll-margin-top:1rem}}
dl{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:.4rem 1rem;margin:0}}dt{{color:var(--muted)}}dd{{margin:0;min-width:0}}code{{font-size:.82em;word-break:break-all}}
details{{border-top:1px solid var(--line);padding-top:.75rem;margin-top:.5rem}}summary{{cursor:pointer;min-height:44px;padding:.4rem 0;font-weight:650}}details p{{margin-bottom:0}}
.coverage{{max-width:36rem}}table{{border-collapse:collapse;width:100%;table-layout:fixed}}th,td{{text-align:left;padding:.6rem;border-bottom:1px solid var(--line)}}caption{{text-align:left;color:var(--muted);padding:.5rem 0}}
footer{{border-top:1px solid var(--line);margin-top:2rem;font-size:.9rem}}.primary{{font-weight:700}}.record-id{{font-size:.85rem;color:var(--muted)}}
@media(max-width:650px){{.cards{{grid-template-columns:1fr}}header{{padding-top:1.5rem}}.card{{padding:1rem}}dl{{grid-template-columns:minmax(0,1fr)}}dd{{margin-bottom:.3rem}}}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}
</style></head><body><a class="skip" href="#records">Skip to observed records</a>
<header><p class="eyebrow">Dayflare / source notebook / EN + RU Wikipedia</p>
<h1>Know which page you are looking at.</h1>
<p class="lead">Explore {len(panel['pages'])} selected Wikipedia identities, their observed names and exact source evidence across culture, books, games, science and sport.</p>
<div class="notice"><strong>Historical metadata snapshot · {esc(provenance['observation_date_utc'])} UTC</strong><br>
Retrieved {esc(provenance['retrieval_start_utc'])} – {esc(provenance['retrieval_end_utc'])}. This is a retained observation, not a live refresh or a popularity chart.</div>
<p><a class="primary" href="#records">Explore the observed records ↓</a></p><nav aria-label="Browse by subject">{nav}</nav>
<p class="record-id">Snapshot: {SNAPSHOT}</p></header>
<main id="records" tabindex="-1"><section class="coverage" aria-labelledby="coverage-heading"><h2 id="coverage-heading">What is covered?</h2>
<p><strong>{panel['coverage']['obtained_count']} of {panel['coverage']['intended_count']}</strong> selected local page identities retained. Selection is curated, not representative. Missing identities never mean zero attention.</p>
<table><caption>Observed page counts in this panel, not pageviews or people.</caption><thead><tr><th scope="col">Subject</th><th scope="col">English</th><th scope="col">Russian</th></tr></thead><tbody>{coverage}</tbody></table>
<p>Wikidata IDs are observations, not independently resolved mappings. Two editions sharing an ID do not establish equivalent page scope or continuous history.</p></section>
{''.join(sections)}
<section id="downloads"><h2>Reproduce or compare later</h2><p>This is the first durably retained raw baseline for the two-date comparison. A separately collected later date is still required; no second snapshot or change is invented.</p>
<p class="links"><a href="source/panel.json">Original panel JSON</a><a href="provenance.json">Retention provenance</a><a href="verification.json">Recomputed source checks</a><a href="manifest.json">Build hashes</a></p>
<p>Page IDs, titles and observed QIDs agree with the retained decoded JSON. Checksums establish byte agreement, not independent authentication of Wikimedia transport. Compressed wire bodies are not retained. No article text or images are included.</p>
</section></main><footer><p>Source: English and Russian Wikipedia Action API metadata; observed Wikidata identifiers. No pageview histories, lifecycle labels, causal claims or national-population comparisons.</p>
<p><a href="https://github.com/drevendev/Dayflare/actions/runs/{provenance['source']['run_id']}">Original collection run</a> · <a href="https://github.com/drevendev/Dayflare/issues/145">Two-date comparison work</a></p></footer></body></html>'''
    return page.encode('utf-8')


def output_files(source: Path = DEFAULT) -> dict[str, bytes]:
    panel, proof, provenance, members = load_retained(source)
    files = {'source/' + name: data for name, data in members.items()}
    files['index.html'] = render(panel, provenance)
    files['provenance.json'] = canonical_bytes(provenance)
    files['verification.json'] = canonical_bytes(proof)
    files['manifest.json'] = canonical_bytes({
        'schema_version': 'dayflare.retained-identity-preview.v1', 'snapshot_id': SNAPSHOT,
        'source_capsule_sha256': CAPSULE_SHA256, 'observation_date_utc': provenance['observation_date_utc'],
        'status': 'BUILT_NOT_DEPLOYED', 'pageviews': 'NOT_COLLECTED',
        'files_sha256': {name: sha256(data).hexdigest() for name, data in sorted(files.items())},
    })
    return files


def build(destination: Path, source: Path = DEFAULT, *, check: bool = False) -> dict[str, bytes]:
    files = output_files(source)  # Validate completely before touching the destination.
    destination = Path(destination)
    if check:
        require(destination.is_dir() and not destination.is_symlink(), 'Missing or linked preview')
        paths = list(destination.rglob('*'))
        require(not any(path.is_symlink() for path in paths), 'Linked preview member')
        actual = {path.relative_to(destination).as_posix() for path in paths if path.is_file()}
        require(actual == set(files), 'Preview inventory mismatch')
        for name, data in files.items():
            require(read_file(destination / name, MAX_TOTAL) == data, 'Preview bytes differ: ' + name)
        return files
    destination.mkdir(parents=False, exist_ok=False)  # One winner; never replace last-good output.
    for name in sorted(files, key=lambda name: (name == 'manifest.json', name)):
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(files[name])
    return files


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', nargs='?', type=Path)
    parser.add_argument('--source', type=Path, default=DEFAULT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.destination is None:
            require(not args.check, '--check requires a preview directory')
            _, proof, _, _ = load_retained(args.source)
            print(json.dumps(proof, sort_keys=True))
        else:
            build(args.destination, args.source, check=args.check)
            print(('VERIFIED' if args.check else 'BUILT') + ' retained real identity baseline; NOT DEPLOYED')
    except (OSError, ValueError, PanelError, KeyError, TypeError) as exc:
        parser.exit(2, f'INVALID RETAINED IDENTITY: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
