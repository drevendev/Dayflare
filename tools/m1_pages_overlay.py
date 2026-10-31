"""Build an additive, UNPUBLISHED Pages tree from a source-gated M1 candidate.

The existing M0 root remains byte-for-byte identical. A dated M1 atlas lives at
m1/. This module neither writes Git refs nor enables or deploys Pages.
Input directories must be exported trees, NOT working Git checkouts.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from hashlib import sha1, sha256
import json
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

from tools.m1_publication_gate import (
    PublicationError, SCHEMA, canonical, compare_release, strict_object,
)
from tools.rolling_pageview_source import _atomic_new_dir

RELEASE_FILES = {"index.html", ".nojekyll", "release-manifest.json"}
# Byte-exact release workflow versions (#84, #87, #92, #95; #100 pending review).
# Preserve byte-exact versions during the M1 release transition. These are metadata,
# not manifest-listed M0 assets; unknown paths/modified bytes remain fatal.
APPROVED_RELEASE_METADATA_BLOBS = {
    ".github/workflows/m1-release-candidate.yml": frozenset({
        "5d1a217c713e428394e35eee2d5cbc659d92e5f5",
        "767601f69ef00c028b1f87459c1abb29784bbd8f",
        "826f45d83de5b601c7d48cbed168ae23c1d11a16",
        "d674555c610c9c29498d3656b8365672ff7978d4",
        "68bc227fb8eb3585cc5df301a74610ea57e4e84d",
    }),
}
HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_FILES = 100
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TREE_BYTES = 24 * 1024 * 1024


def sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    """Identify exact GitHub-reviewed workflow bytes, including the blob header."""
    return sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def inventory(root: Path) -> dict[str, bytes]:
    """Read an exported tree strictly, rejecting links, specials and oversize."""
    if root.is_symlink() or not root.is_dir():
        raise PublicationError("expected an existing non-symlink exported tree")
    files: dict[str, bytes] = {}
    total = 0
    for node in root.rglob("*"):
        info = node.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PublicationError("linked or non-regular publication member")
        relative = node.relative_to(root).as_posix()
        if relative.startswith(".git/") or relative == ".git":
            raise PublicationError("Git metadata is not publishable content")
        if info.st_size > MAX_FILE_BYTES or len(files) >= MAX_FILES:
            raise PublicationError("oversized publication member/inventory")
        data = node.read_bytes()
        if len(data) != info.st_size:
            raise PublicationError("publication input changed during reading")
        total += len(data)
        if total > MAX_TREE_BYTES:
            raise PublicationError("publication input exceeds total size limit")
        files[relative] = data
    return files


def verified_m0_root(files: dict[str, bytes]) -> None:
    if not {"index.html", ".nojekyll", "release-manifest.json"}.issubset(files):
        raise PublicationError("missing accepted M0 Pages root")
    if files[".nojekyll"]:
        raise PublicationError("unexpected root .nojekyll contents")
    manifest = strict_object(files["release-manifest.json"], "existing M0 manifest")
    expected = manifest.get("files_sha256")
    # Keep the M0 manifest strict for *served* root assets. A single
    # reviewed GitHub Actions file may coexist on gh-pages, but only when
    # its content is byte-for-byte the pinned accepted Git blob.
    metadata = set(files) & set(APPROVED_RELEASE_METADATA_BLOBS)
    for name in metadata:
        if git_blob_sha1(files[name]) not in APPROVED_RELEASE_METADATA_BLOBS[name]:
            raise PublicationError("approved release metadata digest mismatch")
    present = {k for k in files if k != "release-manifest.json" and not k.startswith("m1/")} - metadata
    if (manifest.get("status") != "UNPUBLISHED_STATIC_RELEASE_CANDIDATE"
            or not isinstance(expected, dict) or set(expected) != present):
        raise PublicationError("existing M0 manifest/inventory mismatch")
    for name in present:
        if not isinstance(expected[name], str) or not HEX.fullmatch(expected[name]):
            raise PublicationError("invalid existing M0 asset digest")
        if sha(files[name]) != expected[name]:
            raise PublicationError("existing M0 asset changed")


def verified_m1_candidate(files: dict[str, bytes], candidate_pin: str,
                          manifest_pin: str) -> dict:
    if set(files) != RELEASE_FILES or files[".nojekyll"]:
        raise PublicationError("unexpected M1 candidate inventory")
    if not isinstance(candidate_pin, str) or not HEX.fullmatch(candidate_pin):
        raise PublicationError("independent candidate SHA-256 pin required")
    if not isinstance(manifest_pin, str) or not HEX.fullmatch(manifest_pin):
        raise PublicationError("independent manifest SHA-256 pin required")
    raw = files["release-manifest.json"]
    if sha(raw) != manifest_pin:
        raise PublicationError("candidate manifest differs from accepted pin")
    manifest = strict_object(raw, "M1 release manifest")
    expected_keys = {"schema_version", "status", "dataset_id", "method_version",
                     "observation_end", "retrieved_at", "candidate_sha256", "html_sha256",
                     "source_receipt_sha256", "source_seed_sha256", "series",
                     "daily_observations"}
    if set(manifest) != expected_keys or raw != canonical(manifest):
        raise PublicationError("noncanonical or incompatible M1 manifest")
    if (manifest["schema_version"] != SCHEMA or
            manifest["status"] != "DATED_ARCHIVE_NOT_LIVE" or
            type(manifest["series"]) is not int or manifest["series"] != 20 or
            type(manifest["daily_observations"]) is not int or
            manifest["daily_observations"] != 700 or
            not isinstance(manifest["dataset_id"], str) or
            not manifest["dataset_id"] or
            manifest["method_version"] != "v0-empirical-35d"):
        raise PublicationError("M1 source scope or method incompatible")
    for field in ("candidate_sha256", "html_sha256", "source_receipt_sha256", "source_seed_sha256"):
        if not isinstance(manifest[field], str) or not HEX.fullmatch(manifest[field]):
            raise PublicationError("invalid M1 source/asset digest")
    if manifest["candidate_sha256"] != candidate_pin or sha(files["index.html"]) != manifest["html_sha256"]:
        raise PublicationError("M1 candidate/source or HTML digest mismatch")
    try:
        observed = date.fromisoformat(manifest["observation_end"])
        retrieval_text = manifest["retrieved_at"]
        when = datetime.fromisoformat(retrieval_text.replace("Z", "+00:00"))
        # A pinned hash does not make a malformed or temporally impossible
        # release trustworthy. Require exact UTC notation and a retrieval after
        # the complete observation day (not a claim about provider freshness).
        if (manifest["observation_end"] != observed.isoformat() or
                re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", retrieval_text) is None or
                when.utcoffset() != timedelta(0) or
                # Compare dates instead of adding a day: 9999-12-31 must
                # fail closed rather than overflow the supported date range.
                when.date() <= observed):
            raise ValueError("noncanonical or premature retrieval")
    except (TypeError, ValueError, AttributeError) as exc:
        raise PublicationError("invalid M1 observation/retrieval date") from exc
    return manifest


def stage_overlay(current_pages: Path, candidate: Path, destination: Path,
                  expected_candidate_sha256: str,
                  expected_manifest_sha256: str) -> dict:
    """Stage a brand-new Pages tree, keeping the previously accepted one intact."""
    if current_pages.resolve() == candidate.resolve():
        raise PublicationError("current release and M1 candidate cannot be the same tree")
    if destination.exists() or destination.is_symlink():
        raise PublicationError("refusing to overwrite an existing stage")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise PublicationError("stage parent must be an existing real directory")
    original = inventory(current_pages)
    accepted = inventory(candidate)
    verified_m0_root(original)
    proposed = verified_m1_candidate(accepted, expected_candidate_sha256,
                                     expected_manifest_sha256)
    old_m1 = {k[3:]: value for k, value in original.items() if k.startswith("m1/")}
    if old_m1:
        old_manifest_sha = sha(old_m1.get("release-manifest.json", b""))
        previous = verified_m1_candidate(old_m1, old_m1.get("release-manifest.json") and
                                         strict_object(old_m1["release-manifest.json"], "old M1").get("candidate_sha256"),
                                         old_manifest_sha)
        decision = compare_release(previous, proposed)
        if decision == "UNCHANGED_ALREADY_CURRENT":
            raise PublicationError("unchanged M1 release; no new staging necessary")
    else:
        decision = compare_release(None, proposed)
    if len(original) + len(accepted) > MAX_FILES:
        raise PublicationError("overlay inventory exceeds size budget")
    output = {k: v for k, v in original.items() if not k.startswith("m1/")}
    output.update({"m1/" + key: data for key, data in accepted.items()})
    if sum(map(len, output.values())) > MAX_TREE_BYTES:
        raise PublicationError("overlay exceeds total size budget")
    temp = Path(tempfile.mkdtemp(prefix=".dayflare-pages-", dir=destination.parent))
    try:
        for name, data in sorted(output.items()):
            target = temp / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        if inventory(temp) != output:
            raise PublicationError("staged overlay does not match accepted input bytes")
        if inventory(current_pages) != original or inventory(candidate) != accepted:
            raise PublicationError("publication inputs changed while staging")
        _atomic_new_dir(temp, destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return {"status": "STAGED_NOT_DEPLOYED", "decision": decision,
            "m0_files_preserved": len(original) - len(old_m1),
            "m1_candidate_sha256": expected_candidate_sha256,
            "m1_manifest_sha256": expected_manifest_sha256,
            "observation_end": proposed["observation_end"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-pages", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = stage_overlay(args.current_pages, args.candidate, args.destination,
                               args.expected_candidate_sha256,
                               args.expected_manifest_sha256)
    except (PublicationError, OSError) as exc:
        print(f"NOT_DEPLOYED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
