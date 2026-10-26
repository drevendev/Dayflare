"""Verify the exact HTTP bytes of a reviewed Dayflare static release.

This is a read-only publication check, NOT a deployment step or proof of
browser usability. Pin the approved manifest SHA-256 from the accepted build;
without that independent pin, a self-consistent wrong/stale release passes.

Usage (after authorized deployment):
    python -m tools.verify_public_release \
      --base-url https://drevendev.github.io/Dayflare/ \
      --expected-manifest-sha256 <64-hex-sha256>

For local HTTP-only regression tests, --allow-loopback-http is accepted with a
numeric loopback host; those results must never be labeled LIVE_VERIFIED.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from tools.m1_cross_subject_static import validate_assets
from tools.m1_curated_static import validate_assets as validate_curated_assets

MAX_MANIFEST_BYTES = 128 * 1024
MAX_ASSET_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
EXPECTED_DATASET = 'd02-20261018-084126'
EXPECTED_METHOD = 'v0-empirical-35d'
EXPECTED_WINDOW = ['2026-08-11', '2026-09-14']
REQUIRED_ASSETS = {
    'index.html', 'app.js', 'styles.css', 'evidence.html',
    'evidence/d02-20261018/source.zip',
    'evidence/d02-20261018/provenance.json',
    'evidence/d02-20261018/README.md', '.nojekyll',
    'identities-m1-20261024.html', 'identities-m1-20261024.json',
    'identity-explorer.js',
    'm1-cross-subject-20261025.html', 'm1-cross-subject-20261025.json',
    'm1-curated-20261023.html', 'm1-curated-20261023.json',
}
VISITOR_ASSETS = REQUIRED_ASSETS - {'.nojekyll'}
MIME = {
    '.html': {'text/html'},
    '.js': {'text/javascript', 'application/javascript', 'application/x-javascript'},
    '.css': {'text/css'},
    '.json': {'application/json', 'text/json'},
    '.zip': {'application/zip', 'application/x-zip-compressed', 'application/octet-stream'},
    '.md': {'text/plain', 'text/markdown', 'text/x-markdown', 'application/octet-stream'},
}


class VerificationError(ValueError):
    """A served byte, type or version is inconsistent with the pinned release."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise VerificationError(f'Redirect not accepted at {req.full_url}: HTTP {code}')


def hexdigest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def origin(base_url: str, *, allow_loopback_http: bool = False) -> bool:
    """Validate an explicit static site root. Returns True for HTTPS."""
    p = urlsplit(base_url)
    if p.username or p.password or p.query or p.fragment or not p.hostname:
        raise VerificationError('Base URL must have a host, no credentials/query/fragment')
    if not p.path.endswith('/') or '\\' in p.path or any(
        v in ('.', '..') for v in unquote(p.path).split('/')
    ):
        raise VerificationError('Base URL must point to a clean trailing-slash directory')
    if p.scheme == 'https':
        return True
    if p.scheme == 'http' and allow_loopback_http:
        try:
            if ipaddress.ip_address(p.hostname).is_loopback:
                return False
        except ValueError:
            pass
    raise VerificationError('HTTPS required (except explicit numeric loopback testing)')


def _path(name: str) -> None:
    if (not isinstance(name, str) or len(name) > 180 or not name or name.startswith('/')
            or '\\' in name or '%' in name or '?' in name or '#' in name
            or any(p in ('', '.', '..') for p in name.split('/'))):
        raise VerificationError(f'Unsafe release path: {name!r}')


def _type(name: str, header: str) -> None:
    ext = '.' + name.rsplit('.', 1)[-1]
    mime = header.split(';', 1)[0].strip().lower()
    if ext not in MIME or mime not in MIME[ext]:
        raise VerificationError(f'Incorrect Content-Type for {name}: {header!r}')
    if name.endswith(('.html','.js','.css','.json','.md')) and 'charset=' in header.lower():
        charset = header.lower().split('charset=', 1)[1].strip().split(';', 1)[0].strip('"')
        if charset not in ('utf-8', 'utf8'):
            raise VerificationError(f'Unsupported charset for {name}: {charset}')


