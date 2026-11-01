"""Create an immutable UNPUBLISHED M1 static candidate from retained real-source CI.

This is not a deployer. A separate later acceptance and authorized, exact-head
Pages publication are required. Never replace the existing M0 release here.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from zipfile import ZipFile, BadZipFile

HEX = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = "dayflare.m1.static-snapshot.v1"
MAX_ZIP = 4 * 1024 * 1024
MAX_FILE = 512 * 1024
MAX_EXPANDED = 8 * 1024 * 1024


class PublicationError(ValueError):
    """This candidate must not be adopted/deployed."""


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def strict_object(data: bytes, label: str) -> dict:
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise PublicationError(f"{label}: duplicate key {key}")
            obj[key] = value
        return obj

    def invalid(value):
        raise PublicationError(f"{label}: nonfinite number {value}")

    try:
        doc = json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                         parse_constant=invalid)
    except (UnicodeDecodeError, ValueError) as exc:
        raise PublicationError(f"{label}: invalid JSON") from exc
    if type(doc) is not dict:
        raise PublicationError(f"{label}: expected object")
    return doc


def read_archive(path: Path) -> dict[str, bytes]:
    """Reject traversal, duplicates, special members and decompression bombs."""
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_ZIP:
        raise PublicationError("missing, linked or oversized Actions archive")
    files = {}
    total = 0
    try:
        with ZipFile(path) as archive:
            for item in archive.infolist():
                name = item.filename
                parts = PurePosixPath(name).parts
                if (not name or name.startswith("/") or "\\" in name or
                        any(part in ("", ".", "..") for part in name.split("/")) or
                        not parts or item.is_dir() or name in files or
                        item.compress_type not in (0, 8)):
                    raise PublicationError("unsafe or duplicate Actions ZIP member")
                mode = item.external_attr >> 16
                if mode and (mode & 0o170000) not in (0, 0o100000):
                    raise PublicationError("non-regular Actions ZIP member")
                if item.file_size > MAX_FILE:
                    raise PublicationError("oversized ZIP member")
                with archive.open(item) as stream:
                    data = stream.read(MAX_FILE + 1)
                if len(data) != item.file_size or len(data) > MAX_FILE:
                    raise PublicationError("truncated or oversized ZIP member")
                total += len(data)
                if total > MAX_EXPANDED:
                    raise PublicationError("expanded Actions archive exceeds budget")
                files[name] = data
    except (BadZipFile, OSError, EOFError) as exc:
        raise PublicationError("unreadable Actions archive") from exc
    return files


def _release_revision(manifest: dict) -> tuple[date, datetime]:
    """Require an exact UTC retrieval after the complete observation day."""
    try:
        observation = manifest["observation_end"]
        retrieval = manifest["retrieved_at"]
        if (type(observation) is not str or
                re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", observation) is None):
            raise ValueError("noncanonical observation date")
        observed = date.fromisoformat(observation)
        if observed.isoformat() != observation:
            raise ValueError("noncanonical observation date")
        if (type(retrieval) is not str or
                re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
                             retrieval) is None):
            raise ValueError("noncanonical UTC retrieval")
        retrieved = datetime.fromisoformat(retrieval.replace("Z", "+00:00"))
        # Compare dates instead of adding one day: max-year dates must fail
        # closed without overflowing datetime's supported range.
        if (retrieved.utcoffset() is None or
                retrieved.utcoffset().total_seconds() != 0 or
                retrieved.date() <= observed):
            raise ValueError("retrieval cannot predate the completed observation day")
        return observed, retrieved
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise PublicationError("invalid previous/proposed revision time") from exc


def compare_release(previous: dict | None, proposed: dict) -> str:
    """No older release, same-revision collision or silent method migration."""
    new = _release_revision(proposed)
    if previous is None:
        return "FIRST_M1_CANDIDATE_REQUIRES_SEPARATE_PUBLICATION_APPROVAL"
    required = {"schema_version", "dataset_id", "method_version", "observation_end",
                "retrieved_at", "candidate_sha256", "html_sha256", "source_receipt_sha256",
                "source_seed_sha256", "series", "daily_observations", "status"}
    if set(previous) != required or previous.get("schema_version") != SCHEMA:
        raise PublicationError("previous release is not M1; explicit migration review required")
    if previous["method_version"] != proposed["method_version"]:
        raise PublicationError("method change needs explicit migration")
    for field in ("candidate_sha256", "html_sha256", "source_receipt_sha256", "source_seed_sha256"):
        if type(previous[field]) is not str or not HEX.fullmatch(previous[field]):
            raise PublicationError("previous release has invalid digest")
    if previous["status"] != "DATED_ARCHIVE_NOT_LIVE" or previous["series"] != 20 or previous["daily_observations"] != 700:
        raise PublicationError("previous release has incompatible coverage or status")
    old = _release_revision(previous)
    if new < old:
        raise PublicationError("rollback: previous release is newer")
    # Each CI run stages into a fresh directory. A 20-row count and matching
    # method do NOT prevent replacing the reviewed editorial title/ID basket.
    # A new selection must be adopted through a separately reviewed migration.
    if previous["source_seed_sha256"] != proposed.get("source_seed_sha256"):
        raise PublicationError("curated source seed changed; explicit cohort migration review required")
    if new == old:
        if previous != proposed:
            raise PublicationError("same-revision collision or metadata drift")
        return "UNCHANGED_ALREADY_CURRENT"
    if previous["dataset_id"] == proposed["dataset_id"]:
        raise PublicationError("dataset ID reused across different revisions")
    return "NEWER_CANDIDATE_STILL_REQUIRES_PUBLICATION_APPROVAL"


def public_copy(html: bytes) -> bytes:
    """Retain exact metrics while replacing three reviewed local-preview labels."""
    text = html.decode("utf-8")
    substitutions = {
        "Dayflare · dated attention atlas (local preview)": "Dayflare · dated attention atlas",
        "<strong>LOCAL EVIDENCE — UPSTREAM ORIGIN NOT INDEPENDENTLY VERIFIED</strong>. This is an offline preview, <strong>not</strong> a public release, live feed, stable historical page-ID series or representative ranking.":
            "<strong>DATED SOURCE EVIDENCE — UPSTREAM ORIGIN NOT INDEPENDENTLY VERIFIED</strong>. This archived snapshot is <strong>not</strong> a live feed, stable historical page-ID series or representative ranking.",
        "A rolling preview is not a live publication.":
            "An archived snapshot is not a live measurement or a freshness guarantee.",
    }
    for before, after in substitutions.items():
        if text.count(before) != 1:
            raise PublicationError("unknown preview HTML/version; refuse presentation rewrite")
        text = text.replace(before, after)
    if "SYNTHETIC TEST DATA" in text or "LOCAL EVIDENCE" in text:
        raise PublicationError("synthetic or unreviewed local-only HTML")
    return text.encode("utf-8")


def build(archive: Path, destination: Path, expected_candidate_sha256: str,
          previous_manifest: Path | None = None) -> dict:
    """Reverify the exact source and HTML then atomically stage without deployment."""
    if not HEX.fullmatch(expected_candidate_sha256):
        raise PublicationError("candidate SHA-256 pin required")
    from tools.rolling_pageview_source import verify_bundle, _atomic_new_dir
    from tools.rolling_window_gate import stamp
    from tools.stage_rolling_version import _current, _check_directory
    from tools.rolling_snapshot_preview import export_staged_current_preview

    files = read_archive(archive)
    needed = {"m1-curated-source/candidate.json", "m1-curated-source/source-receipt.json",
              "m1-curated-source/seeds.json", "m1-curated-seed.json",
              "m1-curated-stage/current.json", "m1-curated-preview/index.html",
              "m1-curated-preview/preview-manifest.json", "index.html", "START_HERE.txt"}
    if not needed.issubset(files):
        raise PublicationError("incomplete source/stage/preview Actions artifact")
    if digest(files["m1-curated-source/candidate.json"]) != expected_candidate_sha256:
        raise PublicationError("Actions candidate differs from SHA-256 pin")
    seed_for_inventory = strict_object(files["m1-curated-seed.json"], "inventory seed")
    rows = seed_for_inventory.get("pages")
    if type(rows) is not list or len(rows) != 20:
        raise PublicationError("archive seed must contain precisely 20 identities")
    raw_names = set()
    for row in rows:
        if (type(row) is not dict or row.get("project") not in ("en.wikipedia", "ru.wikipedia")
                or type(row.get("page_id")) is not int or row["page_id"] <= 0):
            raise PublicationError("invalid archive seed identity")
        raw_names.add(f"raw/{row['project']}.{row['page_id']}.json")
    if len(raw_names) != 20:
        raise PublicationError("duplicate identity in archived seed")
    source_names = {"candidate.json", "seeds.json", "source-receipt.json"} | raw_names
    version_prefix = f"m1-curated-stage/versions/{expected_candidate_sha256}/"
    expected_names = ({"m1-curated-seed.json", "m1-curated-stage/current.json",
                       "m1-curated-preview/index.html", "m1-curated-preview/preview-manifest.json",
                       "index.html", "START_HERE.txt"} |
                      {"m1-curated-source/" + name for name in source_names} |
                      {version_prefix + name for name in ("candidate.json", "gate-report.json", "manifest.json")} |
                      {version_prefix + "source/" + name for name in source_names})
    if set(files) != expected_names:
        raise PublicationError("Actions archive has unexpected/missing source evidence members")

    with tempfile.TemporaryDirectory(prefix="dayflare-gate-") as root_name:
        root = Path(root_name)
        for name, data in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        stage = root / "m1-curated-stage"
        _check_directory(stage)
        _check_directory(stage / "versions")
        pointer = _current(stage)  # Recomputes source/receipt/gate/manifest checks.
        if pointer is None or pointer["version_sha256"] != expected_candidate_sha256:
            raise PublicationError("versioned pointer differs from candidate pin")
        proof = verify_bundle(root / "m1-curated-source", now=stamp(pointer["retrieved_at"]))
        if (proof["candidate_sha256"] != expected_candidate_sha256 or
                proof["series"] != 20 or proof["observations"] != 700):
            raise PublicationError("source coverage or digest differs")
        if proof["provenance_status"] != "runtime_reported_transport_not_independently_authenticated":
            raise PublicationError("synthetic or incompatible provenance")
        if files["m1-curated-seed.json"] != files["m1-curated-source/seeds.json"]:
            raise PublicationError("seed mismatch")
        seed = strict_object(files["m1-curated-seed.json"], "seed")
        counts = {(ed, sub): 0 for ed in ("en.wikipedia", "ru.wikipedia")
                  for sub in ("culture", "books", "games", "science", "sport")}
        for row in seed["pages"]:
            key = row.get("project"), row.get("subject")
            if key not in counts:
                raise PublicationError("unknown edition/subject")
            counts[key] += 1
        if any(value != 2 for value in counts.values()):
            raise PublicationError("20-title curated coverage changed")
        regenerated = root / "regenerated"
        verified = export_staged_current_preview(stage, regenerated)
        for name in ("index.html", "preview-manifest.json"):
            if files[f"m1-curated-preview/{name}"] != (regenerated / name).read_bytes():
                raise PublicationError("Actions preview differs from source-recomputed HTML/manifest")
        if files["index.html"] != files["m1-curated-preview/index.html"]:
            raise PublicationError("ZIP root entrypoint differs from verified preview")
        candidate = strict_object(files["m1-curated-source/candidate.json"], "candidate")
        output_html = public_copy(files["index.html"])
        manifest = {
            "schema_version": SCHEMA, "status": "DATED_ARCHIVE_NOT_LIVE",
            "dataset_id": candidate["dataset_id"], "method_version": candidate["method_version"],
            "observation_end": candidate["observation_end"], "retrieved_at": candidate["retrieved_at"],
            "candidate_sha256": expected_candidate_sha256,
            "source_receipt_sha256": digest(files["m1-curated-source/source-receipt.json"]),
            "source_seed_sha256": proof["seed_sha256"], "html_sha256": digest(output_html),
            "series": 20, "daily_observations": 700,
        }
        if (verified["candidate_sha256"] != expected_candidate_sha256 or
                verified["html_sha256"] != digest(files["index.html"])):
            raise PublicationError("replayed preview manifest differs")
        previous = None
        if previous_manifest is not None:
            if previous_manifest.is_symlink() or previous_manifest.stat().st_size > 65536:
                raise PublicationError("unsafe or oversized previous public manifest")
            previous = strict_object(previous_manifest.read_bytes(), "previous")
        decision = compare_release(previous, manifest)
        if destination.exists() or destination.is_symlink():
            raise PublicationError("refusing to replace previously staged candidate")
        if not destination.parent.is_dir() or destination.parent.is_symlink():
            raise PublicationError("candidate parent must be an existing real directory")
        temp = Path(tempfile.mkdtemp(prefix=".dayflare-m1-", dir=destination.parent))
        try:
            (temp / "index.html").write_bytes(output_html)
            (temp / ".nojekyll").write_bytes(b"")
            (temp / "release-manifest.json").write_bytes(canonical(manifest))
            if digest((temp / "index.html").read_bytes()) != manifest["html_sha256"]:
                raise PublicationError("staged HTML failed readback")
            _atomic_new_dir(temp, destination)
        finally:
            if temp.exists():
                import shutil
                shutil.rmtree(temp)
    return {"result": "STAGED_NOT_DEPLOYED", "decision": decision,
            "candidate_sha256": expected_candidate_sha256,
            "html_sha256": manifest["html_sha256"],
            "observation_end": manifest["observation_end"],
            "retrieved_at": manifest["retrieved_at"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--previous-manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        result = build(args.archive, args.destination, args.expected_candidate_sha256,
                       args.previous_manifest)
    except (PublicationError, OSError, ValueError) as exc:
        print(f"NOT_DEPLOYED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
