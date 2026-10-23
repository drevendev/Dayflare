"""Package an unapproved, reproducible M0 artifact from an exact checkout.

This is a read-only CI output, NOT an independent release approval or deployment.
Only an accepted master revision may be uploaded by the caller's workflow gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from tools.build_static_release import ROOT, build_zip, bundle_files, digest
from tools.stage_pages import checked_files

SHA1 = re.compile(r'[0-9a-f]{40}\Z')
CONTENTS = {'dayflare-m0.zip', 'release-manifest.json', 'release-receipt.json'}


class CandidateError(ValueError):
    """Fail closed if an artifact is ambiguous, changed or not source-bound."""


def candidate_bytes(files: dict[str, bytes], commit: str) -> dict[str, bytes]:
    """Create exactly three deterministic files; hashes are proposals, not approvals."""
    if not isinstance(commit, str) or not SHA1.fullmatch(commit):
        raise CandidateError('Exact 40-character lowercase source commit required')
    manifest = files.get('release-manifest.json')
    if not isinstance(manifest, bytes):
        raise CandidateError('Missing source-bound release manifest')
    archive = build_zip(files)
    # This self-derived checksum is for integrity only. A reviewer must pin the
    # manifest independently before staging or publishing this candidate.
    checked_files(archive, digest(manifest), files)
    metadata = json.loads(manifest)
    receipt = {
        'status': 'UNAPPROVED_MASTER_CANDIDATE_NOT_DEPLOYED',
        'source_commit': commit,
        'archive_sha256': digest(archive),
        'manifest_sha256': digest(manifest),
        'dataset_id': metadata['dataset_id'],
        'method_version': metadata['method_version'],
        'observation_window_utc': metadata['observation_window_utc'],
        'independent_approval': False,
        'live_verified': False,
        'note': 'Hash is self-computed, not independent approval. No Pages deployment.',
    }
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    return {
        'dayflare-m0.zip': archive,
        'release-manifest.json': manifest,
        'release-receipt.json': receipt_bytes,
    }


def check_candidate(destination: Path, expected: dict[str, bytes]) -> None:
    if destination.is_symlink() or not destination.is_dir():
        raise CandidateError('Candidate directory is missing or a symlink')
    actual = set()
    for path in destination.rglob('*'):
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise CandidateError('Candidate contains an unsafe filesystem entry')
        if path.is_file():
            actual.add(path.relative_to(destination).as_posix())
    if actual != CONTENTS or set(expected) != CONTENTS:
        raise CandidateError('Candidate inventory differs from exact expected files')
    for name in CONTENTS:
        if (destination / name).read_bytes() != expected[name]:
            raise CandidateError(f'Candidate bytes changed: {name}')


def write_candidate(destination: Path, files: dict[str, bytes], commit: str) -> dict[str, bytes]:
    """Create a new location exclusively; never replace an earlier candidate."""
    expected = candidate_bytes(files, commit)
    if destination.exists() or destination.is_symlink():
        raise CandidateError('Candidate already exists; refusing to replace it')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()  # atomic fail if another writer created this directory
    try:
        for name, contents in sorted(expected.items()):
            with (destination / name).open('xb') as stream:
                stream.write(contents)
        check_candidate(destination, expected)
    except BaseException:
        # Only this invocation's newly-created directory is removable.
        shutil.rmtree(destination)
        raise
    return expected


def exact_checkout(expected_commit: str) -> None:
    if not SHA1.fullmatch(expected_commit):
        raise CandidateError('Expected source SHA must be lowercase 40-hex')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != expected_commit:
        raise CandidateError(f'Checked out {head}, expected {expected_commit}')
    dirty = subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--'], cwd=ROOT, check=False)
    if dirty.returncode != 0:
        raise CandidateError('Tracked source differs from exact checked-out commit')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        exact_checkout(args.expected_commit)
        files = bundle_files(ROOT)
        expected = write_candidate(args.output, files, args.expected_commit)
    except (CandidateError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    print('PASS UNAPPROVED_NOT_DEPLOYED source_commit=' + args.expected_commit +
          ' archive_sha256=' + digest(expected['dayflare-m0.zip']) +
          ' manifest_sha256=' + digest(expected['release-manifest.json']))


if __name__ == '__main__':
    main()
