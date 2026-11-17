"""Verify and open a preserved M1 30-title atlas without contacting the network.

An independently supplied exact ZIP SHA-256 is mandatory. This consumes a local
UNPUBLISHED evidence capsule; verification does not approve its origin or deploy it.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
from pathlib import Path
import re

from tools.m1_30_archive import (
    ArchiveError, SCHEMA, decode, digest, read_zip, require, verify, MAX_ZIP,
)


UNPUBLISHED = 'UNPUBLISHED_PRESERVED_EVIDENCE_NOT_PAGES'
ORIGIN = 'runtime-reported; not independently authenticated'
EXTRA = {'archive-manifest.json', 'README.txt'}


def consume(source: Path, expected_sha256: str, html_out: Path | None = None) -> dict:
    """Fail closed before writing; never replace a previous visitor download."""
    require(isinstance(expected_sha256, str) and
            re.fullmatch(r'[0-9a-f]{64}', expected_sha256) is not None,
            'independent lowercase SHA-256 pin required')
    require(source.is_file() and not source.is_symlink() and
            source.stat().st_size <= MAX_ZIP, 'missing/linked/oversized preserved ZIP')
    original_bytes = source.read_bytes()
    actual = sha256(original_bytes).hexdigest()
    require(hmac.compare_digest(actual, expected_sha256),
            'preserved ZIP differs from independent SHA-256 pin')
    members = read_zip(source)  # Includes member/path/size/duplicate safety limits.
    require(digest(source.read_bytes()) == actual,
            'preserved ZIP changed during verification')
    require(EXTRA <= members.keys(), 'missing preserved archive manifest or README')
    archive = decode(members['archive-manifest.json'], 'archive-manifest')
    require(archive.get('schema_version') == SCHEMA and
            archive.get('status') == UNPUBLISHED and
            archive.get('upstream_origin') == ORIGIN and
            members['README.txt'].startswith(b'Dayflare | PRESERVED REAL EN/RU EVIDENCE'),
            'unexpected archive version, publication state or disclaimer')
    recorded = archive.get('files')
    originals = {name: raw for name, raw in members.items() if name not in EXTRA}
    require(type(recorded) is dict and set(recorded) == set(originals),
            'archive manifest must cover every original member exactly')
    for name, raw in originals.items():
        require(type(recorded[name]) is str and
                hmac.compare_digest(recorded[name], digest(raw)),
                'archive member SHA-256 mismatch: ' + name)
    require(type(archive.get('source_actions_zip_sha256')) is str and
            re.fullmatch(r'[0-9a-f]{64}', archive['source_actions_zip_sha256']) is not None,
            'missing original Actions ZIP digest')
    facts = verify(originals)  # Re-check all 30 histories and real-output browser receipts.
    for key, value in facts.items():
        require(archive.get(key) == value, 'archive/source fact mismatch: ' + key)
    if html_out is not None:
        require(not html_out.exists() and not html_out.is_symlink() and
                html_out.parent.is_dir() and not html_out.parent.is_symlink(),
                'HTML destination must be new in a real directory')
        # Exclusive creation means a previous accepted download is never replaced.
        with html_out.open('xb') as handle:
            handle.write(originals['index.html'])
    return {**facts, 'archive_sha256': actual, 'status': UNPUBLISHED,
            'html_path': str(html_out) if html_out else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='preserved 30-title ZIP')
    parser.add_argument('--expected-sha256', required=True,
                        help='independently accepted exact lowercase SHA-256 of ZIP')
    parser.add_argument('--html-out', type=Path,
                        help='optional new path for verified standalone HTML')
    args = parser.parse_args()
    print(json.dumps(consume(args.archive, args.expected_sha256, args.html_out),
                     sort_keys=True))


if __name__ == '__main__':
    main()
