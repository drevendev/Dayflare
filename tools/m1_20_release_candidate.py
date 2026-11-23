"""Stage a Nov 18 real-source M1 release-format candidate; NEVER deploy it.

This is deliberately distinct from the local-only preview. It replays the
Git-pinned original responses using the existing preview builder, then applies
the separately established strict dated-publication presentation/revision
gate. Review/permission checks still precede any later public release.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
from tempfile import TemporaryDirectory

from .m1_20_local_atlas import build as build_local
from .m1_20_retained_source import CANDIDATE_SHA256, SEED_SHA256, pinned_members
from .m1_pages_overlay import verified_m1_candidate
from .m1_publication_gate import (
    PublicationError, SCHEMA, MAX_FILE, canonical, compare_release, digest, public_copy,
    require_current_release, strict_object,
)
from .rolling_pageview_source import _atomic_new_dir



def _open_candidate_directory(directory: Path) -> int:
    """Pin every directory component to no-follow POSIX handles.

    Path preflight + Path.read_bytes is unsafe: an attacker can replace the
    member or an ancestor with a symlink between validation and reading.
    """
    if (not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW") or
            not hasattr(os, "O_NONBLOCK") or
            os.open not in os.supports_dir_fd or os.listdir not in os.supports_fd):
        raise PublicationError("race-safe candidate audit requires POSIX dir_fd/O_NOFOLLOW")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fd = None
    try:
        fd = os.open("/" if directory.is_absolute() else ".", flags)
        for part in directory.parts:
            if part in ("/", "."):
                continue
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except OSError as exc:
        if fd is not None:
            os.close(fd)
        raise PublicationError("candidate requires an existing non-symlink directory path") from exc


def _read_candidate_member(directory_fd: int, name: str) -> bytes:
    """Open one regular member by its pinned directory, reading at most MAX_FILE."""
    # O_NONBLOCK prevents a raced-in FIFO from hanging before fstat can reject it.
    flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
             getattr(os, "O_CLOEXEC", 0))
    try:
        member_fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise PublicationError("linked or inaccessible M1 candidate member") from exc
    try:
        first = os.fstat(member_fd)
        if (not stat.S_ISREG(first.st_mode) or first.st_nlink != 1 or
                not 0 <= first.st_size <= MAX_FILE):
            raise PublicationError("linked, special or oversized M1 candidate member")
        chunks = []
        size = 0
        while True:
            chunk = os.read(member_fd, min(65536, MAX_FILE - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE:
                raise PublicationError("oversized M1 candidate member during read")
            chunks.append(chunk)
        last = os.fstat(member_fd)
        identity = lambda s: (
            s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size,
            s.st_mtime_ns, s.st_ctime_ns,
        )
        if size != first.st_size or identity(first) != identity(last):
            raise PublicationError("M1 candidate member changed while reading")
        return b"".join(chunks)
    finally:
        os.close(member_fd)


def _candidate_inventory(directory_fd: int) -> set[str]:
    """Enumerate members through the held directory descriptor."""
    return set(os.listdir(directory_fd))


def verify_existing(directory: Path, expected_manifest_sha256: str) -> dict:
    """Audit already-exported bytes without rebuilding, writing or network access.

    A hash read from the same directory is NOT independent approval. The caller
    must supply a separately recorded 64-hex manifest SHA-256.
    """
    if (type(expected_manifest_sha256) is not str or
            re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256) is None):
        raise PublicationError("independent 64-hex M1 manifest pin required")
    directory_fd = _open_candidate_directory(Path(directory))
    try:
        before = os.fstat(directory_fd)
        required = {"index.html", ".nojekyll", "release-manifest.json"}
        if _candidate_inventory(directory_fd) != required:
            raise PublicationError("unexpected M1 candidate directory inventory")
        files = {
            name: _read_candidate_member(directory_fd, name)
            for name in sorted(required)
        }
        after = os.fstat(directory_fd)
        if (_candidate_inventory(directory_fd) != required or
                before.st_mtime_ns != after.st_mtime_ns or
                before.st_ctime_ns != after.st_ctime_ns):
            raise PublicationError("M1 candidate directory changed while reading")
    finally:
        os.close(directory_fd)
    manifest = verified_m1_candidate(files, CANDIDATE_SHA256, expected_manifest_sha256)
    return {
        "result": "VERIFIED_NOT_APPROVED_NOT_DEPLOYED",
        "manifest_sha256": expected_manifest_sha256,
        "html_sha256": manifest["html_sha256"],
        "observation_end": manifest["observation_end"],
        "retrieved_at": manifest["retrieved_at"],
    }


def build(destination: Path, previous_manifest: Path | None = None) -> dict:
    """Write three immutable, source-bound files to a NEW local directory."""
    destination = Path(destination)
    if (destination.exists() or destination.is_symlink() or
            not destination.parent.is_dir() or destination.parent.is_symlink()):
        raise PublicationError("candidate requires a new path in an existing real directory")
    with TemporaryDirectory(prefix=".dayflare-m1-candidate-", dir=destination.parent) as name:
        scratch = Path(name)
        preview = scratch / "verified-preview"
        local = build_local(preview)  # Pinned source/body replay and deterministic renderer.
        members = pinned_members()  # Recheck immutable XZ and exact safe tar inventory.
        candidate_raw = members["candidate.json"]
        receipt_raw = members["source-receipt.json"]
        seed_raw = members["seeds.json"]
        candidate = strict_object(candidate_raw, "retained candidate")
        if (digest(candidate_raw) != CANDIDATE_SHA256 or
                digest(seed_raw) != SEED_SHA256 or
                local["candidate_sha256"] != CANDIDATE_SHA256 or
                local["source_seed_sha256"] != SEED_SHA256 or
                local["series"] != 20 or
                local["observation_end"] != candidate["observation_end"] or
                local["retrieved_at"] != candidate["retrieved_at"] or
                local["provenance_status"] !=
                "runtime_reported_transport_not_independently_authenticated"):
            raise PublicationError("pinned source, receipt or preview mismatch")
        html = public_copy((preview / "index.html").read_bytes())
        manifest = {
            "schema_version": SCHEMA,
            "status": "DATED_ARCHIVE_NOT_LIVE",
            "dataset_id": candidate["dataset_id"],
            "method_version": candidate["method_version"],
            "observation_end": candidate["observation_end"],
            "retrieved_at": candidate["retrieved_at"],
            "candidate_sha256": CANDIDATE_SHA256,
            "source_receipt_sha256": digest(receipt_raw),
            "source_seed_sha256": SEED_SHA256,
            "html_sha256": digest(html),
            "series": 20,
            "daily_observations": 700,
        }
        require_current_release(manifest)
        previous = None
        if previous_manifest is not None:
            previous_manifest = Path(previous_manifest)
            if (previous_manifest.is_symlink() or not previous_manifest.is_file() or
                    previous_manifest.stat().st_size > 65536):
                raise PublicationError("unsafe or oversized previous release manifest")
            previous = strict_object(previous_manifest.read_bytes(), "previous")
        decision = compare_release(previous, manifest)
        output = scratch / "release"
        output.mkdir()
        (output / "index.html").write_bytes(html)
        (output / ".nojekyll").write_bytes(b"")
        raw = canonical(manifest)
        (output / "release-manifest.json").write_bytes(raw)
        # This is an INTERNAL CONSISTENCY check; self-derived hashes never
        # constitute independent release approval.
        verified_m1_candidate(
            {p.name: p.read_bytes() for p in output.iterdir()},
            CANDIDATE_SHA256, digest(raw),
        )
        if (digest((output / "index.html").read_bytes()) != manifest["html_sha256"] or
                (output / "release-manifest.json").read_bytes() != raw):
            raise PublicationError("candidate readback mismatch")
        _atomic_new_dir(output, destination)  # No-replace atomic visibility.
    return {
        "result": "STAGED_NOT_DEPLOYED",
        "decision": decision,
        "candidate_sha256": CANDIDATE_SHA256,
        "manifest_sha256": digest(raw),
        "html_sha256": manifest["html_sha256"],
        "observation_end": manifest["observation_end"],
        "retrieved_at": manifest["retrieved_at"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new local directory only")
    parser.add_argument("--previous-manifest", type=Path,
                        help="independently accepted prior M1 release manifest")
    parser.add_argument("--verify-manifest-sha256", metavar="SHA256",
                        help="read-only verify existing candidate with an external manifest pin")
    args = parser.parse_args(argv)
    try:
        if args.verify_manifest_sha256 is not None:
            if args.previous_manifest is not None:
                raise PublicationError("--previous-manifest is only for staging")
            result = verify_existing(args.destination, args.verify_manifest_sha256)
        else:
            result = build(args.destination, args.previous_manifest)
    except (ValueError, OSError) as exc:
        print(f"NOT_DEPLOYED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
