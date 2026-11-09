"""Compare an accepted M1 release to a verified new offline source candidate.

This is a reviewer-facing decision receipt, NOT source authentication, acceptance,
publication, or a report of changes in article traffic without previous raw data.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
import sys

from .m1_publication_gate import PublicationError, canonical, compare_release, strict_object
from .rolling_window_gate import WindowError, stamp, validate

SCHEMA = "dayflare.m1.refresh-review.v1"
STATUS = "REVIEW_REQUIRED_NOT_DEPLOYED"


def _read(path: Path, label: str, limit: int = 2 * 1024 * 1024) -> tuple[bytes, dict]:
    if path.is_symlink() or not path.is_file():
        raise PublicationError(f"{label}: missing or linked input")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise PublicationError(f"{label}: empty or oversized input")
    doc = strict_object(raw, label)
    if raw != canonical(doc):
        raise PublicationError(f"{label}: noncanonical source JSON")
    return raw, doc


def summarize(previous: dict, proposed: dict, candidate: dict, receipt: dict) -> dict:
    """Describe only provable release/date changes, never inferred pageview deltas."""
    try:
        validate(candidate, now=stamp(candidate["retrieved_at"]))
    except (WindowError, KeyError, TypeError, ValueError) as exc:
        raise PublicationError("invalid proposed rolling candidate") from exc
    decision = compare_release(previous, proposed)
    if decision == "UNCHANGED_ALREADY_CURRENT":
        raise PublicationError("no release revision change; no review delta to publish")
    if (proposed["candidate_sha256"] != sha256(canonical(candidate)).hexdigest()
            or proposed["dataset_id"] != candidate["dataset_id"]
            or proposed["method_version"] != candidate["method_version"]
            or proposed["observation_end"] != candidate["observation_end"]
            or proposed["retrieved_at"] != candidate["retrieved_at"]
            or proposed["series"] != len(candidate["series"])
            or proposed["daily_observations"] != sum(len(s["daily"]) for s in candidate["series"])):
        raise PublicationError("release manifest does not bind proposed source candidate")
    required_receipt = {"schema_version", "seed_sha256", "candidate_sha256", "retrieved_at",
                        "observation_start", "observation_end", "requests_attempted",
                        "total_wire_bytes", "total_decoded_bytes", "sources",
                        "provenance_status", "publication_status"}
    if (set(receipt) != required_receipt
            or receipt["schema_version"] != "dayflare.rolling-source-receipt.v1"
            or receipt["provenance_status"] != "runtime_reported_transport_not_independently_authenticated"
            or receipt["publication_status"] != "LOCAL_EVIDENCE_ONLY_NOT_PUBLISHED"
            or receipt["candidate_sha256"] != proposed["candidate_sha256"]
            or receipt["seed_sha256"] != proposed["source_seed_sha256"]
            or receipt["retrieved_at"] != proposed["retrieved_at"]
            or receipt["observation_end"] != proposed["observation_end"]
            or receipt["observation_start"] != (date.fromisoformat(proposed["observation_end"])
                                                     - timedelta(days=34)).isoformat()
            or type(receipt["requests_attempted"]) is not int
            or receipt["requests_attempted"] != len(candidate["series"])
            or type(receipt["sources"]) is not list
            or len(receipt["sources"]) != len(candidate["series"])):
        raise PublicationError("source receipt or provenance is incompatible with proposed release")
    old = date.fromisoformat(previous["observation_end"])
    new = date.fromisoformat(proposed["observation_end"])
    return {
        "schema_version": SCHEMA,
        "status": STATUS,
        "decision": decision,
        "previous_dataset_id": previous["dataset_id"],
        "proposed_dataset_id": proposed["dataset_id"],
        "previous_observation_end": old.isoformat(),
        "proposed_observation_end": new.isoformat(),
        "new_completed_utc_days": (new - old).days,
        "previous_retrieved_at": previous["retrieved_at"],
        "proposed_retrieved_at": proposed["retrieved_at"],
        "method_version": proposed["method_version"],
        "source_seed_sha256": proposed["source_seed_sha256"],
        "previous_candidate_sha256": previous["candidate_sha256"],
        "proposed_candidate_sha256": proposed["candidate_sha256"],
        "source_receipt_sha256": proposed["source_receipt_sha256"],
        "series": proposed["series"],
        "daily_observations": proposed["daily_observations"],
        "traffic_delta": "NOT_COMPUTED_PREVIOUS_RAW_SERIES_NOT_AVAILABLE",
        "source_authentication": "RUNTIME_REPORTED_NOT_INDEPENDENTLY_VERIFIED",
    }


def build(previous: Path, proposed: Path, candidate: Path, receipt: Path, out: Path) -> dict:
    _, old = _read(previous, "previous manifest")
    _, new = _read(proposed, "proposed manifest")
    _, source = _read(candidate, "candidate")
    receipt_bytes, reported = _read(receipt, "source receipt")
    if sha256(receipt_bytes).hexdigest() != new.get("source_receipt_sha256"):
        raise PublicationError("release manifest/source receipt SHA-256 mismatch")
    result = summarize(old, new, source, reported)
    if out.is_symlink() or out.exists() or not out.parent.is_dir():
        raise PublicationError("review destination already exists or parent is missing")
    with out.open("xb") as target:
        target.write(canonical(result))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--proposed", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build(args.previous, args.proposed, args.candidate, args.receipt, args.output)
    except (PublicationError, OSError) as exc:
        print(f"NO_PUBLICATION: {exc}", file=sys.stderr)
        return 2
    print(f"{result['decision']}: {result['new_completed_utc_days']} new completed UTC days; REVIEW REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
