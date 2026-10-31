"""Stage validated rolling candidates without replacing a newer local accepted candidate.

OFFLINE ONLY. This does not authenticate Wikimedia sources or update a website.
A POSIX advisory lock serializes cooperating writers; immutable SHA-addressed
version directories and an atomic pointer preserve the previous valid candidate.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time

from .rolling_window_gate import (WindowError, canonical, read_candidate, stamp,
                                  validate, require, MAX_BYTES)

SCHEMA = "dayflare.rolling-stage.v1"
POINTER_SCHEMA = "dayflare.rolling-current.v1"
PROVENANCE = "self_reported_not_independently_verified"
STATUS = "LOCAL_CANDIDATE_ONLY_NOT_PUBLISHED"
VERSION_FILES = frozenset({"candidate.json", "gate-report.json", "manifest.json"})
SOURCE_VERSION_FILES = VERSION_FILES | {"source"}
SOURCE_SCHEMA = "dayflare.rolling-stage.v2"
SOURCE_PROVENANCE = "runtime_reported_transport_not_independently_authenticated"


class StageError(ValueError):
    pass


def _check_directory(path: Path, *, allow_create: bool = False) -> None:
    if allow_create:
        path.mkdir(exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise StageError(f"unsafe or missing directory: {path}")


def _regular_bytes(path: Path, limit: int = MAX_BYTES) -> bytes:
    if path.is_symlink():
        raise StageError(f"linked artifact rejected: {path}")
    try:
        mode = path.stat().st_mode
    except FileNotFoundError as exc:
        raise StageError(f"missing artifact: {path}") from exc
    if not stat.S_ISREG(mode):
        raise StageError(f"non-file artifact: {path}")
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if not 0 < len(payload) <= limit:
        raise StageError(f"empty/oversize artifact: {path}")
    return payload


def _json_object(raw: bytes, where: str):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise StageError(f"{where}: duplicate JSON key")
            result[name] = value
        return result

    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                            parse_constant=lambda x: (_ for _ in ()).throw(StageError("nonfinite JSON")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageError(f"{where}: malformed JSON") from exc
    if not isinstance(result, dict):
        raise StageError(f"{where}: object required")
    return result


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_once(path: Path, value: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _exclusive(root: Path):
    # The lock is deliberately retained between calls. A crashed process drops
    # its flock automatically; a PID file or manual lock-breaking is unnecessary.
    _check_directory(root, allow_create=True)
    lock = root / ".stage.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise StageError("lock is not a regular file")
        until = time.monotonic() + 10
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= until:
                    raise StageError("staging lock busy; no change made")
                time.sleep(0.04)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _expected_fields(manifest):
    return {key: manifest[key] for key in (
        "version_sha256", "dataset_id", "method_version", "observation_end", "retrieved_at")}


def _version_files(root: Path, sha: str):
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
        raise StageError("invalid candidate digest in pointer")
    directory = root / "versions" / sha
    _check_directory(directory)
    inventory = {x.name for x in directory.iterdir()}
    if inventory not in (VERSION_FILES, SOURCE_VERSION_FILES):
        raise StageError("version has missing or extra files")
    has_source = inventory == SOURCE_VERSION_FILES
    blobs = {name: _regular_bytes(directory / name) for name in VERSION_FILES}
    if _sha(blobs["candidate.json"]) != sha:
        raise StageError("candidate bytes do not match immutable version name")
    doc = _json_object(blobs["candidate.json"], "candidate")
    report = _json_object(blobs["gate-report.json"], "gate-report")
    manifest = _json_object(blobs["manifest.json"], "manifest")
    if canonical(doc) != blobs["candidate.json"] or canonical(report) != blobs["gate-report.json"] or canonical(manifest) != blobs["manifest.json"]:
        raise StageError("noncanonical version member")
    keys = {"schema_version", "version_sha256", "gate_report_sha256", "dataset_id", "method_version",
            "observation_end", "retrieved_at", "provenance_status", "publication_status"}
    if has_source:
        keys |= {"source_receipt_sha256", "source_provenance_status"}
    if (set(manifest) != keys or
            manifest["schema_version"] != (SOURCE_SCHEMA if has_source else SCHEMA) or
            manifest["version_sha256"] != sha or
            manifest["gate_report_sha256"] != _sha(blobs["gate-report.json"])):
        raise StageError("invalid manifest or gate report digest")
    if (manifest["provenance_status"] != PROVENANCE or manifest["publication_status"] != STATUS
            or report.get("candidate_sha256") != sha
            or report.get("schema_version") != "dayflare.rolling-gate-report.v1"
            or report.get("provenance_status") != PROVENANCE
            or report.get("publication_status") != "NOT_STAGED_NOT_DEPLOYED"):
        raise StageError("version report/provenance disagrees")
    if any(manifest[k] != doc.get(k) or manifest[k] != report.get(k)
           for k in ("dataset_id", "method_version", "observation_end", "retrieved_at")):
        raise StageError("version metadata disagreement")
    # A self-consistent edited report+manifest digest is not evidence that
    # daily counts, coverage or windows were actually validated. Recompute
    # the exact historical gate decision at the recorded retrieval instant:
    # a later wall clock cannot retroactively make an early source complete.
    try:
        original_report = validate(doc, now=stamp(doc["retrieved_at"]))
    except (WindowError, ValueError) as exc:
        raise StageError("stored candidate invalid at retrieval time") from exc
    if canonical(original_report) != blobs["gate-report.json"]:
        raise StageError("stored gate report differs from recalculated candidate")
    if has_source:
        # The v2 immutable version preserves the exact source evidence, not
        # merely a claim that it was once verified before pointer promotion.
        from .rolling_pageview_source import SourceError, verify_bundle
        source_root = directory / "source"
        try:
            proof = verify_bundle(source_root, now=stamp(doc["retrieved_at"]))
        except (SourceError, WindowError, OSError) as exc:
            raise StageError("stored source bundle failed retained-body verification") from exc
        if (proof["candidate_sha256"] != sha or
                proof["provenance_status"] != SOURCE_PROVENANCE or
                manifest["source_provenance_status"] != SOURCE_PROVENANCE or
                _regular_bytes(source_root / "candidate.json") != blobs["candidate.json"] or
                _sha(_regular_bytes(source_root / "source-receipt.json")) != manifest["source_receipt_sha256"]):
            raise StageError("stored source receipt/candidate binding mismatch")
    return manifest


def _current(root: Path):
    path = root / "current.json"
    if not path.exists() and not path.is_symlink():
        return None
    pointer_raw = _regular_bytes(path, 64 * 1024)
    pointer = _json_object(pointer_raw, "current")
    if canonical(pointer) != pointer_raw or set(pointer) != {
        "schema_version", "version_sha256", "dataset_id", "method_version", "observation_end",
        "retrieved_at", "provenance_status", "publication_status",
    } or pointer["schema_version"] != POINTER_SCHEMA:
        raise StageError("malformed current pointer")
    version = _version_files(root, pointer["version_sha256"])
    if any(pointer[k] != version[k] for k in _expected_fields(version)) or pointer["provenance_status"] != PROVENANCE or pointer["publication_status"] != STATUS:
        raise StageError("current pointer disagrees with immutable version")
    return pointer


def _pointer(manifest):
    return {"schema_version": POINTER_SCHEMA,
            **_expected_fields(manifest),
            "provenance_status": PROVENANCE,
            "publication_status": STATUS}


def _ordering(manifest):
    return date.fromisoformat(manifest["observation_end"]), stamp(manifest["retrieved_at"])


def _publish_pointer(root: Path, pointer: dict):
    fd, tmp = tempfile.mkstemp(prefix=".current-", dir=root)
    path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(pointer))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(path, root / "current.json")  # Single atomic visibility boundary.
        _fsync_dir(root)
    finally:
        path.unlink(missing_ok=True)


def _materialize_version(root: Path, manifest: dict, data: bytes, report: bytes,
                         source_bundle: Path | None = None):
    versions = root / "versions"
    _check_directory(versions, allow_create=True)
    sha = manifest["version_sha256"]
    destination = versions / sha
    if destination.exists() or destination.is_symlink():
        old = _version_files(root, sha)
        if old != manifest:
            raise StageError("immutable version collision")
        return False
    temp = Path(tempfile.mkdtemp(prefix=".incoming-", dir=versions))
    try:
        for filename, payload in (("candidate.json", data), ("gate-report.json", report),
                                  ("manifest.json", canonical(manifest))):
            _write_once(temp / filename, payload)
        if source_bundle is not None:
            # Bounded immutable copy, no symlinks or implicit reads outside the
            # reviewed bundle. Reverify the copied bytes before publishing them
            # and before changing current.json; a source race fails closed.
            from .rolling_pageview_source import MAX_BODY, SourceError, verify_bundle
            source_root = Path(source_bundle)
            _check_directory(source_root)
            raw_root = source_root / "raw"
            _check_directory(raw_root)
            retained = temp / "source"
            retained.mkdir()
            retained_raw = retained / "raw"
            retained_raw.mkdir()
            for name, limit in (("candidate.json", MAX_BYTES),
                                ("source-receipt.json", MAX_BYTES),
                                ("seeds.json", 32 * 1024)):
                _write_once(retained / name, _regular_bytes(source_root / name, limit))
            members = list(raw_root.iterdir())
            if not 1 <= len(members) <= 30:
                raise StageError("invalid retained response inventory")
            for member in sorted(members):
                _write_once(retained_raw / member.name, _regular_bytes(member, MAX_BODY))
            _fsync_dir(retained_raw)
            _fsync_dir(retained)
            try:
                proof = verify_bundle(retained, now=stamp(manifest["retrieved_at"]))
            except (SourceError, WindowError, OSError) as exc:
                raise StageError("source changed during immutable staging") from exc
            if (proof["candidate_sha256"] != sha or
                    proof["provenance_status"] != SOURCE_PROVENANCE or
                    _regular_bytes(retained / "candidate.json") != data or
                    _sha(_regular_bytes(retained / "source-receipt.json")) != manifest["source_receipt_sha256"]):
                raise StageError("copied source receipts do not match staged candidate")
        _fsync_dir(temp)
        # Under the same advisory lock, cooperative writers cannot race here.
        # os.rename won't overwrite an existing non-empty destination directory.
        os.rename(temp, destination)
        _fsync_dir(versions)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    if _version_files(root, sha) != manifest:
        raise StageError("post-stage readback mismatch")
    return True


def stage(doc: dict, root: Path, *, now=None,
          source_bundle: Path | None = None) -> dict:
    # Fail closed before filesystem mutations for invalid candidate data.
    report = validate(doc, now=now)
    # A candidate staged days after its recorded source retrieval must not
    # acquire provider-lag completeness that it lacked when collected.
    try:
        validate(doc, now=stamp(doc["retrieved_at"]))
    except (WindowError, ValueError) as exc:
        raise StageError("candidate was not complete at retrieval time") from exc
    candidate_raw = canonical(doc)
    report_raw = canonical(report)
    sha = _sha(candidate_raw)
    if source_bundle is not None:
        from .rolling_pageview_source import SourceError, verify_bundle
        source_bundle = Path(source_bundle)
        # Validate before the first stage directory/lock is created. This is
        # internally consistent, self-reported transport, NOT upstream proof.
        try:
            proof = verify_bundle(source_bundle, now=stamp(doc["retrieved_at"]))
        except (SourceError, WindowError, OSError) as exc:
            raise StageError("source bundle failed retained-body verification") from exc
        if (proof["candidate_sha256"] != sha or
                proof["provenance_status"] != SOURCE_PROVENANCE or
                _regular_bytes(source_bundle / "candidate.json") != candidate_raw):
            raise StageError("source receipt/candidate mismatch or synthetic source")
    manifest = {
        "schema_version": SCHEMA,
        "version_sha256": sha,
        "gate_report_sha256": _sha(report_raw),
        "dataset_id": doc["dataset_id"], "method_version": doc["method_version"],
        "observation_end": doc["observation_end"], "retrieved_at": doc["retrieved_at"],
        "provenance_status": PROVENANCE,
        "publication_status": STATUS,
    }
    if source_bundle is not None:
        manifest.update({
            "schema_version": SOURCE_SCHEMA,
            "source_receipt_sha256": _sha(_regular_bytes(source_bundle / "source-receipt.json")),
            "source_provenance_status": SOURCE_PROVENANCE,
        })
    root = Path(root)
    with _exclusive(root):
        previous = _current(root)
        if previous is not None:
            # Once accepted evidence includes retained raw source bodies, future
            # candidates must preserve that verification level. A plausible
            # self-reported v1 revision must not replace a source-bound v2.
            prior_manifest = _version_files(root, previous["version_sha256"])
            if prior_manifest["schema_version"] == SOURCE_SCHEMA and source_bundle is None:
                raise StageError("source-backed stage cannot promote an unverified revision")
            if previous["method_version"] != manifest["method_version"]:
                raise StageError("method version change needs explicit migration")
            old_key, new_key = _ordering(previous), _ordering(manifest)
            if new_key < old_key:
                raise StageError("rollback: older observation/retrieval revision")
            if new_key == old_key and previous["version_sha256"] != sha:
                raise StageError("collision: same revision has different candidate bytes")
            if previous["dataset_id"] == manifest["dataset_id"] and previous["version_sha256"] != sha:
                raise StageError("dataset ID reused for different bytes")
        staged_new = _materialize_version(root, manifest, candidate_raw, report_raw,
                                          source_bundle=source_bundle)
        if previous is None or previous["version_sha256"] != sha:
            _publish_pointer(root, _pointer(manifest))
            outcome = "PROMOTED_LOCAL_CANDIDATE_ONLY"
        else:
            outcome = "UNCHANGED_IDEMPOTENT"
        if _current(root) != _pointer(manifest):
            raise StageError("current pointer readback mismatch")
        return {"result": outcome, "version_sha256": sha,
                "observation_end": manifest["observation_end"],
                "retrieved_at": manifest["retrieved_at"],
                "version_created": staged_new,
                "provenance_status": PROVENANCE,
                "publication_status": STATUS}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("stage_root", type=Path)
    args = parser.parse_args(argv)
    try:
        result = stage(read_candidate(args.candidate), args.stage_root)
    except (OSError, WindowError, StageError, ValueError) as exc:
        print(f"STAGE_REJECTED: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
