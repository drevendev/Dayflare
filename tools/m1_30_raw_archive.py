"""Verify/restore 30 exact raw Pageviews bodies from the retained 2026-11-17 run.

No network or publication. Original Actions receipt, transport and browser evidence
remain in the expiring full ZIP; this capsule preserves raw decoded HTTP bodies only.
"""
from __future__ import annotations

import argparse
import base64
from datetime import date, timedelta
from hashlib import sha256
import hmac
import json
import lzma
from pathlib import Path
import re

from tools.m1_30_retained_candidate import read_candidate

ARMOR = Path(__file__).resolve().parents[1] / 'evidence/m1-30-20261117-raw-pages.xz.b64'
ARMOR_SIZE = 7681
XZ_SHA256 = 'dcdb125bc3b3d4c65e9e8715a7377e870e3b1bd6dc460c04825c704514f37fd0'
JSON_SHA256 = '9cbed114a098d15ba3e53d9127506b8596954fce2e752de8eab5ee814d7c957d'
JSON_SIZE = 188116
EXACT_B64 = re.compile(r'[A-Za-z0-9+/]+={0,2}\Z')


class RawArchiveError(ValueError):
    pass


def need(value: bool, detail: str) -> None:
    if not value:
        raise RawArchiveError(detail)


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def decode_json(raw: bytes) -> dict:
    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                            parse_constant=lambda _: need(False, 'nonfinite JSON'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RawArchiveError('invalid UTF-8/JSON') from exc
    need(type(result) is dict, 'expected JSON object')
    return result


def read_raw_archive(candidate: dict, path: Path = ARMOR) -> dict[str, bytes]:
    need(path.is_file() and not path.is_symlink()
         and path.stat().st_size == ARMOR_SIZE, 'missing, linked or wrong-sized raw armor')
    try:
        text = path.read_text(encoding='ascii')
        need(text.endswith('\n') and EXACT_B64.fullmatch(text[:-1]) is not None,
             'noncanonical raw armor')
        compressed = base64.b64decode(text[:-1], validate=True)
        need(base64.b64encode(compressed).decode('ascii') == text[:-1]
             and hmac.compare_digest(sha256(compressed).hexdigest(), XZ_SHA256),
             'wrong compressed source archive')
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=128 * 1024 * 1024)
        raw = decoder.decompress(compressed, max_length=JSON_SIZE + 1)
        need(decoder.eof and not decoder.unused_data and len(raw) == JSON_SIZE
             and hmac.compare_digest(sha256(raw).hexdigest(), JSON_SHA256),
             'truncated, extra or changed raw source archive')
    except (UnicodeError, OSError, ValueError, EOFError, lzma.LZMAError) as exc:
        if isinstance(exc, RawArchiveError):
            raise
        raise RawArchiveError('cannot decode raw source archive') from exc
    records = decode_json(raw)
    series = candidate['series']
    expected = {f"{row['project']}.{row['page_id']}.json": row for row in series}
    need(len(series) == len(expected) == len(records) == 30
         and set(expected) == set(records), 'raw source identity/coverage mismatch')
    start = date.fromisoformat('2026-10-11')
    days = [(start + timedelta(days=i)).strftime('%Y%m%d00') for i in range(35)]
    result = {}
    for name, row in expected.items():
        original = records[name]
        need(type(original) is str, 'raw source is not a string')
        body = original.encode('utf-8')
        pin = row['source']
        need(len(body) == pin['response_bytes']
             and hmac.compare_digest(sha256(body).hexdigest(), pin['body_sha256']),
             'raw source exact-byte mismatch')
        doc = decode_json(body)
        items = doc.get('items')
        need(type(items) is list and len(items) == 35, 'incomplete Pageviews history')
        for i, (item, point) in enumerate(zip(items, row['daily'])):
            need(type(item) is dict and item.get('project') == row['project']
                 and item.get('article', '').replace('_', ' ') == row['title']
                 and item.get('access') == 'all-access' and item.get('agent') == 'user'
                 and item.get('granularity') == 'daily' and item.get('timestamp') == days[i]
                 and type(item.get('views')) is int and item['views'] >= 0
                 and item['views'] == point['views'], 'Pageviews filter/date/count mismatch')
        result[name] = body
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new directory for 30 original JSON bodies')
    args = parser.parse_args()
    _, candidate = read_candidate()
    files = read_raw_archive(candidate)
    if args.output:
        need(args.output.parent.is_dir() and not args.output.parent.is_symlink()
             and not args.output.exists() and not args.output.is_symlink(),
             'destination must be new and parent must exist')
        args.output.mkdir()
        for filename, body in sorted(files.items()):
            with (args.output / filename).open('xb') as handle:
                handle.write(body)
    print(json.dumps({'status': 'RAW_DECODED_HTTP_BODIES_PRESERVED_NOT_PUBLISHED',
                      'dataset_id': candidate['dataset_id'], 'source_bodies': len(files),
                      'daily_observations': 1050, 'raw_archive_sha256': JSON_SHA256,
                      'restored_to': str(args.output) if args.output else None}, sort_keys=True))


if __name__ == '__main__':
    main()