def _fetch(opener, url: str, name: str, max_bytes: int) -> bytes:
    request = Request(url, headers={'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache',
                                    'User-Agent': 'Dayflare-static-release-check/1.0'})
    try:
        with opener.open(request, timeout=12) as response:
            code = response.status
            if code != 200:
                raise VerificationError(f'{name}: HTTP {code} (expected 200)')
            content_encoding = response.headers.get('Content-Encoding', 'identity').lower().strip()
            if content_encoding not in ('identity', ''):
                raise VerificationError(f'{name}: encoded response {content_encoding!r}; request identity bytes')
            declared = response.headers.get('Content-Length')
            if declared:
                try:
                    length = int(declared)
                except ValueError as exc:
                    raise VerificationError(f'{name}: invalid Content-Length') from exc
                if length > max_bytes or length < 0:
                    raise VerificationError(f'{name}: invalid declared asset size {length}')
            _type(name, response.headers.get('Content-Type', ''))
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise VerificationError(f'{name}: HTTP asset exceeds {max_bytes} bytes')
            if declared and len(body) != int(declared):
                raise VerificationError(f'{name}: incomplete HTTP body')
            return body
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError(f'{name}: HTTP request failed: {type(exc).__name__}: {exc}') from exc


@dataclass(frozen=True)
class Verification:
    url: str
    manifest_sha256: str
    dataset_id: str
    method_version: str
    verified_assets: int
    total_bytes: int
    transport: str
    status: str = 'HTTP_BYTES_VERIFIED_NOT_BROWSER_VERIFIED'


