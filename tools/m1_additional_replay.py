"""Restore exact additional-cohort source members, not the original ZIP or a release."""
import argparse
import base64
from hashlib import sha256
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
CAPSULE = ROOT / 'evidence/m1-additional-20261127-source.xz.b64'
CAPSULE_SHA = '47af99f9708820bb9d67d5c1b504f91827e2204fbbb877df77eb0ff46636bc71'
ZIP_SHA = '47f789ce1d09c7597ab27f71a936233c35daea770e8f914301c1925b60a10c42'
CANDIDATE_SHA = '4cde167a050fdb0a9d50a1804137f0a0b848f9e3d6ad3cff5f47531c61cac149'
SEED_SHA = 'd3fad61ef128bcf98daf24fd9b929ca6836bead89b07c390bd804ff0d65ad68a'
RETRIEVED = '2026-11-27T17:20:31Z'
IDS = {'en.wikipedia': (6644, 23579, 48193, 333987, 7239234),
       'ru.wikipedia': (7817, 36225, 83471, 149670, 1016844)}
NAMES = {'candidate.json', 'seeds.json', 'source-receipt.json'} | {
    f'raw/{p}.{i}.json' for p, ids in IDS.items() for i in ids}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return sha256(raw).hexdigest()


def members(path=CAPSULE):
    path = Path(path).absolute()
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
            'missing or linked capsule')
    with path.open('rb') as stream:
        armor = stream.read(7090)
    require(len(armor) == 7089 and digest(armor) == CAPSULE_SHA, 'capsule pin mismatch')
    compressed = base64.b64decode(armor[:-1], validate=True)
    require(base64.b64encode(compressed) + b'\n' == armor, 'noncanonical armor')
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=128 * 1024 * 1024)
    payload = decoder.decompress(compressed, max_length=200001)
    require(decoder.eof and not decoder.unused_data and len(payload) <= 200000,
            'invalid capsule payload')
    doc = json.loads(payload)
    require(set(doc) == {'schema', 'original_zip_sha256', 'members'}
            and doc['schema'] == 'dayflare.m1-additional-source-capsule.v1'
            and doc['original_zip_sha256'] == ZIP_SHA, 'capsule metadata mismatch')
    require(set(doc['members']) == NAMES and all(type(v) is str for v in doc['members'].values()),
            'source member inventory mismatch')
    raw = {n: v.encode('utf-8') for n, v in doc['members'].items()}
    require(digest(raw['candidate.json']) == CANDIDATE_SHA
            and digest(raw['seeds.json']) == SEED_SHA, 'source pin mismatch')
    receipt = json.loads(raw['source-receipt.json'])
    require(receipt['retrieved_at'] == RETRIEVED and receipt['candidate_sha256'] == CANDIDATE_SHA
            and receipt['seed_sha256'] == SEED_SHA, 'source receipt mismatch')
    sources = receipt['sources']
    require(len(sources) == 10 and {s['raw_member'] for s in sources} == NAMES - {
        'candidate.json', 'seeds.json', 'source-receipt.json'}, 'receipt inventory mismatch')
    require(all(digest(raw[s['raw_member']]) == s['body_sha256'] for s in sources),
            'source body mismatch')
    return raw


def restore(destination, path=CAPSULE):
    raw = members(path)
    destination = Path(destination).absolute()
    require(destination.parent.is_dir() and not any(p.is_symlink() for p in destination.parents)
            and not destination.exists() and not destination.is_symlink(), 'destination must be new')
    destination.mkdir()
    (destination / 'raw').mkdir()
    for name, value in sorted(raw.items()):
        (destination / name).write_bytes(value)
    return {'status': 'SOURCE_MEMBERS_RESTORED_NOT_PUBLISHED', 'members': len(raw),
            'capsule_sha256': CAPSULE_SHA, 'original_zip_sha256': ZIP_SHA}


def replay(destination, path=CAPSULE, *, historical_edition=False):
    from .rolling_snapshot_preview import export_verified_preview
    from .rolling_window_gate import stamp

    destination = Path(destination).absolute()
    with TemporaryDirectory(prefix='.dayflare-additional-', dir=destination.parent) as scratch:
        bundle = Path(scratch) / 'source'
        restore(bundle, path)
        preview = export_verified_preview(bundle, destination, now=stamp(RETRIEVED),
                                          historical_edition=historical_edition)
    return {'status': 'CANDIDATE_NOT_PUBLISHED_BROWSER_NOT_RUN', 'preview': preview}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('restore', 'replay', 'edition'))
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    result = restore(args.destination) if args.operation == 'restore' else replay(
        args.destination, historical_edition=args.operation == 'edition')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
