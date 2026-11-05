"""Reproduce the real 4–5 Nov EN/RU comparison from retained source bytes.

The 5 Nov artifact's twenty raw API JSON bodies were byte-identical to 4 Nov.
Retain lossless XOR deltas of the four other files; verify every recovered byte
against original provider-response manifest hashes before comparing.
No live acquisition, historical continuity inference, or publication.
"""
from __future__ import annotations

import argparse
import base64
import io
import os
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import zlib
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from .m1_identity_history import compare_bytes, write_bundle
from .m1_retained_identity import (
    DEFAULT as BEFORE, load_retained, read_file,
    strict_json, verify_members, require,
)

ROOT = Path(__file__).resolve().parents[1]
AFTER = ROOT / 'evidence/m1-identity-20261105'
DELTA_SHA256 = '64def4e4d21add65063d448f965d0bf9b86edfa186d0200f651c8fa11fe6aaff'
PROVENANCE_SHA256 = '72fd7fdd99614a70f480cb90b86cba9d36dcd39565ae79f93ad1da22e8fa4431'
PANEL_SHA256 = '6da7fd25c2000484ac2f88f40632eefe3b69f57f662b9c0bc090e43cb2e20344'
EXPECTED = {'panel.json', 'collection-report.json', 'internal-consistency.json', 'bundle-manifest.json'}


def load_pair(after: Path = AFTER):
    """Reconstruct actual 5 Nov metadata and independently verify all 24 source members."""
    before, _, baseline, original = load_retained(BEFORE)
    delta_raw = read_file(after / 'source-delta.json', 16 * 1024)
    provenance_raw = read_file(after / 'provenance.json', 16 * 1024)
    require(sha256(delta_raw).hexdigest() == DELTA_SHA256, 'Unreviewed later metadata delta')
    require(sha256(provenance_raw).hexdigest() == PROVENANCE_SHA256, 'Unreviewed later provenance')
    p = strict_json(provenance_raw)
    delta = strict_json(delta_raw)
    require(delta['schema_version'] == 'dayflare.identity-source-xor-delta.v1', 'Unexpected delta schema')
    require(delta['baseline_panel_sha256'] == sha256(original['panel.json']).hexdigest(),
            'Delta baseline differs from pinned source')
    require(set(delta['files']) == EXPECTED, 'Missing or unlisted metadata delta')
    require(delta['no_change_raw_bodies'] == 20, 'Unreviewed raw reuse inventory')
    core = {}
    for name, spec in delta['files'].items():
        src = original[name]
        require(0 < len(src) == spec['bytes'] <= 256 * 1024, 'Metadata delta length differs')
        require(sha256(src).hexdigest() == spec['before_sha256'], 'Metadata base hash mismatch')
        compressed = base64.b64decode(spec['xor_zlib_base64'], validate=True)
        require(len(compressed) <= 8 * 1024, 'Compressed delta too large')
        inflater = zlib.decompressobj()
        mask = inflater.decompress(compressed, len(src) + 1)
        require(inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail and
                len(mask) == len(src), 'Metadata delta failed bounded decoding')
        reconstructed = bytes(a ^ b for a, b in zip(src, mask))
        require(sha256(reconstructed).hexdigest() == spec['after_sha256'],
                'Metadata delta result hash mismatch')
        core[name] = reconstructed
    require(sha256(core['panel.json']).hexdigest() == delta['later_panel_sha256'],
            'Delta later panel pin mismatch')
    require({k: v['after_sha256'] for k, v in delta['files'].items()} == p['delta']['core_files_sha256'],
            'Provenance metadata digests differ')
    members = dict(core)
    members.update((name, data) for name, data in original.items() if name.startswith('raw/'))
    require(len(members) == p['delta']['reconstructed_member_count'] == 24,
            'Reconstructed identity inventory differs')
    # The original 5 Nov manifest (not merely the 4 Nov receipt) verifies
    # every independently hash-pinned reused raw decoded API response.
    later, proof = verify_members(members, p)
    require(sha256(members['panel.json']).hexdigest() == p['followup_panel_sha256'] == PANEL_SHA256,
            'Follow-up panel pin mismatch')
    old_keys = {(r['page_ref']['project'], r['page_ref']['page_id']) for r in before['pages']}
    new_keys = {(r['page_ref']['project'], r['page_ref']['page_id']) for r in later['pages']}
    require(old_keys == new_keys and len(old_keys) == 20, 'Later local ID set changed')
    old_rows = sorted(before['pages'], key=lambda x: (x['page_ref']['project'], x['page_ref']['page_id']))
    new_rows = sorted(later['pages'], key=lambda x: (x['page_ref']['project'], x['page_ref']['page_id']))
    for old, new in zip(old_rows, new_rows):
        require(all(old[k] == new[k] for k in ('page_ref', 'topic_id', 'subject', 'relation')),
                'Later editorial scope changed')
    result = compare_bytes(original['panel.json'], members['panel.json'])
    require(result['evidence_kind'] == 'reported_retrieval', 'Real source kind required')
    require([x['observation_date_utc'] for x in result['inputs']] ==
            ['2026-11-04', '2026-11-05'], 'Unexpected paired observation dates')
    require(result['summary']['identities_in_union'] == 20 and
            result['summary']['observed_in_both'] == 20 and
            result['summary']['change_counts'] == {'unchanged_observation': 20},
            'Unexpected observed change in actual retained inputs')
    require(not any(r['pageview_join_allowed'] for r in result['pages']), 'Unsafe pageview join')
    return original['panel.json'], members['panel.json'], p, result, proof


