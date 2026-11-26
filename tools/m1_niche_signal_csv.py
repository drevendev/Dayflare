"""Export exact weekly signals for the retained 19-title niche cohort, offline."""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from .m1_niche_replay import (
    META, PARTS, RAW_NAME, RETRIEVED, archive_bytes, new_destination, require,
)
from .m1_30_archive import decode, read_zip
from .m1_30_signal_csv import render_csv
from .rolling_pageview_source import verify_bundle
from .rolling_window_gate import stamp


def export(destination: Path, parts: Path = PARTS) -> bytes:
    """Verify the original pinned source before exporting; never overwrite."""
    raw = archive_bytes(parts)
    destination = new_destination(destination)
    with TemporaryDirectory(prefix='.dayflare-niche-csv-', dir=destination.parent) as tmp:
        scratch = Path(tmp)
        original = scratch / 'original.zip'
        original.write_bytes(raw)
        members = read_zip(original)
        raw_names = set(members) - META
        require(META <= set(members) and len(raw_names) == 19
                and all(RAW_NAME.fullmatch(name) for name in raw_names),
                'unexpected source member inventory')
        receipt = decode(members['source-receipt.json'], 'source receipt')
        candidate = decode(members['candidate.json'], 'candidate')
        require(receipt.get('retrieved_at') == RETRIEVED, 'unexpected historical retrieval')
        bundle = scratch / 'source'
        (bundle / 'raw').mkdir(parents=True)
        for name, data in members.items():
            (bundle / name).write_bytes(data)
        proof = verify_bundle(bundle, now=stamp(RETRIEVED))
        require(proof['series'] == 19 and proof['observations'] == 665
                and proof['candidate_sha256'] == sha256(members['candidate.json']).hexdigest(),
                'expected 19 verified complete histories')
        result = render_csv(candidate, receipt)
    with destination.open('xb') as stream:
        stream.write(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args(argv)
    try:
        export(args.destination)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'NICHE_SIGNAL_EXPORT_REJECTED: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