def verify(base_url: str, expected_manifest_sha256: str, *, allow_loopback_http: bool = False) -> Verification:
    https = origin(base_url, allow_loopback_http=allow_loopback_http)
    if not isinstance(expected_manifest_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_manifest_sha256):
        raise VerificationError('A lowercase SHA-256 of the accepted manifest is required')
    opener = build_opener(NoRedirect())
    raw = _fetch(opener, base_url + 'release-manifest.json', 'release-manifest.json', MAX_MANIFEST_BYTES)
    if hexdigest(raw) != expected_manifest_sha256:
        raise VerificationError('Served manifest differs from independently accepted release SHA-256')
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise VerificationError('Invalid release manifest JSON') from exc
    if not isinstance(manifest, dict) or manifest.get('dataset_id') != EXPECTED_DATASET or manifest.get('method_version') != EXPECTED_METHOD or manifest.get('observation_window_utc') != EXPECTED_WINDOW:
        raise VerificationError('Wrong dataset, method or observation window')
    assets = manifest.get('files_sha256')
    if not isinstance(assets, dict) or set(assets) != REQUIRED_ASSETS:
        raise VerificationError('Manifest must enumerate the expected M0 files')
    identity=manifest.get('auxiliary_identity_dataset')
    if (not isinstance(identity,dict)
            or identity.get('dataset_id')!='m1-20261024-enru-curated-20'
            or identity.get('observation_date_utc')!='2026-10-24'
            or type(identity.get('observed_ids')) is not int
            or identity['observed_ids']!=20
            or identity.get('pageviews')!='not_collected'
            or identity.get('origin_authenticated') is not False):
        raise VerificationError('Missing or unsupported observed identity dataset receipt')
    companion = manifest.get('auxiliary_cross_subject_dataset')
    if (not isinstance(companion, dict)
            or companion.get('dataset_id') != 'm1-cross-subject-title-20261025'
            or companion.get('title_series') != 4
            or companion.get('daily_observations') != 140
            or companion.get('observation_window_utc') != EXPECTED_WINDOW
            or companion.get('retrieved_utc') != '2026-10-25'
            or companion.get('source_sample_sha256') != 'f159d102eca3e0406a785abde487754ac6cf35e1852cfc5de4235774c25168ba'
            or companion.get('historical_page_id_continuity') != 'not_verified'
            or companion.get('raw_http_bodies_in_release') is not False):
        raise VerificationError('Missing or unsupported cross-subject historical receipt')
    curated_receipt=manifest.get('auxiliary_curated_title_dataset')
    if (not isinstance(curated_receipt, dict)
            or curated_receipt.get('dataset_id') != 'm1-curated-20261023-d96477427ece'
            or curated_receipt.get('measured_series') != 20
            or curated_receipt.get('daily_observations') != 700
            or curated_receipt.get('source_candidate_sha256') != 'd96477427ece441302b11485f56a79703f77615b4a2b8cc98b4afaec078fc091'
            or curated_receipt.get('title_scoped') is not True
            or curated_receipt.get('historical_page_id_continuity') is not False):
        raise VerificationError('Missing or unsupported 20-series title history receipt')
    if manifest.get('input_archive_sha256') != assets['evidence/d02-20261018/source.zip']:
        raise VerificationError('Manifest source archive disagrees with served archive pin')
    total = len(raw)
    cross_assets = {}
    curated_assets = {}
    for name in sorted(assets):
        _path(name)
        expected = assets[name]
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise VerificationError(f'Missing or invalid SHA-256 for {name}')
        if name == '.nojekyll':
            # Pages treats this as a publication directive, not a visitor-facing
            # asset. Some hosts do not serve dotfiles at all.
            if expected != hexdigest(b''):
                raise VerificationError('Unexpected .nojekyll publication directive')
            continue
        path_url = base_url + quote(name, safe='/')
        raw_asset = _fetch(opener, path_url, name, MAX_ASSET_BYTES)
        total += len(raw_asset)
        if total > MAX_TOTAL_BYTES:
            raise VerificationError('Aggregate release response size exceeds budget')
        if hexdigest(raw_asset) != expected:
            raise VerificationError(f'{name}: served bytes differ from accepted manifest')
        if name in ('m1-cross-subject-20261025.json', 'm1-cross-subject-20261025.html'):
            cross_assets[name] = raw_asset
        if name in ('m1-curated-20261023.json', 'm1-curated-20261023.html',
                    'identities-m1-20261024.json'):
            curated_assets[name] = raw_asset
    # A self-consistent release manifest must not be sufficient to bless an
    # internally invalid title-history page, even with an external hash pin.
    try:
        actual = validate_assets(
            cross_assets['m1-cross-subject-20261025.json'],
            cross_assets['m1-cross-subject-20261025.html'])
    except (ValueError, KeyError, UnicodeDecodeError, TypeError) as exc:
        raise VerificationError(f'Invalid served cross-subject historical evidence: {exc}') from exc
    if actual != companion:
        raise VerificationError('Served cross-subject evidence differs from release receipt')
    try:
        curated_actual = validate_curated_assets(
            curated_assets['m1-curated-20261023.json'],
            curated_assets['m1-curated-20261023.html'],
            curated_assets['identities-m1-20261024.json'])
    except (ValueError, KeyError, UnicodeDecodeError, TypeError) as exc:
        raise VerificationError(f'Invalid served 20-series historical evidence: {exc}') from exc
    if curated_actual != curated_receipt:
        raise VerificationError('Served 20-series evidence differs from release receipt')
    # A Pages project root is the visitor's entry point, not /index.html.
    # A stale index at "/" must not be accepted merely because the explicitly
    # addressed /index.html and other assets happen to match the manifest.
    landing = _fetch(opener, base_url, 'index.html', MAX_ASSET_BYTES)
    if hexdigest(landing) != assets['index.html']:
        raise VerificationError('Visitor root HTML differs from accepted index.html')
    total += len(landing)
    if total > MAX_TOTAL_BYTES:
        raise VerificationError('Aggregate release response size exceeds budget')
    return Verification(base_url, expected_manifest_sha256, EXPECTED_DATASET, EXPECTED_METHOD,
                        len(VISITOR_ASSETS), total, 'https' if https else 'local-loopback-http')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    parser.add_argument('--allow-loopback-http', action='store_true',
                        help='Testing ONLY: local numeric loopback, never public live verification')
    args = parser.parse_args()
    try:
        result = verify(args.base_url, args.expected_manifest_sha256,
                        allow_loopback_http=args.allow_loopback_http)
    except VerificationError as error:
        parser.exit(1, f'FAIL: {error}\n')
    print(json.dumps(result.__dict__, sort_keys=True))
    print('NOTE: HTTP bytes alone do not establish LIVE_VERIFIED; real browser and authorized Pages deployment remain separate.')


if __name__ == '__main__':
    main()
