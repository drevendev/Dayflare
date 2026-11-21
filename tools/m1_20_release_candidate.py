"""Stage a Nov 18 real-source M1 release-format candidate; NEVER deploy it.

This is deliberately distinct from the local-only preview. It replays the
Git-pinned original responses using the existing preview builder, then applies
the separately established strict dated-publication presentation/revision
gate. Review/permission checks still precede any later public release.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .m1_20_local_atlas import build as build_local
from .m1_20_retained_source import CANDIDATE_SHA256, SEED_SHA256, pinned_members
from .m1_pages_overlay import verified_m1_candidate
from .m1_publication_gate import (
    PublicationError, SCHEMA, canonical, compare_release, digest, public_copy,
    require_current_release, strict_object,
)
from .rolling_pageview_source import _atomic_new_dir


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
    args = parser.parse_args(argv)
    try:
        result = build(args.destination, args.previous_manifest)
    except (ValueError, OSError) as exc:
        print(f"NOT_DEPLOYED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
