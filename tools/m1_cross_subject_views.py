"""Read-only, bounded historical page-request evidence for culture and games.

These are TITLE-scoped Wikimedia series, not histories of observed page IDs.
No data is staged to Pages or used to replace the accepted M0 capsule here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from tools.d01_probe import BASE, USER_AGENT, analyze_items, expected_dates, iso_now
from tools.d02_probe import read_bounded_body, weekly_metrics, MAX_RESPONSE_BYTES

START = '20260811'
END = '20260914'
SCHEMA = 'dayflare.m1-cross-subject-title-views.v1'
METHOD = 'v0-empirical-35d'
REQUESTS = (
    {'project': 'en.wikipedia.org', 'article': 'Cinema', 'subject': 'culture'},
    {'project': 'ru.wikipedia.org', 'article': 'Кинематограф', 'subject': 'culture'},
    {'project': 'en.wikipedia.org', 'article': 'Video_game', 'subject': 'games'},
    {'project': 'ru.wikipedia.org', 'article': 'Компьютерная_игра', 'subject': 'games'},
)
MIN_SPACING = 2.0
SLOW_THRESHOLD = 1.0
SLOW_PAUSE = 5.0
TIMEOUT = 20
MAX_AGGREGATE = 4 * MAX_RESPONSE_BYTES


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def collect(output: Path, *, opener=urlopen, pause=time.sleep, clock=time.monotonic) -> int:
    """Collect four series without retries; retain failure receipts and never overwrite."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    expected = expected_dates(START, END)
    assert len(expected) == 35
    started = iso_now()
    receipts, sample = [], []
    previous_elapsed = None
    total_bytes = 0
    for index, spec in enumerate(REQUESTS):
        if previous_elapsed is not None:
            pause(SLOW_PAUSE if previous_elapsed > SLOW_THRESHOLD else MIN_SPACING)
        endpoint = f'{BASE}/{spec["project"]}/all-access/user/{quote(spec["article"], safe="")}/daily/{START}/{END}'
        started_request = iso_now()
        t0 = clock()
        status, raw, complete, error = None, b'', False, None
        try:
            request = Request(endpoint, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
            with opener(request, timeout=TIMEOUT) as response:
                status = int(response.status)
                raw, truncated = read_bounded_body(response)
                complete = not truncated
                if truncated:
                    error = 'ResponseTooLarge'
        except HTTPError as exc:
            status = int(exc.code)
            error = f'HTTP {status}'
            exc.close()
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        previous_elapsed = max(0.0, clock() - t0)
        total_bytes += len(raw)
        if total_bytes > MAX_AGGREGATE:
            error = 'AggregateBudgetExceeded'
        payload_items = []
        if status == 200 and complete and not error:
            try:
                parsed = json.loads(raw.decode('utf-8'))
                if not isinstance(parsed, dict) or not isinstance(parsed.get('items'), list):
                    raise ValueError('expected an object containing items list')
                payload_items = parsed['items']
            except (UnicodeDecodeError, ValueError, TypeError) as exc:
                error = f'InvalidJSON: {exc}'
        result = analyze_items(payload_items, spec, expected) if status == 200 and not error else None
        normalized = result['normalized_items'] if result else []
        metrics = None
        if result and result['semantic_valid'] and result['normalized_complete']:
            try:
                metrics = weekly_metrics(normalized)
            except ValueError as exc:
                error = f'InvalidMetrics: {exc}'
        valid = bool(status == 200 and complete and not error and result and result['semantic_valid']
                     and result['normalized_complete'] and metrics is not None)
        # Full accepted HTTP 200 bodies permit subsequent independent re-validation;
        # never publish these objects directly as a site's refreshed data.
        raw_path = None
        if status == 200 and complete and raw and total_bytes <= MAX_AGGREGATE:
            raw_path = f'source-{index:02d}.json'
            (output / raw_path).write_bytes(raw)
        receipts.append({
            'requested': spec, 'endpoint': endpoint,
            'filters': {'access': 'all-access', 'agent': 'user', 'granularity': 'daily'},
            'started_at': started_request, 'retrieved_at': iso_now(),
            'http_status': status, 'source_bytes': len(raw) if complete else None,
            'source_sha256': sha(raw) if complete and raw else None,
            'source_file': raw_path, 'semantic_errors': result['semantic_errors'] if result else [],
            'observed_days': len(normalized) if valid else None,
            'documented_zero_days': result['omitted_zero_days'] if valid else None,
            'valid': valid, 'error': error,
        })
        sample.append({'request': spec, 'items': normalized if valid else None, 'metrics': metrics if valid else None})
    success = len(receipts) == 4 and all(r['valid'] for r in receipts)
    sample_bytes = canonical(sample)
    (output / 'sample.json').write_bytes(sample_bytes + b'\n')
    manifest = {
        'schema': SCHEMA, 'method': METHOD,
        'status': 'UNPUBLISHED_REVIEW_REQUIRED' if success else 'INVALID_UNPUBLISHED',
        'success': success, 'started_at': started, 'finished_at': iso_now(),
        'observation_window': {'start': START, 'end': END, 'expected_days': 35},
        'selection': 'Four editor-selected title-scoped histories for culture and games; NOT a representative sample.',
        'limits': 'Request counts, not unique users or causes; title URLs do not prove historical page-ID continuity or Wikidata equivalence.',
        'request_count': len(REQUESTS), 'sample_sha256': sha(sample_bytes), 'receipts': receipts,
    }
    (output / 'receipt.json').write_bytes(canonical(manifest) + b'\n')
    print(json.dumps({'status': manifest['status'], 'coverage': sum(r['valid'] for r in receipts),
                      'requested': len(REQUESTS), 'sample_sha256': manifest['sample_sha256']}))
    return 0 if success else 2


def main() -> int:
    return collect(Path('artifacts/m1_cross_subject_views'))


if __name__ == '__main__':
    raise SystemExit(main())
