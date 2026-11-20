"""Rebuild/verify a dated, portable PARTIAL 30-title atlas from Git-retained bytes.

No network, Pages, trust enrollment or replacement of the accepted 20-title release.
The archive includes exact decoded HTTP bodies and the source receipt, NOT the
original wire payloads, identity/seed stage or CI/browser artifacts.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from hashlib import sha256
import hmac
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import stat
from zipfile import BadZipFile, ZipFile, ZipInfo, ZIP_STORED

from tools.m1_30_reader import render
from tools.m1_30_retained_candidate import (
    CANDIDATE_SHA256, DATASET_ID, OBS_END, OBS_START, read_candidate,
)
from tools.m1_30_raw_archive import (
    RECEIPT_ARMOR, RECEIPT_ARMOR_SIZE, RECEIPT_JSON_SHA256, RECEIPT_JSON_SIZE,
    RECEIPT_XZ_SHA256, decode_json, read_pinned_xz, read_raw_archive,
)

SCHEMA = 'dayflare.m1-30.git-retained-portable.v1'
STATUS = 'UNPUBLISHED_PARTIAL_EVIDENCE_NOT_PAGES'
README = (
    'Dayflare — UNPUBLISHED / PARTIAL EVIDENCE / NOT A LIVE SITE\n'
    '30 editor-selected title-scoped EN/RU Wikipedia histories; 35 UTC days.\n'
    'Open index.html offline for search, detail, A/B comparison and exact CSV.\n'
    'Included: pinned normalized candidate, exact decoded HTTP bodies, source receipt.\n'
    'NOT included: wire gzip, identity/seed/staging files, Chromium screenshots.\n'
    'Upstream HTTP provenance is runtime-reported, not independently authenticated.\n'
    'Title histories do not prove uninterrupted historical page-ID continuity.\n'
    'agent=user does NOT mean unique human visitors; selection is not representative.\n'
    'This is NOT the accepted 20-title release and is NOT a Pages deployment.\n'
    'Verify this ZIP with an independently reviewed SHA-256 before opening.\n'
).encode('utf-8')
MAX_ZIP = 2 * 1024 * 1024
HEX = re.compile(r'[0-9a-f]{64}\Z')


class BundleError(ValueError):
    """Invalid, changed, oversized or incorrectly described offline evidence."""


def need(ok: bool, why: str) -> None:
    if not ok:
        raise BundleError(why)


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def facts(candidate: dict) -> dict:
    return {
        'schema_version': SCHEMA,
        'status': STATUS,
        'dataset_id': DATASET_ID,
        'method_version': 'v0-empirical-35d',
        'observation_start': str(OBS_START),
        'observation_end': str(OBS_END),
        'retrieved_at': '2026-11-17T08:30:55Z',
        'selected_histories': 30,
        'daily_observations': 1050,
        'source_scope': 'decoded_HTTP_bodies_and_receipt_only',
        'provenance': 'runtime_reported_not_independently_authenticated',
    }


def members_from_retained() -> dict[str, bytes]:
    candidate_raw, candidate = read_candidate()  # Exact independent input pin.
    bodies = read_raw_archive(candidate)           # Full 35-day raw-count validation.
    receipt = read_pinned_xz(RECEIPT_ARMOR, RECEIPT_ARMOR_SIZE,
                             RECEIPT_XZ_SHA256, RECEIPT_JSON_SIZE,
                             RECEIPT_JSON_SHA256)
    files = {
        'index.html': render(candidate),
        'source/candidate.json': candidate_raw,
        'source/source-receipt.json': receipt,
        'README.txt': README,
    }
    files.update({'source/raw/' + name: raw for name, raw in bodies.items()})
    manifest = {
        **facts(candidate),
        'members': {name: {'bytes': len(raw), 'sha256': digest(raw)}
                    for name, raw in sorted(files.items())},
    }
    files['manifest.json'] = canonical(manifest)
    return files


def encode_zip(files: dict[str, bytes]) -> bytes:
    """Use STORE and fixed metadata for cross-runtime byte-for-byte determinism."""
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_STORED, allowZip64=False) as archive:
        for name in sorted(files):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = ZIP_STORED
            archive.writestr(info, files[name])
    need(len(output.getvalue()) <= MAX_ZIP, 'bundle exceeds bounded size')
    return output.getvalue()


def read_members(path: Path) -> dict[str, bytes]:
    need(path.is_file() and not path.is_symlink()
         and path.stat().st_size <= MAX_ZIP, 'missing, linked or oversized ZIP')
    result: dict[str, bytes] = {}
    inflated = 0
    try:
        with ZipFile(path, 'r') as archive:
            entries = archive.infolist()
            need(5 <= len(entries) <= 40, 'invalid member count')
            for info in entries:
                name = info.filename
                pure = PurePosixPath(name)
                mode = info.external_attr >> 16
                need(name and name not in result and '\\' not in name
                     and not name.startswith('/') and str(pure) == name
                     and all(part not in ('', '.', '..') for part in pure.parts)
                     and not info.is_dir() and not stat.S_ISLNK(mode)
                     and info.compress_type == ZIP_STORED and not (info.flag_bits & 1)
                     and 0 <= info.file_size <= 512_000,
                     'unsafe, duplicate, encrypted or oversized archive member')
                inflated += info.file_size
                need(inflated <= MAX_ZIP, 'expanded archive budget exceeded')
                result[name] = archive.read(info)
    except (OSError, BadZipFile, RuntimeError, EOFError) as exc:
        raise BundleError('invalid ZIP bytes') from exc
    return result


def verify(source: Path, expected_sha256: str, html_out: Path | None = None) -> dict:
    """Pin ZIP externally; verify all source and presentation bytes before any write."""
    need(type(expected_sha256) is str and HEX.fullmatch(expected_sha256) is not None,
         'independent lowercase SHA-256 required')
    need(source.is_file() and not source.is_symlink()
         and source.stat().st_size <= MAX_ZIP, 'missing, linked or oversized ZIP')
    raw_zip = source.read_bytes()
    need(hmac.compare_digest(digest(raw_zip), expected_sha256),
         'ZIP does not match independent SHA-256')
    files = read_members(source)
    need(hmac.compare_digest(digest(source.read_bytes()), expected_sha256),
         'ZIP changed during verification')
    need('source/candidate.json' in files and 'manifest.json' in files,
         'missing candidate or manifest')
    candidate_raw = files['source/candidate.json']
    need(hmac.compare_digest(digest(candidate_raw), CANDIDATE_SHA256),
         'normalized candidate differs from independently pinned bytes')
    candidate = decode_json(candidate_raw)
    rows = candidate.get('series')
    need(type(rows) is list and len(rows) == 30
         and candidate.get('dataset_id') == DATASET_ID
         and candidate.get('method_version') == 'v0-empirical-35d'
         and candidate.get('observation_end') == str(OBS_END)
         and candidate.get('retrieved_at') == '2026-11-17T08:30:55Z',
         'wrong dataset or observation window')
    identities = [(r['project'], r['page_id']) for r in rows]
    need(len(set(identities)) == 30
         and sum(project == 'en.wikipedia' for project, _ in identities) == 15
         and sum(project == 'ru.wikipedia' for project, _ in identities) == 15,
         'missing, duplicate or incomparable series identity')
    expected_files = {'README.txt', 'manifest.json', 'index.html',
                      'source/candidate.json', 'source/source-receipt.json'}
    expected_files.update('source/raw/' + f'{project}.{page_id}.json'
                          for project, page_id in identities)
    need(set(files) == expected_files, 'missing or unrecognized archive member')
    need(files['README.txt'] == README, 'missing PARTIAL/UNPUBLISHED disclaimer')
    need(hmac.compare_digest(digest(files['source/source-receipt.json']),
                             RECEIPT_JSON_SHA256), 'changed original source receipt')
    manifest = decode_json(files['manifest.json'])
    need({key: manifest.get(key) for key in facts(candidate)} == facts(candidate),
         'manifest dataset/method/status mismatch')
    expected_manifest_files = {
        name: {'bytes': len(content), 'sha256': digest(content)}
        for name, content in files.items() if name != 'manifest.json'
    }
    need(manifest.get('members') == expected_manifest_files,
         'manifest does not bind all members by size/SHA-256')
    receipt = decode_json(files['source/source-receipt.json'])
    sources = receipt.get('sources')
    need(type(sources) is list and len(sources) == 30
         and receipt.get('candidate_sha256') == CANDIDATE_SHA256
         and receipt.get('requests_attempted') == 30
         and receipt.get('publication_status') == 'LOCAL_EVIDENCE_ONLY_NOT_PUBLISHED',
         'source receipt coverage/identity mismatch')
    by_identity = {(s['project'], s['page_id']): s for s in sources}
    need(len(by_identity) == 30 and set(by_identity) == set(identities),
         'source receipt identity mismatch')
    dates = [(OBS_START + timedelta(days=i)).isoformat() for i in range(35)]
    need(dates[-1] == str(OBS_END), 'wrong 35-day window')
    for row in rows:
        identity = (row['project'], row['page_id'])
        name = f'{identity[0]}.{identity[1]}.json'
        body = files['source/raw/' + name]
        record = by_identity[identity]
        need(record.get('raw_member') == 'raw/' + name
             and record.get('http_status') == 200
             and record.get('body_sha256') == digest(body)
             and row['source']['body_sha256'] == digest(body)
             and record.get('response_bytes') == len(body),
             'raw body/receipt pin mismatch')
        daily = row.get('daily')
        items = decode_json(body).get('items')
        need(type(daily) is list and type(items) is list
             and len(daily) == len(items) == 35
             and [d.get('date') for d in daily] == dates,
             'missing or incomparable daily history')
        for i, (point, item) in enumerate(zip(daily, items)):
            need(item.get('timestamp') == dates[i].replace('-', '') + '00'
                 and item.get('project') == identity[0]
                 and item.get('article', '').replace('_', ' ') == row['title']
                 and item.get('access') == 'all-access' and item.get('agent') == 'user'
                 and item.get('granularity') == 'daily'
                 and type(point.get('views')) is int and point['views'] >= 0
                 and type(item.get('views')) is int
                 and item['views'] == point['views'],
                 'source count/filter/date mismatch')
    need(files['index.html'] == render(candidate),
         'HTML does not represent pinned source and current reader')
    if html_out is not None:
        need(html_out.parent.is_dir() and not html_out.parent.is_symlink()
             and not html_out.exists() and not html_out.is_symlink(),
             'HTML destination must be new and parent must exist')
        with html_out.open('xb') as handle:
            handle.write(files['index.html'])
    return {**facts(candidate), 'zip_sha256': expected_sha256,
            'html_sha256': digest(files['index.html']),
            'html_path': str(html_out) if html_out else None}


def build(destination: Path) -> dict:
    need(destination.parent.is_dir() and not destination.parent.is_symlink()
         and not destination.exists() and not destination.is_symlink(),
         'ZIP destination must be new and parent must exist')
    files = members_from_retained()
    archive = encode_zip(files)
    with destination.open('xb') as handle:
        handle.write(archive)
    return verify(destination, digest(archive))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--output', type=Path, help='new deterministic partial ZIP')
    operation.add_argument('--verify', type=Path, help='existing ZIP to check')
    parser.add_argument('--expected-sha256', help='independently reviewed ZIP SHA-256')
    parser.add_argument('--html-out', type=Path, help='new HTML path after verification')
    args = parser.parse_args()
    if args.output:
        need(args.expected_sha256 is None and args.html_out is None,
             '--output cannot use consumer verification/extraction flags')
        result = build(args.output)
    else:
        need(args.expected_sha256 is not None, '--verify requires independent pin')
        result = verify(args.verify, args.expected_sha256, args.html_out)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
