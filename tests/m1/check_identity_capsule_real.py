"""Replay the accepted 4-Nov baseline through the generic capsule, offline only."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import m1_identity_capsule as capsule
from tools.m1_identity_panel import canonical_bytes
from tools.m1_bundle_verify import verify_bundle

# Independently accepted evidence/m1-identity-20261104/provenance.json pins.
# These are SOURCE pins, not approval of this new renderer or its output ZIP.
SOURCE_MANIFEST = 'ec53dddeef0164359f921250043d997c0dc8abd0dd9b6740118681ab35b6873f'
SOURCE_REVISION = '90c0f4db491680246d73190bac1545f021779c07'
SOURCE_RUN = 'https://github.com/drevendev/Dayflare/actions/runs/41814628479'


def check(bundle: Path, destination: Path) -> dict:
    sources = capsule.snapshot_directory(bundle)
    capsule.need(capsule.digest(sources['source/bundle-manifest.json']) == SOURCE_MANIFEST,
                 'not the accepted 4-Nov source manifest')
    options = dict(source_revision=SOURCE_REVISION, source_run_url=SOURCE_RUN,
                   evidence_kind='reported_retrieval')
    first = capsule.build_capsule(bundle, **options)
    second = capsule.build_capsule(bundle, **options)
    capsule.need(first == second, 'real replay is not deterministic')
    files, receipt = capsule.verify_capsule(first, capsule.digest(first))
    capsule.need({name: data for name, data in files.items() if name.startswith('source/')} == sources,
                 'replay changed original source members')
    capsule.need((receipt['intended_count'], receipt['retained_count'], receipt['unavailable_count'])
                 == (20, 20, 0), 'unexpected accepted source coverage')
    capsule.need(receipt['observation_date_utc'] == '2026-11-04', 'unexpected source date')
    capsule.need(receipt['retrieval_completed_at_utc'] is None, 'invented completion time')
    destination.mkdir()  # No existing artifact is replaced, including racing writers.
    pin = capsule.write_capsule(destination / 'identity-evidence-20261104.zip', first)
    capsule.unpack_capsule(first, pin, destination / 'preview')
    capsule.need(verify_bundle(destination / 'preview/source')['verified_pages'] == 20,
                 'unpacked bundle does not pass original verifier')
    for name, data in sources.items():
        capsule.need((destination / 'preview' / name).read_bytes() == data,
                     'unpacked source bytes differ')
    result = {'status': 'HISTORICAL_REPLAY_NOT_PUBLISHED', 'source_manifest_sha256': SOURCE_MANIFEST,
              'capsule_sha256': pin, 'capsule_bytes': len(first), 'source_members': len(sources),
              'retained_identities': 20, 'observation_date_utc': '2026-11-04',
              'network_requests': 0, 'network_origin_verified': False,
              'two_builds_identical': True, 'all_source_bytes_preserved': True}
    (destination / 'SHA256SUMS').write_text(pin + '  identity-evidence-20261104.zip\n', encoding='ascii')
    (destination / 'replay-check.json').write_bytes(canonical_bytes(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path, help='source/ from the accepted baseline adapter')
    parser.add_argument('destination', type=Path, help='new replay output directory')
    args = parser.parse_args()
    try:
        result = check(args.bundle, args.destination)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'REAL_REPLAY_INVALID: {exc}\n')
    print(canonical_bytes(result).decode(), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
