"""Replay a separately pinned original 30-title Actions ZIP with today's renderer.

Offline only: no new observations, trust enrollment, release or Pages writes.
The original browser receipt describes the old HTML, not the rebuilt preview.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

from .m1_30_archive import MAX_ZIP, digest, read_zip, require, verify
from .rolling_snapshot_preview import export_verified_preview
from .rolling_window_gate import stamp

PREFIX = 'm1-30-source/'
METADATA = {'candidate.json', 'seeds.json', 'source-receipt.json'}
RAW_NAME = re.compile(r'raw/(?:en|ru)\.wikipedia\.[1-9][0-9]*\.json\Z')


def replay(source: Path, destination: Path, expected_sha256: str) -> dict:
    """Verify a pinned ZIP and rebuild from original source bytes, not old HTML."""
    source, destination = Path(source), Path(destination)
    require(re.fullmatch(r'[0-9a-f]{64}', expected_sha256) is not None,
            'expected an independent lowercase SHA-256 pin')
    require(source.is_file() and not source.is_symlink(), 'missing or linked source ZIP')
    parent = destination.absolute().parent
    require(parent.is_dir() and not any(p.is_symlink() for p in (parent, *parent.parents))
            and not destination.exists() and not destination.is_symlink(),
            'destination must be new inside an existing real directory')
    # Hash and read the SAME bounded bytes; never reopen a mutable original ZIP.
    with source.open('rb') as handle:
        raw = handle.read(MAX_ZIP + 1)
    require(len(raw) <= MAX_ZIP and digest(raw) == expected_sha256,
            'source ZIP exceeds budget or differs from independent SHA-256')
    with TemporaryDirectory(prefix='.dayflare-30-replay-', dir=parent) as tmp:
        scratch = Path(tmp)
        pinned = scratch / 'original.zip'
        pinned.write_bytes(raw)
        files = read_zip(pinned)
        facts = verify(files)
        members = {name[len(PREFIX):]: data for name, data in files.items()
                   if name.startswith(PREFIX)}
        raw_names = set(members) - METADATA
        require(METADATA <= set(members) and len(raw_names) == 30
                and all(RAW_NAME.fullmatch(name) is not None for name in raw_names),
                'unexpected source member inventory')
        bundle = scratch / 'source'
        (bundle / 'raw').mkdir(parents=True)
        for name, data in members.items():
            (bundle / name).write_bytes(data)
        # The source verifier replays all raw responses and enforces exact inventory,
        # filters and timestamps. Use the historical retrieval instant, not today.
        manifest = export_verified_preview(bundle, destination,
                                           now=stamp(facts['retrieved_at']))
    return {'source_actions_zip_sha256': expected_sha256,
            'source_commit': facts['source_commit'],
            'source_html_sha256': facts['html_sha256'],
            'preview': manifest,
            'status': 'LOCAL_REBUILD_NOT_PUBLISHED_BROWSER_NOT_RUN'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='original successful Actions ZIP')
    parser.add_argument('destination', type=Path, help='new local preview directory')
    parser.add_argument('--expected-sha256', required=True,
                        help='independently recorded original ZIP SHA-256')
    args = parser.parse_args(argv)
    try:
        result = replay(args.source, args.destination, args.expected_sha256)
    except (OSError, ValueError) as exc:
        print(f'REPLAY_REJECTED: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
