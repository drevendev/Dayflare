"""Preserve a real, independently inspectable M1 30-title Actions bundle offline.

No network, publication, Pages writes, trust enrollment or replacement of the
accepted 20-title release. The output remains an UNPUBLISHED candidate.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from hashlib import sha256
from io import BytesIO
import argparse
import json
from pathlib import Path, PurePosixPath
import stat
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

SCHEMA = 'dayflare.m1-30-preserved-evidence.v1'
MAX_ZIP = 4 * 1024 * 1024
MAX_EXPANDED = 8 * 1024 * 1024
MAX_FILES = 200
SUBJECTS = {'culture', 'books', 'games', 'science', 'sport'}


class ArchiveError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ArchiveError(message)


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def decode(raw: bytes, label: str) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, label + ': duplicate key')
            value[key] = item
        return value
    try:
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                         parse_constant=lambda _: require(False, 'nonfinite number'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ArchiveError(label + ': invalid JSON') from exc
    require(type(obj) is dict, label + ': expected object')
    return obj


def read_zip(path: Path) -> dict[str, bytes]:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_ZIP,
            'source ZIP missing, linked or over budget')
    out = {}
    total = 0
    try:
        with ZipFile(path) as z:
            require(len(z.infolist()) <= MAX_FILES, 'too many source ZIP members')
            for info in z.infolist():
                name = info.filename
                p = PurePosixPath(name)
                require(name and not name.startswith('/') and '\\' not in name
                        and str(p) == name and all(x not in ('', '.', '..') for x in p.parts)
                        and not name.endswith('/') and name not in out,
                        'unsafe or duplicate ZIP path')
                mode = info.external_attr >> 16
                require(not stat.S_ISLNK(mode) and not info.is_dir(), 'ZIP link or directory')
                require(info.file_size <= 1024 * 1024 and not (info.flag_bits & 1),
                        'oversized or encrypted member')
                total += info.file_size
                require(total <= MAX_EXPANDED, 'source ZIP inflated budget exceeded')
                out[name] = z.read(info)
    except (OSError, RuntimeError, EOFError, BadZipFile) as exc:
        raise ArchiveError('invalid source ZIP') from exc
    return out


def verify(files: dict[str, bytes]) -> dict:
    def read(name):
        require(name in files, 'missing ' + name)
        return decode(files[name], name)

    run = read('m1-30-pageview-run.json')
    preview = read('m1-30-preview/preview-manifest.json')
    source = read('m1-30-source/source-receipt.json')
    current = read('m1-30-stage/current.json')
    candidate_raw = files.get('m1-30-source/candidate.json')
    require(candidate_raw is not None, 'missing 30-title candidate')
    candidate = decode(candidate_raw, 'candidate')
    version = digest(candidate_raw)
    prefix = f'm1-30-stage/versions/{version}/'
    require(current.get('version_sha256') == version
            and files.get(prefix + 'candidate.json') == candidate_raw
            and files.get(prefix + 'source/source-receipt.json')
            == files.get('m1-30-source/source-receipt.json'),
            'immutable stage/raw-source mismatch')
    html = files.get('m1-30-preview/index.html')
    require(html is not None and 0 < len(html) <= 1024 * 1024, 'missing or oversized HTML')
    html_sha = digest(html)
    require(files.get('index.html') == html, 'preview root mismatch')
    require(all(x.get('candidate_sha256') == version for x in (run, preview, source)),
            'candidate pin mismatch')
    require(run.get('html_sha256') == html_sha == preview.get('html_sha256'),
            'HTML pin mismatch')
    require(run.get('selected_titles') == preview.get('series') == 30
            and run.get('daily_observations') == 1050,
            'unexpected measured coverage')
    require(run.get('identity_manifest_sha256')
            == digest(files.get('m1-identity/bundle-manifest.json', b'')),
            'current identity provenance mismatch')
    require(run.get('source_commit') and len(run['source_commit']) == 40,
            'missing source commit')
    require(source.get('requests_attempted') == 30
            and source.get('observation_end') == candidate.get('observation_end')
            and source.get('retrieved_at') == candidate.get('retrieved_at')
            and source.get('seed_sha256') == digest(files.get('m1-30-source/seeds.json', b''))
            == preview.get('source_seed_sha256'), 'source/seed linkage mismatch')
    require(source.get('publication_status') == 'LOCAL_EVIDENCE_ONLY_NOT_PUBLISHED'
            and preview.get('publication_status') == 'LOCAL_PREVIEW_NOT_PUBLISHED'
            and run.get('status') == 'UNPUBLISHED_SOURCE_REVIEW_REQUIRED',
            'unreviewed publication state')
    entries = candidate.get('series')
    sources = source.get('sources')
    require(isinstance(entries, list) and isinstance(sources, list)
            and len(entries) == len(sources) == 30, 'expected 30 complete series and sources')
    start = date.fromisoformat(source['observation_start'])
    end = date.fromisoformat(source['observation_end'])
    dates = [(start + timedelta(days=i)).isoformat() for i in range(35)]
    require(dates[-1] == end.isoformat(), 'invalid 35-day observation window')
    by_key = {}
    for record in sources:
        key = (record.get('project'), record.get('page_id'))
        require(key not in by_key and record.get('http_status') == 200,
                'duplicate/failed raw source')
        name = 'm1-30-source/' + str(record.get('raw_member'))
        raw = files.get(name)
        require(raw is not None and digest(raw) == record.get('body_sha256')
                and len(raw) == record.get('response_bytes'), 'source body corruption')
        by_key[key] = (record, decode(raw, name))
    candidate_keys = [(row.get('project'), row.get('page_id')) for row in entries]
    require(all(type(key[0]) is str and type(key[1]) is int for key in candidate_keys)
            and len(set(candidate_keys)) == len(entries)
            and set(candidate_keys) == set(by_key),
            'candidate/source key mismatch')
    coverage = Counter()
    for row in entries:
        key = (row.get('project'), row.get('page_id'))
        require(key in by_key and row.get('access') == 'all-access'
                and row.get('agent') == 'user', 'candidate identity or filters unavailable')
        record, raw = by_key[key]
        daily = row.get('daily')
        items = raw.get('items')
        require(isinstance(items, list) and isinstance(daily, list)
                and len(items) == len(daily) == 35, 'missing history')
        require([v.get('date') for v in daily] == dates, 'candidate day sequence mismatch')
        for d, item in zip(daily, items):
            require(item.get('timestamp') == d['date'].replace('-', '') + '00'
                    and item.get('project') == key[0]
                    and item.get('article', '').replace('_', ' ') == row.get('title')
                    and item.get('access') == 'all-access' and item.get('agent') == 'user'
                    and item.get('granularity') == 'daily'
                    and type(item.get('views')) is int and item['views'] >= 0
                    and item['views'] == d.get('views') and d.get('value_state') == 'observed',
                    'candidate differs from retained raw day')
        require(row.get('source', {}).get('body_sha256') == record['body_sha256'],
                'source provenance differs from candidate')
        coverage[(key[0], record.get('subject'))] += 1
    require(coverage == Counter({(project, subject): 3
             for project in ('en.wikipedia', 'ru.wikipedia') for subject in SUBJECTS}),
            'edition/subject coverage mismatch')
    browser = read('m1-30-browser/receipt.json')
    require(browser.get('html_sha256') == html_sha
            and browser.get('mode') == 'LOCAL_HTTP_NOT_PUBLIC'
            and browser.get('status') == 'NOT_PUBLISHED_NOT_LIVE_VERIFIED',
            'browser evidence mismatch')
    screenshot_widths = set()
    for shot in browser.get('screenshots', []):
        width = shot.get('width')
        screenshot_widths.add(width)
        require(width == shot.get('document_width')
                and digest(files.get('m1-30-browser/' + str(shot.get('screenshot')), b''))
                == shot.get('sha256'), 'browser screenshot/width mismatch')
    require(screenshot_widths == {320, 390, 1280}, 'missing browser viewport evidence')
    return {'source_commit': run['source_commit'], 'dataset_id': candidate['dataset_id'],
            'candidate_sha256': version, 'html_sha256': html_sha,
            'observation_start': dates[0], 'observation_end': dates[-1],
            'retrieved_at': candidate['retrieved_at'], 'series': 30, 'daily_observations': 1050}


def build(source: Path, destination: Path) -> dict:
    require(not destination.exists() and not destination.is_symlink(),
            'destination already exists; never replace a preserved snapshot')
    files = read_zip(source)
    facts = verify(files)
    manifest = {**facts, 'schema_version': SCHEMA,
                'status': 'UNPUBLISHED_PRESERVED_EVIDENCE_NOT_PAGES',
                'upstream_origin': 'runtime-reported; not independently authenticated',
                'source_actions_zip_sha256': digest(source.read_bytes()),
                'files': {name: digest(value) for name, value in sorted(files.items())}}
    files['archive-manifest.json'] = canonical(manifest)
    files['README.txt'] = (
        'Dayflare | PRESERVED REAL EN/RU EVIDENCE (NOT A LIVE OR ACCEPTED RELEASE)\n'
        '30 editorial title-scoped Wikimedia page-request histories / 35 UTC days.\n'
        'Source bytes, receipts, browser screenshots and offline HTML included.\n'
        'No historical page-ID continuity or independently authenticated origin.\n'
        'Never replace the accepted 20-title gh-pages archive with this candidate.\n'
        'Verify each extracted member against archive-manifest.json and separately\n'
        'compare its SHA256 to an independently recorded acceptance fingerprint.\n'
    ).encode('utf-8')
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_DEFLATED, compresslevel=9) as z:
        for name, raw in sorted(files.items()):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, raw, compress_type=ZIP_DEFLATED, compresslevel=9)
    with destination.open('xb') as target:
        target.write(buffer.getvalue())
    return {**facts, 'archive_sha256': digest(buffer.getvalue()),
            'path': str(destination), 'status': manifest['status']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='real successful Actions artifact ZIP')
    parser.add_argument('destination', type=Path, help='new immutable offline ZIP')
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.destination), sort_keys=True))


if __name__ == '__main__':
    main()