"""Synchronize README's dated M1 release facts from an independently pinned archive.

Offline only. This tool does not accept or deploy a release: the expected manifest
SHA-256 must come from a separately reviewed native gh-pages release. A manifest
retrieved from the same untrusted directory is never its own trust anchor.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import tempfile

START = "<!-- dayflare:m1-release:start -->"
END = "<!-- dayflare:m1-release:end -->"
OLD_START = "**Latest accepted archive ("
OLD_END = "\n\n### Earlier accepted release example"
SCHEMA = "dayflare.m1.static-snapshot.v1"
METHOD = "v0-empirical-35d"
FIELDS = frozenset({
    "candidate_sha256", "daily_observations", "dataset_id", "html_sha256",
    "method_version", "observation_end", "retrieved_at", "schema_version",
    "series", "source_receipt_sha256", "source_seed_sha256", "status",
})
HEX = re.compile(r"[0-9a-f]{64}\Z")
DATASET = re.compile(r"run-[0-9]{8}-[0-9]{6}-[0-9a-f]{12}\Z")


class SyncError(ValueError):
    """No release data or README should be adopted from this input."""


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SyncError("duplicate release manifest key")
        result[key] = value
    return result


def _nonfinite(value):
    raise SyncError("nonfinite release manifest value")


def _read_regular(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SyncError(f"missing or linked input: {path.name}")
    size = path.stat().st_size
    if size > limit or size < 0:
        raise SyncError(f"oversized input: {path.name}")
    raw = path.read_bytes()
    if len(raw) != size:
        raise SyncError(f"input changed during read: {path.name}")
    return raw


def accepted_manifest(release_dir: Path, expected_manifest_sha256: str) -> dict:
    if (type(expected_manifest_sha256) is not str or
            HEX.fullmatch(expected_manifest_sha256) is None):
        raise SyncError("independently reviewed manifest SHA-256 required")
    raw = _read_regular(release_dir / "release-manifest.json", 128 * 1024)
    if digest(raw) != expected_manifest_sha256:
        raise SyncError("manifest does not match independent acceptance pin")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                         parse_constant=_nonfinite)
    except SyncError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise SyncError("invalid release manifest JSON") from exc
    if type(doc) is not dict or set(doc) != FIELDS:
        raise SyncError("unexpected M1 manifest fields")
    canonical = (json.dumps(doc, sort_keys=True, ensure_ascii=False,
                            separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if raw != canonical:
        raise SyncError("noncanonical M1 manifest")
    if (doc["schema_version"] != SCHEMA or doc["method_version"] != METHOD or
            doc["status"] != "DATED_ARCHIVE_NOT_LIVE" or
            type(doc["series"]) is not int or doc["series"] != 20 or
            type(doc["daily_observations"]) is not int or doc["daily_observations"] != 700 or
            type(doc["dataset_id"]) is not str or not DATASET.fullmatch(doc["dataset_id"])):
        raise SyncError("incompatible M1 scope, method or dataset")
    for key in ("candidate_sha256", "html_sha256", "source_receipt_sha256",
                "source_seed_sha256"):
        if type(doc[key]) is not str or HEX.fullmatch(doc[key]) is None:
            raise SyncError(f"invalid {key}")
    try:
        observed = date.fromisoformat(doc["observation_end"])
        if doc["observation_end"] != observed.isoformat():
            raise ValueError("noncanonical observation date")
        retrieved = datetime.strptime(doc["retrieved_at"], "%Y-%m-%dT%H:%M:%SZ")
        if retrieved.strftime("%Y-%m-%dT%H:%M:%SZ") != doc["retrieved_at"]:
            raise ValueError("noncanonical UTC retrieval date")
        if retrieved.date() <= observed:
            raise ValueError("retrieval before complete observation")
        # 35 *complete* UTC days, including the final observation day.
        doc["_start"] = (observed - timedelta(days=34)).isoformat()
    except (TypeError, ValueError, OverflowError) as exc:
        raise SyncError("invalid M1 observation/retrieval chronology") from exc
    html = _read_regular(release_dir / "index.html", 8 * 1024 * 1024)
    if digest(html) != doc["html_sha256"]:
        raise SyncError("HTML differs from independently pinned manifest")
    return doc


def render(manifest: dict) -> str:
    return (f"{START}\n"
            f"**Latest accepted archive (observed {manifest['_start']}–{manifest['observation_end']} UTC; "
            f"retrieved {manifest['retrieved_at'].replace('T', ' ').removesuffix('Z')} UTC):** "
            f"{manifest['series']} editor-selected title-scoped EN/RU histories "
            f"across books, culture, games, science and sport; five complete UTC "
            f"weeks / {manifest['daily_observations']} daily request observations. "
            f"Dataset `{manifest['dataset_id']}`, method `{manifest['method_version']}`, "
            f"schema `{manifest['schema_version']}`. "
            f"[Accepted release manifest](https://github.com/drevendev/Dayflare/blob/gh-pages/m1/release-manifest.json) "
            f"pins the downloadable HTML SHA-256 `{manifest['html_sha256']}`; "
            f"verify with `sha256sum dayflare-m1.html`. The manifest pin must be "
            f"independently established by native release review; this generated "
            f"summary alone does not authenticate Wikimedia, approve a release or "
            f"prove Pages is live. Counts are requests, **not** people, causes, "
            f"verified page-ID histories or cross-edition equivalences. "
            f"This selected, dated sample is **not** a representative ranking, "
            f"live refresh or verified deployed website.\n{END}")


def synchronize(text: str, section: str, *, bootstrap: bool = False) -> str:
    if text.count(START) == 1 and text.count(END) == 1:
        a = text.index(START)
        b = text.index(END)
        if b < a or text.find("\n", b) == -1:
            raise SyncError("invalid README release markers")
        return text[:a] + section + text[b + len(END):]
    if START in text or END in text or not bootstrap:
        raise SyncError("README missing or duplicate release markers")
    if text.count(OLD_START) != 1 or text.count(OLD_END) != 1:
        raise SyncError("cannot safely bootstrap README release block")
    a = text.index(OLD_START)
    b = text.index(OLD_END, a)
    return text[:a] + section + text[b:]


def run(readme: Path, release_dir: Path, pin: str, *, write: bool = False,
        bootstrap: bool = False) -> bool:
    if bootstrap and not write:
        raise SyncError("--bootstrap requires --write")
    manifest = accepted_manifest(release_dir, pin)
    raw = _read_regular(readme, 512 * 1024)
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise SyncError("README is not UTF-8") from exc
    rendered = synchronize(text, render(manifest), bootstrap=bootstrap)
    if rendered == text:
        return False
    if not write:
        raise SyncError("README release facts differ from independently pinned M1")
    if readme.read_bytes() != raw:
        raise SyncError("README changed during synchronization")
    fd, name = tempfile.mkstemp(prefix=".dayflare-readme-", dir=readme.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(rendered.encode("utf-8"))
        os.chmod(name, stat.S_IMODE(readme.stat().st_mode))
        os.replace(name, readme)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-m1", type=Path, required=True,
                        help="Independently accepted, exported gh-pages/m1 directory")
    parser.add_argument("--expected-manifest-sha256", required=True,
                        help="Independent SHA-256 from reviewed native release")
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--write", action="store_true", help="Atomically update README")
    parser.add_argument("--bootstrap", action="store_true",
                        help="Explicitly migrate the one original unmarked README paragraph")
    args = parser.parse_args()
    try:
        changed = run(args.readme, args.accepted_m1, args.expected_manifest_sha256,
                      write=args.write, bootstrap=args.bootstrap)
    except (SyncError, OSError) as exc:
        parser.exit(1, f"M1 README sync rejected: {exc}\n")
    print("README_UPDATED" if changed else "README_MATCHES_ACCEPTED_MANIFEST")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
