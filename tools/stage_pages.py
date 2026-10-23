"""Stage a reviewed Dayflare M0 Pages candidate without publishing anything.

The caller must supply the independently approved SHA-256 of the release manifest.
The exact ZIP bytes must also match a fresh deterministic build from the current
checkout. No API calls, credentials, branch writes, or Pages deployment occur.

Example (only after an accepted manifest pin has been recorded separately):
    python -m tools.stage_pages --archive Dayflare-M0-static-Pages-UNPUBLISHED.zip \
        --destination /tmp/dayflare-pages-candidate \
        --expected-manifest-sha256 <64-hex-approved-sha256>
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED

from tools.build_static_release import ROOT, REQUIRED, build_zip, bundle_files, digest

MAX_ARCHIVE_BYTES = 5 * 1024 * 1024
MAX_ASSET_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


class StageError(ValueError):
    """Refuse ambiguous, changed or incomplete candidate staging."""


def checked_files(archive: bytes, approved_manifest_sha256: str,
                  expected: dict[str, bytes]) -> dict[str, bytes]:
    """Validate a candidate against both an independent pin and checkout bytes."""
    if not isinstance(approved_manifest_sha256, str) or not SHA256.fullmatch(approved_manifest_sha256):
        raise StageError('An independent lowercase SHA-256 manifest pin is required')
    if not isinstance(archive, bytes) or len(archive) > MAX_ARCHIVE_BYTES:
        raise StageError('Invalid or oversized release ZIP')
    if set(expected) != REQUIRED or any(not isinstance(v, bytes) for v in expected.values()):
        raise StageError('Checkout release inventory is incomplete')
    # Canonical bytes guard against appended ZIP junk, altered ZIP metadata and
    # payloads inconsistent with the reviewed source, even if internally hashed.
    if archive != build_zip(expected):
        raise StageError('Release ZIP differs from current deterministic checkout build')
    files: dict[str, bytes] = {}
    try:
        with ZipFile(io.BytesIO(archive), 'r') as z:
            entries = z.infolist()
            names = [item.filename for item in entries]
            if len(names) != len(REQUIRED) or set(names) != REQUIRED or len(set(names)) != len(names):
                raise StageError('Unexpected or duplicate release members')
            total = 0
            for entry in entries:
                name = entry.filename
                if entry.is_dir() or entry.flag_bits & 1 or entry.compress_type != ZIP_DEFLATED:
                    raise StageError(f'Unsafe ZIP entry: {name}')
                # Reject symlinks and special files. GitHub's deterministic builder
                # writes regular 0644 entries, not filesystem pointers.
                mode = entry.external_attr >> 16
                if mode != 0o644:
                    raise StageError(f'Unexpected ZIP file mode: {name}')
                limit = MAX_MANIFEST_BYTES if name == 'release-manifest.json' else MAX_ASSET_BYTES
                if entry.file_size > limit:
                    raise StageError(f'Oversized declared ZIP member: {name}')
                with z.open(entry) as source:
                    content = source.read(limit + 1)
                if len(content) > limit or len(content) != entry.file_size:
                    raise StageError(f'Invalid ZIP member size: {name}')
                total += len(content)
                if total > MAX_TOTAL_BYTES:
                    raise StageError('Release expands beyond aggregate budget')
                files[name] = content
    except (BadZipFile, OSError, EOFError) as exc:
        raise StageError(f'Cannot decode release ZIP: {exc}') from exc
    manifest_bytes = files['release-manifest.json']
    if digest(manifest_bytes) != approved_manifest_sha256:
        raise StageError('Release manifest differs from independently approved pin')
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, ValueError) as exc:
        raise StageError('Invalid release manifest') from exc
    if not isinstance(manifest, dict) or manifest.get('dataset_id') != 'd02-20261018-084126' or \
            manifest.get('method_version') != 'v0-empirical-35d' or \
            manifest.get('observation_window_utc') != ['2026-08-11', '2026-09-14'] or \
            manifest.get('status') != 'UNPUBLISHED_STATIC_RELEASE_CANDIDATE':
        raise StageError('Unexpected historical dataset/method or release state')
    names = REQUIRED - {'release-manifest.json'}
    if not isinstance(manifest.get('files_sha256'), dict) or set(manifest['files_sha256']) != names:
        raise StageError('Manifest release inventory differs from the accepted schema')
    for name in names:
        if manifest['files_sha256'][name] != digest(files[name]):
            raise StageError(f'Checksum mismatch for {name}')
        if expected[name] != files[name]:
            raise StageError(f'Checkout source differs at {name}')
    if files['.nojekyll'] != b'' or files['release-manifest.json'] != expected['release-manifest.json']:
        raise StageError('Publication directive or manifest differs from reviewed checkout')
    return files


def verify_stage(destination: Path, files: dict[str, bytes]) -> None:
    """Fail closed on missing, modified, extra or symlinked staged assets."""
    if destination.is_symlink() or not destination.is_dir():
        raise StageError('Stage directory is absent or is a symlink')
    actual = set()
    for item in destination.rglob('*'):
        if item.is_symlink():
            raise StageError('Stage contains a symlink')
        if item.is_file():
            actual.add(item.relative_to(destination).as_posix())
        elif not item.is_dir():
            raise StageError('Stage contains an unexpected special entry')
    if actual != set(files):
        raise StageError('Stage member set differs from reviewed bundle')
    for name, expected in files.items():
        if (destination / name).read_bytes() != expected:
            raise StageError(f'Staged bytes differ from approved candidate: {name}')


def stage(archive: bytes, destination: Path, approved_manifest_sha256: str,
          expected: dict[str, bytes], *, check: bool = False) -> str:
    """Stage an immutable directory, never replace an existing one."""
    files = checked_files(archive, approved_manifest_sha256, expected)
    if check:
        verify_stage(destination, files)
        return 'STAGED_VERIFIED_NOT_DEPLOYED'
    if destination.exists() or destination.is_symlink():
        raise StageError('Stage already exists; refusing to replace last valid candidate')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.dayflare-unpublished-', dir=destination.parent))
    try:
        for name, content in sorted(files.items()):
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as out:
                out.write(content)
        verify_stage(temporary, files)
        if destination.exists() or destination.is_symlink():
            raise StageError('Stage was created concurrently; refusing overwrite')
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return 'STAGED_NOT_DEPLOYED'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ROOT/'Dayflare-M0-static-Pages-UNPUBLISHED.zip')
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--expected-manifest-sha256', required=True,
                        help='Independent 64-character lowercase pin from accepted release evidence')
    parser.add_argument('--check', action='store_true', help='Verify an existing stage without writes')
    args = parser.parse_args()
    try:
        if args.archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise StageError('Release ZIP exceeds size budget')
        payload = args.archive.read_bytes()
        expected = bundle_files(ROOT)
        outcome = stage(payload, args.destination, args.expected_manifest_sha256, expected, check=args.check)
    except (StageError, OSError, ValueError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    print(f'PASS {outcome} manifest_sha256={args.expected_manifest_sha256} '
          f'archive_sha256={hashlib.sha256(payload).hexdigest()}; public URL NOT_VERIFIED')


if __name__ == '__main__':
    main()
