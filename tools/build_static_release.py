"""Produce a deterministic, self-contained, *unpublished* Dayflare Pages bundle.

The source lives at ``site/`` but evidence lives at ``evidence/`` in the
repository.  A Pages publication sourced from only ``site/`` therefore cannot
fetch ``../evidence``.  Rebase the reviewed relative path only in the generated
bundle and verify every asset before exposing a candidate for deployment.

This tool never calls GitHub, Wikimedia or a public publishing endpoint.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import io
import json
import posixpath
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from tools.build_portable import EXPECTED, read_evidence
from tools.m1_observed_panel import validate_bytes, validate_html_bytes
from tools.m1_cross_subject_static import validate_assets
from tools.m1_curated_static import validate_assets as validate_curated_assets

ROOT = Path(__file__).resolve().parents[1]
PATH_BEFORE = "const ZIP_URL = '../evidence/d02-20261018/source.zip';"
PATH_AFTER = "const ZIP_URL = './evidence/d02-20261018/source.zip';"
EVIDENCE = 'evidence/d02-20261018/'
# Read-only public documents are exact Git blobs from Dayflare PR #16 at
# a0d3056f1e629016d846961c3e1209bd1602c201, not rewritten versions.
DOC_GIT_BLOBS = {
    EVIDENCE + 'README.md': 'fcc58c9191f243a8237c3f8d00dbb452835faca8',
    EVIDENCE + 'provenance.json': '2fa4ce482cb1a86825781d9cf17c0a30140c96cd',
}
NICHE_ROUTE = 'dayflare-19-2026-11-23-summary.html'
NICHE_SOURCE = 'downloads/' + NICHE_ROUTE
NICHE_SHA256 = '8045f27d478ee096adac09db35d35f767b45699aaf009483a206d4d617ef1d64'
NICHE_RECEIPT = {
    'route': NICHE_ROUTE,
    'html_sha256': NICHE_SHA256,
    'dataset_fingerprint': '10f78c6ab626a6ff2845b4db3e2e207144389ed387f88e22d31f4eeeeaaa905e',
    'method_version': 'v0-empirical-35d',
    'observation_window_utc': ['2026-10-20', '2026-11-23'],
    'measured_series': 19,
    'daily_observations': 665,
}
NICHE_ENTRY = (
    '<div id="dated-niche-entry">'
    f'<a class="hero-explore" id="open-niche-atlas" href="{NICHE_ROUTE}">'
    '<strong>Open the 19-title atlas</strong>'
    '<small class="niche-window">20 Oct–23 Nov 2026 UTC · 665 daily counts</small>'
    '<small class="niche-scope">Separate EN/RU niche cohort · charts, filters and exact comparisons · historical, not live.</small></a></div>'
)

REQUIRED = {NICHE_ROUTE,'index.html','styles.css','app.js','evidence.html','identities-m1-20261024.html','identities-m1-20261024.json','identity-explorer.js','curated-explorer.js',
            EVIDENCE+'source.zip',*DOC_GIT_BLOBS,'m1-cross-subject-20261025.json','m1-cross-subject-20261025.html',
            'm1-curated-20261023.json','m1-curated-20261023.html','.nojekyll','release-manifest.json'}
INDEX_REWRITES = {
    'href="../evidence/d02-20261018/README.md"': ('href="evidence.html"', 1),
    'href="../evidence/d02-20261018/provenance.json"': ('href="evidence.html#provenance"', 2),
}


# Only these nine reviewed, version-bound same-root historical title links may
# have queries. Each complete URL is allowlisted; all other local URLs remain
# query-free. Never admit unreviewed URL parameters or series combinations.
HISTORY_TITLE_LINKS = frozenset({
    'index.html?ds=d02-20261018-084126&m=v0-empirical-35d&w=20260811-20260914&s=2&ed=en.wikipedia.org#detail',
    'index.html?ds=d02-20261018-084126&m=v0-empirical-35d&w=20260811-20260914&s=5&ed=ru.wikipedia.org#detail',
    'index.html?ds=d02-20261018-084126&m=v0-empirical-35d&w=20260811-20260914&s=2&ed=en.wikipedia.org&c=5#comparison',
    'index.html?ds=d02-20261018-084126&m=v0-empirical-35d&w=20260811-20260914&s=0&ed=en.wikipedia.org#detail',
    'index.html?ds=d02-20261018-084126&m=v0-empirical-35d&w=20260811-20260914&s=3&ed=ru.wikipedia.org#detail',
    'index.html?ds=d02-20261018-084126&m=v0-empirical-35d&w=20260811-20260914&s=0&ed=en.wikipedia.org&c=3#comparison',
    'index.html?ds=d02-20261018-084126&m=v0-empirical-35d&w=20260811-20260914&s=1&ed=en.wikipedia.org#detail',
    'index.html?ds=d02-20261018-084126&m=v0-empirical-35d&w=20260811-20260914&s=4&ed=ru.wikipedia.org#detail',
    'index.html?ds=d02-20261018-084126&m=v0-empirical-35d&w=20260811-20260914&s=1&ed=en.wikipedia.org&c=4#comparison',
})


# Exact reviewed URLs for historic title pairs, not live attention or entity equivalence.
CURATED_COMPARE_LINK = (
    "m1-curated-20261023.html?ds=m1-curated-20261023-d96477427ece"
    "&a=topic-en-3921&b=topic-en-5134#curated-compare"
)

CURATED_CROSS_EDITION_LINK = (
    "m1-curated-20261023.html?ds=m1-curated-20261023-d96477427ece"
    "&a=topic-en-155311&b=topic-ru-6269#curated-compare"
)

CURATED_SUBJECT_PAIRS = {
    "culture": ("topic-en-18839", "topic-ru-463", 19366, 2104),
    "games": ("topic-en-5134", "topic-ru-10646", 25917, 4310),
    "science": ("topic-en-4650", "topic-ru-8474", 50073, 6544),
    "sport": ("topic-en-23976719", "topic-ru-7963", 11121, 3211),
}
CURATED_SUBJECT_COMPARE_LINKS = {
    subject: (
        "m1-curated-20261023.html?ds=m1-curated-20261023-d96477427ece"
        f"&a={left}&b={right}#curated-compare"
    )
    for subject, (left, right, _, _) in CURATED_SUBJECT_PAIRS.items()
}


def _curated_topic_marker(topic: str, latest: int) -> bytes:
    _, edition, page_id = topic.split("-", 2)
    return (
        f'id="{topic}" data-project="{edition}.wikipedia" '
        f'data-observed-page-id="{page_id}" data-latest="{latest}"'
    ).encode("ascii")


def _approved_curated_compare(page: str, ref: str, files: dict[str, bytes]) -> bool:
    if page != "index.html":
        return False
    allowed = {
        CURATED_COMPARE_LINK: (
            _curated_topic_marker("topic-en-3921", 37759),
            _curated_topic_marker("topic-en-5134", 25917),
        ),
        CURATED_CROSS_EDITION_LINK: (
            _curated_topic_marker("topic-en-155311", 14110),
            _curated_topic_marker("topic-ru-6269", 3792),
        ),
    }
    for subject, (left, right, left_week, right_week) in CURATED_SUBJECT_PAIRS.items():
        allowed[CURATED_SUBJECT_COMPARE_LINKS[subject]] = (
            _curated_topic_marker(left, left_week),
            _curated_topic_marker(right, right_week),
        )
    pair = allowed.get(ref)
    if pair is None:
        return False
    archive = files["m1-curated-20261023.html"]
    script = files["curated-explorer.js"]
    if (b'name="dayflare-dataset" content="m1-curated-20261023-d96477427ece"' not in archive or
            b"const DATASET = 'm1-curated-20261023-d96477427ece'" not in script or
            b"compareArea.id = 'curated-compare'" not in script or
            any(marker not in archive for marker in pair)):
        raise ValueError("Unverified dated curated comparison destination")
    return True


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


class _LocalLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if d.get('id'):
            self.ids.add(d['id'])
        if tag in ('a','link','script','img'):
            key = 'href' if tag in ('a','link') else 'src'
            if d.get(key) is not None:
                self.refs.append(d[key])


def verify_release_links(files: dict[str, bytes]) -> None:
    pages = {}
    for page in ('index.html','evidence.html','identities-m1-20261024.html','m1-cross-subject-20261025.html','m1-curated-20261023.html'):
        parser = _LocalLinks()
        parser.feed(files[page].decode('utf-8'))
        pages[page] = parser
    for page, parser in pages.items():
        for ref in parser.refs:
            parsed = urlsplit(ref)
            if parsed.scheme in ('https', 'http'):
                continue  # Wikimedia documentation and article links are intentionally external.
            curated_compare = _approved_curated_compare(page, ref, files)
            if (parsed.scheme or parsed.netloc or
                    (parsed.query and not curated_compare and
                     (page != 'identities-m1-20261024.html' or
                      ref not in HISTORY_TITLE_LINKS))):
                raise ValueError(f'Unsupported release URL in {page}: {ref}')
            raw = unquote(parsed.path)
            if raw.startswith('/') or '..' in raw.split('/') or '\\' in raw:
                raise ValueError(f'Out-of-root release URL in {page}: {ref}')
            target = (page if not raw else posixpath.normpath(posixpath.join(posixpath.dirname(page),raw)))
            if target in ('.', ''):
                target = 'index.html'
            if target not in files:
                raise ValueError(f'Broken local release URL in {page}: {ref}')
            if parsed.fragment and not curated_compare and target in pages and parsed.fragment not in pages[target].ids:
                raise ValueError(f'Broken release fragment in {page}: {ref}')



def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bundle_files(source: Path = ROOT) -> dict[str, bytes]:
    # The existing verifier hashes every archive member and checks readiness.
    if source == ROOT:
        read_evidence()
    else:
        # Test-safe alternate root: the input must match the same canonical
        # archive hash; inspect all members and schema, never rely on ZIP name.
        with ZipFile(source / 'evidence/d02-20261018/source.zip') as archive:
            names = set(archive.namelist())
            if names != {'sample.json','receipt.json'}:
                raise ValueError('Unexpected evidence members')
            for name in names:
                if digest(archive.read(name)) != EXPECTED[name]:
                    raise ValueError(f'Invalid source member: {name}')
            receipt = json.loads(archive.read('receipt.json'))
            sample = json.loads(archive.read('sample.json'))
            if not (receipt.get('success') and receipt.get('method_version') == 'v0-empirical-35d'
                    and receipt.get('schema_version') == 1 and receipt.get('request_count') == 6
                    and receipt.get('observation_window') == {'start':'20260811','end':'20260914','expected_days':35}
                    and len(sample) == 6 and all(len(s['items']) == 35 for s in sample)):
                raise ValueError('Incompatible or incomplete evidence')
    evidence = (source/'evidence/d02-20261018/source.zip').read_bytes()
    if digest(evidence) != EXPECTED['source.zip']:
        raise ValueError('Evidence ZIP checksum mismatch; refusing release')
    html = (source/'site/index.html').read_bytes()
    css = (source/'site/styles.css').read_bytes()
    evidence_page = (source/'site/evidence.html').read_bytes()
    app = (source/'site/app.js').read_text(encoding='utf-8')
    if app.count(PATH_BEFORE) != 1 or PATH_AFTER in app:
        raise ValueError('Unexpected archive path in app; review path rewrite')
    if b'<script src="app.js" defer></script>' not in html or b'<link rel="stylesheet" href="styles.css">' not in html:
        raise ValueError('Missing local HTML asset references')
    patched = app.replace(PATH_BEFORE, PATH_AFTER).encode('utf-8')
    # The repository preview keeps its source-relative paths. Only the
    # generated Pages artifact points visitors to its local evidence page.
    text = html.decode('utf-8')
    for original, (replacement, count) in INDEX_REWRITES.items():
        if text.count(original) != count:
            raise ValueError(f'Unreviewed evidence link in source HTML: {original}')
        text = text.replace(original, replacement)
    # The approved standalone reader has its own immutable bytes, inline
    # assets and version-bound shares. Do not rewrite it or its observations.
    niche = (source / NICHE_SOURCE).read_bytes()
    if len(niche) != 329286 or digest(niche) != NICHE_SHA256:
        raise ValueError('Unverified dated 19-title atlas')
    marker = '<p class="intro">Discover 20 measured'
    if text.count(marker) != 1:
        raise ValueError('Unexpected root atlas entry location')
    text = text.replace(marker, NICHE_ENTRY + '<p class="intro">Discover 20 measured', 1)
    text = text.replace('Latest accepted window:</strong>', 'Earlier 20-title accepted window:</strong>', 1)
    files = {NICHE_ROUTE: niche, 'index.html':text.encode('utf-8'), 'styles.css':css,
             'app.js':patched, 'evidence.html':evidence_page,
             EVIDENCE+'source.zip':evidence, '.nojekyll':b''}
    identity_json=(source/'site/identities-m1-20261024.json').read_bytes()
    identity_html=(source/'site/identities-m1-20261024.html').read_bytes()
    observed=validate_bytes(identity_json)
    validate_html_bytes(identity_html)
    source_html=identity_html.decode('utf-8')
    for page in observed['pages']:
        reference=f'data-page-ref="{page["project"]}:{page["page_id"]}"'
        if source_html.count(reference)!=1 or page['raw_response_sha256'] not in source_html:
            raise ValueError('Observed identity HTML/source mismatch')
    files['identity-explorer.js']=(source/'site/identity-explorer.js').read_bytes()
    if not files['identity-explorer.js'] or len(files['identity-explorer.js']) > 32*1024:
        raise ValueError('Missing or oversized observed-identity explorer script')
    files['curated-explorer.js']=(source/'site/curated-explorer.js').read_bytes()
    if not files['curated-explorer.js'] or len(files['curated-explorer.js']) > 32*1024:
        raise ValueError('Missing or oversized curated measured-history explorer script')
    files['identities-m1-20261024.json']=identity_json
    files['identities-m1-20261024.html']=identity_html
    cross_json=(source/'site/m1-cross-subject-20261025.json').read_bytes()
    cross_html=(source/'site/m1-cross-subject-20261025.html').read_bytes()
    cross_meta=validate_assets(cross_json,cross_html)
    files['m1-cross-subject-20261025.json']=cross_json
    files['m1-cross-subject-20261025.html']=cross_html
    curated_json=(source/'site/m1-curated-20261023.json').read_bytes()
    curated_html=(source/'site/m1-curated-20261023.html').read_bytes()
    curated_meta=validate_curated_assets(curated_json, curated_html, identity_json)
    files['m1-curated-20261023.json']=curated_json
    files['m1-curated-20261023.html']=curated_html
    for name, git_sha in DOC_GIT_BLOBS.items():
        value = (source/name).read_bytes()
        if len(value) > 64 * 1024 or git_blob_sha(value) != git_sha:
            raise ValueError(f'Unverified or changed evidence document: {name}')
        files[name] = value
    provenance = json.loads(files[EVIDENCE+'provenance.json'])
    if (provenance.get('dataset_id') != 'd02-20261018-084126'
            or provenance.get('capsule', {}).get('sha256') != EXPECTED['source.zip']
            or provenance.get('schema_version') != 1):
        raise ValueError('Incompatible source provenance')
    verify_release_links(files)
    manifest = {
        'status':'UNPUBLISHED_STATIC_RELEASE_CANDIDATE',
        'source_scope':'selected EN/RU Wikipedia pageview histories; not live or representative',
        'dataset_id':'d02-20261018-084126',
        'method_version':'v0-empirical-35d',
        'observation_window_utc':['2026-08-11','2026-09-14'],
        'retrieved_utc':'2026-10-18T08:41:26Z',
        'daily_observations':210,
        'auxiliary_identity_dataset':{
            'dataset_id':observed['dataset_id'],
            'observation_date_utc':observed['observation_date_utc'],
            'observed_ids':len(observed['pages']),
            'pageviews':'not_collected',
            'origin_authenticated':False,
        },
        'auxiliary_cross_subject_dataset':cross_meta,
        'auxiliary_curated_title_dataset':curated_meta,
        'auxiliary_niche_atlas': NICHE_RECEIPT,
        'files_sha256':{k:digest(v) for k,v in sorted(files.items())},
        'input_archive_sha256':EXPECTED['source.zip'],
        'provenance_git_blob_sha1': DOC_GIT_BLOBS[EVIDENCE+'provenance.json'],
        'evidence_readme_git_blob_sha1': DOC_GIT_BLOBS[EVIDENCE+'README.md'],
        'notes':'Not a deployment receipt. Publication must be separately authorized and HTTP-verified.'
    }
    files['release-manifest.json'] = (json.dumps(manifest,sort_keys=True,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    if files.keys() != REQUIRED:
        raise ValueError('Incomplete release file inventory')
    return files


def build_zip(files: dict[str,bytes]) -> bytes:
    data = io.BytesIO()
    with ZipFile(data,'w',compression=ZIP_DEFLATED,compresslevel=9) as z:
        for name in sorted(files):
            entry = ZipInfo(name,date_time=(2020,1,1,0,0,0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            z.writestr(entry,files[name],compress_type=ZIP_DEFLATED,compresslevel=9)
    return data.getvalue()


def create_release(destination: Path, source: Path = ROOT, check: bool = False) -> bytes:
    files=bundle_files(source)
    payload=build_zip(files)
    if destination.exists():
        if destination.read_bytes()!=payload:
            raise ValueError('Existing release differs; refusing to overwrite last candidate')
    elif check:
        raise FileNotFoundError('No previously built release to check')
    else:
        destination.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation ensures a failed build cannot replace last good.
        with destination.open('xb') as stream:
            stream.write(payload)
    return payload


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'Dayflare-M0-static-Pages-UNPUBLISHED.zip')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    payload=create_release(args.output,check=args.check)
    print(f'PASS deterministic static candidate: {len(payload)} bytes, sha256={digest(payload)}; deployment NOT_RUN')


if __name__=='__main__':
    main()
