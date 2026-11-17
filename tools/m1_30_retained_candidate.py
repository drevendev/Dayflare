"""Read the exact retained 30-title candidate; not a Pages release or raw API archive.

The committed armor is an immutable, independently pinned, normalized source
candidate. It does NOT preserve the original HTTP response bodies or screenshots.
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

ARMOR_PATH = Path(__file__).resolve().parents[1] / 'evidence/m1-30-20261117-candidate.xz.b64'
CANDIDATE_SHA256 = '8c2c164d6bc35ca22786efba3a3581e76290a68de3a1006928acd79013c912f1'
CANDIDATE_SIZE = 76_346
DATASET_ID = 'run-20261117-083055-361cff6a3eb7'
OBS_START = date.fromisoformat('2026-10-11')
OBS_END = date.fromisoformat('2026-11-14')
HEX = re.compile(r'[0-9a-f]{64}\Z')
ARMOR = re.compile(r'[A-Za-z0-9+/]+={0,2}\Z')


class CandidateError(ValueError):
    """Invalid, incomplete or unapproved persisted evidence."""


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise CandidateError(detail)


def read_candidate(path: Path = ARMOR_PATH) -> tuple[bytes, dict]:
    """Bound decompression, pin exact source bytes and validate all 1,050 values."""
    require(path.is_file() and not path.is_symlink(), 'missing or linked evidence file')
    require(path.stat().st_size <= 8_100, 'oversized evidence armor')
    try:
        armor = path.read_text(encoding='ascii')
        require(armor.endswith('\n') and ARMOR.fullmatch(armor[:-1]) is not None,
                'noncanonical evidence armor')
        compressed = base64.b64decode(armor[:-1], validate=True)
        require(base64.b64encode(compressed).decode('ascii') == armor[:-1],
                'noncanonical base64 representation')
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=128 * 1024 * 1024)
        source = decoder.decompress(compressed, max_length=CANDIDATE_SIZE + 1)
        require(decoder.eof and not decoder.unused_data and len(source) == CANDIDATE_SIZE,
                'truncated, trailing or oversized compressed candidate')
    except (OSError, ValueError, EOFError, lzma.LZMAError) as exc:
        if isinstance(exc, CandidateError):
            raise
        raise CandidateError('cannot decode retained candidate') from exc
    require(hmac.compare_digest(sha256(source).hexdigest(), CANDIDATE_SHA256),
            'candidate bytes do not match independent SHA-256')
    try:
        data = json.loads(source)
    except (ValueError, UnicodeError) as exc:
        raise CandidateError('invalid candidate JSON') from exc
    require(type(data) is dict and data.get('schema_version') == 'dayflare.rolling-candidate.v1'
            and data.get('dataset_id') == DATASET_ID
            and data.get('method_version') == 'v0-empirical-35d'
            and data.get('observation_end') == str(OBS_END)
            and data.get('retrieved_at') == '2026-11-17T08:30:55Z',
            'wrong candidate identity, method or timestamps')
    series = data.get('series')
    require(type(series) is list and len(series) == 30, 'expected exactly 30 title series')
    expected_dates = [(OBS_START + timedelta(days=i)).isoformat() for i in range(35)]
    seen = set()
    for row in series:
        require(type(row) is dict and row.get('project') in ('en.wikipedia', 'ru.wikipedia')
                and type(row.get('page_id')) is int and row['page_id'] > 0
                and type(row.get('title')) is str and bool(row['title'])
                and row.get('access') == 'all-access' and row.get('agent') == 'user',
                'invalid title identity/filter')
        identity = (row['project'], row['page_id'])
        require(identity not in seen, 'duplicate page identity')
        seen.add(identity)
        observed = row.get('daily')
        require(type(observed) is list and len(observed) == 35
                and all(type(point) is dict and point.get('date') == expected_dates[i]
                        and point.get('value_state') == 'observed'
                        and type(point.get('views')) is int and point['views'] >= 0
                        for i, point in enumerate(observed)),
                'missing, invalid or out-of-window daily observation')
        provenance = row.get('source')
        require(type(provenance) is dict and provenance.get('http_status') == 200
                and type(provenance.get('body_sha256')) is str
                and HEX.fullmatch(provenance['body_sha256']) is not None,
                'missing source provenance pin')
    require(sum(p == 'en.wikipedia' for p, _ in seen) == 15
            and sum(p == 'ru.wikipedia' for p, _ in seen) == 15,
            'expected 15 series per edition')
    return source, data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        help='extract original exact candidate JSON to a NEW path (never overwrite)')
    args = parser.parse_args()
    source, data = read_candidate()
    if args.output:
        require(args.output.parent.is_dir() and not args.output.parent.is_symlink()
                and not args.output.exists() and not args.output.is_symlink(),
                'output must be a new file in an existing non-symlink directory')
        with args.output.open('xb') as handle:
            handle.write(source)
    print(json.dumps({'dataset_id': DATASET_ID, 'series': len(data['series']),
                      'daily_observations': 1050, 'candidate_sha256': CANDIDATE_SHA256,
                      'observation_start': str(OBS_START), 'observation_end': str(OBS_END),
                      'status': 'UNPUBLISHED_NORMALIZED_CANDIDATE',
                      'output': str(args.output) if args.output else None}, sort_keys=True))


if __name__ == '__main__':
    main()
