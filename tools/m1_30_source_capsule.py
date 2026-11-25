"""Compact text transport for exact source members; not the original ZIP or a release."""
from __future__ import annotations

import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
import lzma
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from zipfile import ZipFile

PREFIX = 'm1-30-source/'
META = {'candidate.json', 'seeds.json', 'source-receipt.json'}
RAW = re.compile(r'raw/(?:en|ru)\.wikipedia\.[1-9][0-9]*\.json\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')
MAX_ZIP = 4 * 1024 * 1024
MAX_PAYLOAD = 2 * 1024 * 1024
MAX_ARMOR = 256 * 1024
SCHEMA = 'dayflare.m1-30-source-capsule.v1'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return sha256(raw).hexdigest()


def pinned(path, pin, limit):
    require(type(pin) is str and HEX.fullmatch(pin) is not None, 'independent SHA-256 required')
    require(path.is_file() and not path.is_symlink(), 'missing or linked input')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit and digest(data) == pin, 'input size or SHA-256 mismatch')
    return data


def inventory(names):
    names = set(names)
    raw = names - META
    require(META <= names and len(raw) == 30 and all(RAW.fullmatch(n) for n in raw),
            'unexpected source inventory')


def canonical(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')


def pack(source: Path, original_pin: str) -> bytes:
    """Copy exact UTF-8 members from a pinned ZIP; does not accept or publish data."""
    raw = pinned(source, original_pin, MAX_ZIP)
    with ZipFile(BytesIO(raw)) as archive:
        entries = archive.infolist()
        require(len(entries) <= 200 and len({x.filename for x in entries}) == len(entries),
                'too many or duplicate ZIP entries')
        selected = {x.filename[len(PREFIX):]: x for x in entries if x.filename.startswith(PREFIX)}
        inventory(selected)
        require(sum(x.file_size for x in selected.values()) <= MAX_PAYLOAD,
                'source members over budget')
        members = {}
        for name, info in selected.items():
            require(not info.is_dir() and (info.external_attr >> 16) & 0o170000 != 0o120000
                    and not info.flag_bits & 1, 'unsafe source member')
            members[name] = archive.read(info).decode('utf-8')
    payload = canonical({'schema': SCHEMA, 'original_zip_sha256': original_pin, 'members': members})
    require(len(payload) <= MAX_PAYLOAD, 'payload over budget')
    armor = base64.b64encode(lzma.compress(payload, format=lzma.FORMAT_XZ, preset=6)) + b'\n'
    require(len(armor) <= MAX_ARMOR, 'capsule over budget')
    return armor


def unpack(source: Path, capsule_pin: str, original_pin: str) -> dict[str, bytes]:
    """Return exact source bytes only; independent capsule and original pins are required."""
    armor = pinned(source, capsule_pin, MAX_ARMOR)
    require(armor.endswith(b'\n'), 'missing armor newline')
    compressed = base64.b64decode(armor[:-1], validate=True)
    require(base64.b64encode(compressed) + b'\n' == armor, 'noncanonical armor')
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=128 * 1024 * 1024)
    payload = decoder.decompress(compressed, max_length=MAX_PAYLOAD + 1)
    require(decoder.eof and not decoder.unused_data and len(payload) <= MAX_PAYLOAD,
            'truncated, trailing or oversized capsule')
    doc = json.loads(payload)
    require(type(doc) is dict and set(doc) == {'schema', 'original_zip_sha256', 'members'}
            and canonical(doc) == payload and doc['schema'] == SCHEMA,
            'noncanonical capsule payload')
    require(type(original_pin) is str and HEX.fullmatch(original_pin) is not None
            and doc['original_zip_sha256'] == original_pin, 'original ZIP pin mismatch')
    members = doc['members']
    require(type(members) is dict and all(type(v) is str for v in members.values()),
            'invalid source members')
    inventory(members)
    return {name: value.encode('utf-8') for name, value in members.items()}


def replay(source: Path, destination: Path, capsule_pin: str, original_pin: str) -> dict:
    """Run the existing full source verifier/renderer, at the historical retrieval instant."""
    from .rolling_snapshot_preview import export_verified_preview
    from .rolling_window_gate import stamp

    members = unpack(source, capsule_pin, original_pin)
    parent = destination.absolute().parent
    require(parent.is_dir() and not any(p.is_symlink() for p in (parent, *parent.parents))
            and not destination.exists() and not destination.is_symlink(), 'destination must be new')
    with TemporaryDirectory(prefix='.dayflare-source-capsule-', dir=parent) as tmp:
        bundle = Path(tmp)
        (bundle / 'raw').mkdir()
        for name, raw in members.items():
            (bundle / name).write_bytes(raw)
        receipt = json.loads(members['source-receipt.json'])
        manifest = export_verified_preview(bundle, destination, now=stamp(receipt['retrieved_at']))
    return {'capsule_sha256': capsule_pin, 'original_zip_sha256': original_pin,
            'preview': manifest, 'status': 'LOCAL_REBUILD_NOT_PUBLISHED_BROWSER_NOT_RUN'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('pack', 'replay'))
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--original-sha256', required=True)
    parser.add_argument('--capsule-sha256')
    args = parser.parse_args(argv)
    if args.operation == 'pack':
        require(args.capsule_sha256 is None, 'pack does not take a capsule pin')
        armor = pack(args.source, args.original_sha256)
        with args.destination.open('xb') as target:
            target.write(armor)
        result = {'capsule_sha256': digest(armor), 'bytes': len(armor),
                  'status': 'SOURCE_TRANSPORT_ONLY_NOT_PUBLISHED'}
    else:
        result = replay(args.source, args.destination, args.capsule_sha256, args.original_sha256)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