def build(output: Path, after: Path = AFTER):
    before_raw, after_raw, _, report, _ = load_pair(after)
    with tempfile.TemporaryDirectory(prefix='dayflare-dated-pair-') as tmp:
        before, later = Path(tmp) / 'before.json', Path(tmp) / 'later.json'
        before.write_bytes(before_raw)
        later.write_bytes(after_raw)
        write_bundle(before, later, Path(output))  # no overwrite; manifest last
    return report


def build_archive(output: Path, after: Path = AFTER):
    """Package the accepted real report for offline visitors, without replacing an existing ZIP.

    All HTML, JSON and manifest bytes come from the same validated renderer as the
    directory output. Stable ZIP metadata makes identical inputs byte-reproducible.
    A same-directory hard link publishes the completed ZIP without an overwrite race.
    """
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Refusing to replace an existing report: {output}")
    with tempfile.TemporaryDirectory(prefix='dayflare-real-pair-build-') as tmp:
        rendered = Path(tmp) / 'report'
        report = build(rendered, after)
        payload = io.BytesIO()
        with ZipFile(payload, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for name in ('index.html', 'history.json', 'manifest.json'):
                info = ZipInfo(name, date_time=(2026, 11, 5, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, (rendered / name).read_bytes(),
                                 compress_type=ZIP_DEFLATED, compresslevel=9)
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, staged = tempfile.mkstemp(prefix='.dayflare-real-pair-', suffix='.zip',
                                      dir=output.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload.getvalue())
                stream.flush()
                os.fsync(stream.fileno())
            os.link(staged, output)  # atomic no-replace, even if another writer races
        finally:
            os.unlink(staged)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', type=Path, help='new canonical HTML/JSON history directory')
    parser.add_argument('--zip', dest='archive', type=Path,
                        help='new deterministic offline ZIP with HTML, JSON and manifest')
    args = parser.parse_args(argv)
    if args.archive and args.output:
        parser.error('Choose either output directory or --zip, not both')
    try:
        report = (build_archive(args.archive) if args.archive else
                  build(args.output) if args.output else load_pair()[3])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'INVALID: {exc}', file=sys.stderr)
        return 2
    print(f"VALIDATED {report['summary']['observed_in_both']}/20 EN/RU stable IDs; "
          f"{report['summary']['change_counts'].get('unchanged_observation', 0)} unchanged observations; "
          'UNPUBLISHED and continuity unknown')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
