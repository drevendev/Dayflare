"""Restore the exact Nov 26 source ZIP or rebuild its local 19-title atlas offline."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / 'evidence/m1-niche-20261126-source'
SIZES = (3072,) * 5 + (3042,)
NAMES = tuple(f'part-{i:02d}.bin' for i in range(len(SIZES)))
ZIP_SHA256 = '122d1d43246d8d34afcef6b2721cc5aeb805c19458d0a4ef86f898bf6aaf5a45'
RETRIEVED = '2026-11-26T05:24:57Z'
META = {'candidate.json', 'seeds.json', 'source-receipt.json'}
RAW_NAME = re.compile(r'raw/(?:en|ru)\.wikipedia\.[1-9][0-9]*\.json\Z')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def archive_bytes(parts: Path = PARTS) -> bytes:
    """The ordered fragments are a lossless transport, not separate datasets."""
    parts = Path(parts).absolute()
    require(parts.is_dir() and not any(p.is_symlink() for p in (parts, *parts.parents)),
            'missing or linked archive directory')
    require({p.name for p in parts.iterdir()} == set(NAMES), 'unexpected archive parts')
    chunks = []
    for name, size in zip(NAMES, SIZES):
        path = parts / name
        require(path.is_file() and not path.is_symlink(), 'missing or linked archive part')
        with path.open('rb') as stream:
            chunk = stream.read(size + 1)
        require(len(chunk) == size, 'wrong archive part size')
        chunks.append(chunk)
    raw = b''.join(chunks)
    require(sha256(raw).hexdigest() == ZIP_SHA256, 'original ZIP SHA-256 mismatch')
    return raw


def new_destination(destination: Path) -> Path:
    path = Path(destination).absolute()
    parent = path.parent
    require(parent.is_dir() and not any(p.is_symlink() for p in (parent, *parent.parents))
            and not path.exists() and not path.is_symlink(), 'destination must be new')
    return path


def restore(destination: Path, parts: Path = PARTS) -> dict:
    raw = archive_bytes(parts)
    destination = new_destination(destination)
    with destination.open('xb') as stream:
        stream.write(raw)
    return {'original_zip_sha256': ZIP_SHA256, 'bytes': len(raw),
            'status': 'ORIGINAL_SOURCE_ZIP_RESTORED_NOT_PUBLISHED'}


def replay(destination: Path, parts: Path = PARTS) -> dict:
    """Use the canonical full source verifier/renderer at historical retrieval time."""
    from .m1_30_archive import decode, read_zip
    from .rolling_snapshot_preview import export_verified_preview
    from .rolling_window_gate import stamp

    raw = archive_bytes(parts)
    destination = new_destination(destination)
    with TemporaryDirectory(prefix='.dayflare-niche-replay-', dir=destination.parent) as tmp:
        scratch = Path(tmp)
        original = scratch / 'original.zip'
        original.write_bytes(raw)
        members = read_zip(original)
        raw_names = set(members) - META
        require(META <= set(members) and len(raw_names) == 19
                and all(RAW_NAME.fullmatch(name) for name in raw_names),
                'unexpected source member inventory')
        receipt = decode(members['source-receipt.json'], 'source receipt')
        require(receipt.get('retrieved_at') == RETRIEVED, 'unexpected historical retrieval')
        bundle = scratch / 'source'
        (bundle / 'raw').mkdir(parents=True)
        for name, value in members.items():
            (bundle / name).write_bytes(value)
        manifest = export_verified_preview(bundle, destination, now=stamp(RETRIEVED))
    return {'original_zip_sha256': ZIP_SHA256, 'preview': manifest,
            'status': 'LOCAL_REBUILD_NOT_PUBLISHED_BROWSER_NOT_RUN'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('restore', 'replay'))
    parser.add_argument('destination', type=Path)
    args = parser.parse_args(argv)
    try:
        result = restore(args.destination) if args.operation == 'restore' else replay(args.destination)
    except (OSError, ValueError) as exc:
        print(f'NICHE_REPLAY_REJECTED: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
