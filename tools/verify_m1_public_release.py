"""Read-only verification of the *served* Dayflare M1 Pages archive.

Pin the manifest SHA-256 independently from a reviewed gh-pages release. A
passing check proves HTTP bytes, not deployment authorization, browser usability,
Wikimedia-origin authenticity, real-time freshness, or LIVE_VERIFIED.

Example (only after Pages has been enabled by an authorized administrator):

    python -m tools.verify_m1_public_release \
      --base-url https://drevendev.github.io/Dayflare/m1/ \
      --expected-manifest-sha256 40893016f1cdd59048c48699056695bb2e90c7430c2d1804d609f48dc32491c0 \
      --expected-dataset-id run-20261107-022343-a32c03ef7daa \
      --expected-observation-end 2026-11-04
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import re
from urllib.parse import urlsplit
from urllib.request import build_opener

from tools.verify_public_release import (
    NoRedirect, VerificationError, _fetch, hexdigest, origin,
)

SCHEMA = 'dayflare.m1.static-snapshot.v1'
METHOD = 'v0-empirical-35d'
STATUS = 'DATED_ARCHIVE_NOT_LIVE'
FIELDS = frozenset({
    'candidate_sha256', 'daily_observations', 'dataset_id', 'html_sha256',
    'method_version', 'observation_end', 'retrieved_at', 'schema_version',
    'series', 'source_receipt_sha256', 'source_seed_sha256', 'status',
})
HEX = re.compile(r'[0-9a-f]{64}\Z')
DATASET = re.compile(r'run-[0-9]{8}-[0-9]{6}-[0-9a-f]{12}\Z')


def check_manifest(raw: bytes, *, expected_dataset_id: str,
                   expected_observation_end: str) -> dict:
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise VerificationError('Invalid M1 release manifest JSON') from exc
    if type(manifest) is not dict or set(manifest) != FIELDS:
        raise VerificationError('Unexpected M1 release manifest fields')
    if (manifest['schema_version'] != SCHEMA or
            manifest['method_version'] != METHOD or
            manifest['status'] != STATUS or
            manifest['dataset_id'] != expected_dataset_id or
            manifest['observation_end'] != expected_observation_end or
            type(manifest['series']) is not int or manifest['series'] != 20 or
            type(manifest['daily_observations']) is not int or
            manifest['daily_observations'] != 700 or
            type(manifest['dataset_id']) is not str or
            not DATASET.fullmatch(manifest['dataset_id'])):
        raise VerificationError('Wrong M1 dataset, method, status or coverage')
    for field in ('html_sha256', 'candidate_sha256', 'source_receipt_sha256',
                  'source_seed_sha256'):
        if type(manifest[field]) is not str or not HEX.fullmatch(manifest[field]):
            raise VerificationError(f'Invalid {field}')
    try:
        end = date.fromisoformat(manifest['observation_end'])
        if end.isoformat() != manifest['observation_end']:
            raise ValueError('noncanonical date')
        retrieved = datetime.strptime(manifest['retrieved_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        if retrieved.strftime('%Y-%m-%dT%H:%M:%SZ') != manifest['retrieved_at']:
            raise ValueError('noncanonical retrieval time')
    except (TypeError, ValueError) as exc:
        raise VerificationError('Invalid M1 observation/retrieval timestamp') from exc
    if retrieved.date() < end + timedelta(days=1):
        raise VerificationError('M1 retrieval predates complete observation window')
    return manifest


def verify(base_url: str, expected_manifest_sha256: str,
           expected_dataset_id: str, expected_observation_end: str,
           *, allow_loopback_http: bool = False) -> dict:
    https = origin(base_url, allow_loopback_http=allow_loopback_http)
    parsed = urlsplit(base_url)
    if (parsed.path != '/Dayflare/m1/' or
            (https and (parsed.hostname != 'drevendev.github.io' or parsed.port is not None))):
        raise VerificationError('Only the exact Dayflare /m1/ route is accepted')
    if type(expected_manifest_sha256) is not str or not HEX.fullmatch(expected_manifest_sha256):
        raise VerificationError('Independently accepted lowercase manifest SHA-256 required')
    if type(expected_dataset_id) is not str or not DATASET.fullmatch(expected_dataset_id):
        raise VerificationError('Expected dataset ID required')
    try:
        end = date.fromisoformat(expected_observation_end)
        if end.isoformat() != expected_observation_end:
            raise ValueError('noncanonical date')
    except (TypeError, ValueError) as exc:
        raise VerificationError('Expected canonical UTC observation end required') from exc
    opener = build_opener(NoRedirect())
    raw = _fetch(opener, base_url + 'release-manifest.json', 'release-manifest.json', 128 * 1024)
    if hexdigest(raw) != expected_manifest_sha256:
        raise VerificationError('Served M1 manifest differs from independent release pin')
    manifest = check_manifest(raw, expected_dataset_id=expected_dataset_id,
                              expected_observation_end=expected_observation_end)
    body = _fetch(opener, base_url + 'index.html', 'index.html', 1024 * 1024)
    if hexdigest(body) != manifest['html_sha256']:
        raise VerificationError('Served M1 HTML differs from pinned release manifest')
    landing = _fetch(opener, base_url, 'index.html', 1024 * 1024)
    if landing != body:
        raise VerificationError('Visitor M1 root differs from verified M1 index.html')
    return {'url': base_url, 'dataset_id': manifest['dataset_id'],
            'method_version': manifest['method_version'],
            'observation_end': manifest['observation_end'],
            'retrieved_at': manifest['retrieved_at'],
            'series': manifest['series'], 'daily_observations': manifest['daily_observations'],
            'manifest_sha256': expected_manifest_sha256,
            'html_sha256': manifest['html_sha256'],
            'transport': 'https' if https else 'local-loopback-http',
            'status': 'HTTP_BYTES_VERIFIED_NOT_BROWSER_VERIFIED'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    parser.add_argument('--expected-dataset-id', required=True)
    parser.add_argument('--expected-observation-end', required=True)
    parser.add_argument('--allow-loopback-http', action='store_true',
                        help='Tests only: numeric loopback, never public LIVE_VERIFIED')
    args = parser.parse_args()
    try:
        result = verify(args.base_url, args.expected_manifest_sha256,
                        args.expected_dataset_id, args.expected_observation_end,
                        allow_loopback_http=args.allow_loopback_http)
    except VerificationError as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    print(json.dumps(result, sort_keys=True))
    print('NOTE: HTTP byte equality is not deployment authorization, browser acceptance, source authenticity or LIVE_VERIFIED.')


if __name__ == '__main__':
    main()
