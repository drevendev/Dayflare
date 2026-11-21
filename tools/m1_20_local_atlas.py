"""Build the dated, genuinely measured Nov 18 EN/RU atlas in one offline command.

Replays Git-retained original response bodies through the source verifier and
existing accessible HTML renderer. Never fetches data, overwrites a preview,
updates gh-pages or claims that the snapshot is live or representative.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .m1_20_retained_source import (
    CANDIDATE_SHA256, SEED_SHA256, unpack,
)
from .rolling_snapshot_preview import export_verified_preview
from .rolling_window_gate import stamp

RETRIEVED_AT = "2026-11-21T14:43:17Z"
OBSERVATION_END = "2026-11-18"
PROVENANCE = "runtime_reported_transport_not_independently_authenticated"


def build(destination: Path) -> dict:
    """Export verified original observations to a new, local-only HTML directory."""
    destination = Path(destination)
    parent = destination.parent
    if (not parent.is_dir() or parent.is_symlink() or
            destination.exists() or destination.is_symlink()):
        raise ValueError("preview must be a new path inside an existing real directory")

    with TemporaryDirectory(prefix=".dayflare-retained-preview-", dir=parent) as scratch:
        evidence = Path(scratch) / "source"
        proof = unpack(evidence)
        if (proof["candidate_sha256"] != CANDIDATE_SHA256 or
                proof["seed_sha256"] != SEED_SHA256 or
                proof["series"] != 20 or proof["observations"] != 700 or
                proof["provenance_status"] != PROVENANCE or
                proof["publication_status"] != "NOT_PUBLISHED"):
            raise ValueError("retained 20-title evidence does not match the pinned source")
        # The historical retrieval instant, not the visitor's clock, defines the gate.
        return export_verified_preview(evidence, destination,
                                       now=stamp(RETRIEVED_AT))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path,
                        help="new directory for index.html and preview-manifest.json")
    args = parser.parse_args(argv)
    try:
        manifest = build(args.destination)
    except (OSError, ValueError) as exc:
        print(f"LOCAL_ATLAS_REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
