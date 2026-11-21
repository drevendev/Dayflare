"""Unpack the independently pinned, historical 2026-11-21 EN/RU source evidence offline."""
from __future__ import annotations
import argparse
from hashlib import sha256
from io import BytesIO
import json
import lzma
from pathlib import Path
import re
import tarfile
from tempfile import TemporaryDirectory

from .rolling_pageview_source import _atomic_new_dir, verify_bundle

CAPSULE = Path(__file__).resolve().parents[1] / "evidence/m1-20-20261121/source.tar.xz"
CAPSULE_SHA256 = "682981f40b272749441c5164e650eb27136b9c1a4c583fddf7338793d493146d"
CANDIDATE_SHA256 = "33f01e00f00de72c58b2794e00b041011c940e8c69afee0870472877929090e9"
SEED_SHA256 = "a32c03ef7daa8c21fe6a75b283281ed4972bf1ab0920b767581fe496a62c81d8"
RAW = re.compile(r"raw/(?:en|ru)\.wikipedia\.[1-9][0-9]*\.json\Z")
META = {"candidate.json", "seeds.json", "source-receipt.json"}

class CapsuleError(ValueError):
    pass

def pinned_members(raw: bytes | None = None) -> dict[str, bytes]:
    if raw is None:
        raw = CAPSULE.read_bytes()
    if len(raw) != 9272 or sha256(raw).hexdigest() != CAPSULE_SHA256:
        raise CapsuleError("source archive pin mismatch")
    try:
        tar_bytes = lzma.decompress(raw, format=lzma.FORMAT_XZ, memlimit=16 * 1024 * 1024)
    except lzma.LZMAError as exc:
        raise CapsuleError("corrupt source archive") from exc
    if len(tar_bytes) != 194560:
        raise CapsuleError("unexpected decompressed size")
    out = {}
    with tarfile.open(fileobj=BytesIO(tar_bytes), mode="r:") as tar:
        members = tar.getmembers()
        if len(members) != 23:
            raise CapsuleError("unexpected source inventory")
        for member in members:
            name = member.name
            if (not member.isfile() or name in out or not
                    (name in META or RAW.fullmatch(name)) or
                    not 0 < member.size <= 1024 * 1024):
                raise CapsuleError("unsafe source member")
            stream = tar.extractfile(member)
            if stream is None:
                raise CapsuleError("missing source body")
            body = stream.read(1024 * 1024 + 1)
            if len(body) != member.size:
                raise CapsuleError("incomplete source member")
            out[name] = body
    if not META.issubset(out) or len([n for n in out if RAW.fullmatch(n)]) != 20:
        raise CapsuleError("missing source receipt or raw response")
    return out

def unpack(target: Path) -> dict:
    target = Path(target)
    if (not target.parent.is_dir() or target.parent.is_symlink() or
            target.exists() or target.is_symlink()):
        raise CapsuleError("output must be absent inside an existing real directory")
    files = pinned_members()
    with TemporaryDirectory(prefix=".dayflare-source-", dir=target.parent) as tmp:
        root = Path(tmp) / "verified"
        (root / "raw").mkdir(parents=True)
        for name, body in files.items():
            (root / name).write_bytes(body)
        proof = verify_bundle(root)
        candidate = json.loads(files["candidate.json"])
        if (proof["candidate_sha256"] != CANDIDATE_SHA256 or
                proof["seed_sha256"] != SEED_SHA256 or
                proof["series"] != 20 or proof["observations"] != 700 or
                proof["provenance_status"] != "runtime_reported_transport_not_independently_authenticated" or
                proof["publication_status"] != "NOT_PUBLISHED" or
                candidate["observation_end"] != "2026-11-18" or
                candidate["retrieved_at"] != "2026-11-21T14:43:17Z"):
            raise CapsuleError("source evidence/receipt mismatch")
        _atomic_new_dir(root, target)
    return proof

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        report = unpack(args.destination)
    except (CapsuleError, OSError, ValueError, tarfile.TarError) as exc:
        parser.exit(2, f"UNPUBLISHED: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
