"""Offline integrity gate for a single, bounded Dayflare identity collection.

This verifies structural closure, checksums, receipt/coverage consistency, and
retained raw bodies. It never authenticates Wikimedia transport or publishes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from .m1_identity_panel import (
    PanelError, canonical_bytes, exact_keys, load_panel, require,
    date_value, timestamp, page_ref, TOPIC, SUBJECTS, RELATIONS, HEX256,
)
from .m1_source_verify import MAX_BODY, MAX_TOTAL, verify_sources, verify_endpoint

SCHEMA = "dayflare.identity-bundle.v1"
REPORT_SCHEMA = "dayflare.identity-collection.v2"
ROOT_MEMBERS = frozenset({
    "panel.json", "collection-report.json", "internal-consistency.json",
    "bundle-manifest.json", "raw",
})


def _strict_json(path: Path, *, size_limit: int) -> object:
    require(path.is_file() and not path.is_symlink(), str(path), "missing or linked artifact")
    with path.open("rb") as stream:
        raw = stream.read(size_limit + 1)
    require(0 < len(raw) <= size_limit, str(path), "empty or oversized artifact")

    def no_duplicates(pairs):
        value = {}
        for key, member in pairs:
            require(key not in value, str(path), "duplicate JSON field: " + key)
            value[key] = member
        return value

    def no_constants(value):
        raise PanelError(f"{path}: non-finite JSON constant {value}")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates,
                          parse_constant=no_constants)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PanelError(f"{path}: invalid JSON encoding") from exc


def _canonical_members(root: Path, expected: set[str] | frozenset[str], *, place: str) -> None:
    require(root.is_dir() and not root.is_symlink(), str(root), f"missing or linked {place}")
    actual = {item.name for item in root.iterdir()}
    require(actual == expected, str(root),
            f"unlisted {place} members or missing files: extra={sorted(actual-expected)}, missing={sorted(expected-actual)}")
    for item in root.iterdir():
        require(not item.is_symlink(), str(item), "symlink forbidden in publication")


def _raw_names(panel: dict) -> set[str]:
    return {f"{row['page_ref']['project']}.{row['page_ref']['page_id']}.json"
            for row in panel["pages"]}


def make_manifest(root: Path, panel: dict) -> dict:
    """Create a deterministic file inventory; the manifest itself is excluded."""
    raw_names = _raw_names(panel)
    _canonical_members(root, ROOT_MEMBERS - {"bundle-manifest.json"}, place="bundle")
    _canonical_members(root / "raw", raw_names, place="raw")
    names = ["panel.json", "collection-report.json", "internal-consistency.json"]
    names.extend("raw/" + name for name in sorted(raw_names))
    members = {}
    for name in names:
        path = root / name
        require(path.is_file() and not path.is_symlink(), str(path), "expected regular file")
        bound = MAX_BODY if name.startswith("raw/") else 256 * 1024
        with path.open("rb") as stream:
            data = stream.read(bound + 1)
        require(0 < len(data) <= bound, str(path), "empty or oversized artifact")
        members[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return {"schema_version": SCHEMA, "panel_id": panel["panel_id"], "files": members}


def verify_bundle(root: Path) -> dict:
    """Check the exact published tree; recompute the source-verification result."""
    _canonical_members(root, ROOT_MEMBERS, place="bundle")
    panel = load_panel(root / "panel.json")
    raw_names = _raw_names(panel)
    _canonical_members(root / "raw", raw_names, place="raw")
    supplied_manifest = _strict_json(root / "bundle-manifest.json", size_limit=32 * 1024)
    manifest = exact_keys(supplied_manifest, "$.bundle", {"schema_version", "panel_id", "files"})
    require(manifest["schema_version"] == SCHEMA, "$.bundle.schema_version", "unsupported bundle version")
    require(manifest["panel_id"] == panel["panel_id"], "$.bundle.panel_id", "panel ID mismatch")
    expected_manifest = make_manifest_for_complete(root, panel)
    require(manifest == expected_manifest, "$.bundle.files", "manifest hash, size or inventory mismatch")

    computed_proof = verify_sources(root / "panel.json", root / "raw")
    supplied_proof = _strict_json(root / "internal-consistency.json", size_limit=256 * 1024)
    require(supplied_proof == computed_proof, "$.proof", "internal consistency result differs from raw bodies")
    report = _strict_json(root / "collection-report.json", size_limit=256 * 1024)
    report = exact_keys(report, "$.report", {
        "schema_version", "panel_id", "selected_at", "intended_count",
        "retained_count", "unavailable_count", "transferred_bytes", "decoded_bytes",
        "body_representation", "retained_bytes",
        "requests_attempted", "intended_by_edition_subject", "obtained_by_edition_subject",
        "attempts", "limitations",
    })
    require(report["schema_version"] == REPORT_SCHEMA,
            "$.report", "invalid collection report version")
    date_value(report["selected_at"], "$.report.selected_at")
    require(report["selected_at"] == panel["selection"]["selected_at"],
            "$.report.selected_at", "selection date mismatch")
    intended = panel["selection"]["intended_count"]
    pages = panel["pages"]
    require(report.get("panel_id") == panel["panel_id"] and report.get("intended_count") == intended,
            "$.report", "selection identity/count mismatch")
    require(report.get("retained_count") == len(pages) and report.get("unavailable_count") == intended-len(pages),
            "$.report", "retained/unavailable totals mismatch")
    require(report.get("retained_bytes") == computed_proof["total_retained_response_bytes"],
            "$.report", "retained byte total disagrees with raw bodies")
    transferred = report.get("transferred_bytes")
    require(type(transferred) is int and 0 < transferred <= MAX_TOTAL,
            "$.report", "transferred byte total inconsistent with budget")
    decoded = report.get("decoded_bytes")
    require(type(decoded) is int and computed_proof["total_retained_response_bytes"] <= decoded <= MAX_TOTAL,
            "$.report", "decoded byte total inconsistent with retention/budget")
    require(report["body_representation"] == "decoded-json-entity", "$.report", "unknown source representation")
    require(report.get("obtained_by_edition_subject") == panel["coverage"]["observed_panel_counts_by_edition_subject"],
            "$.report", "obtained coverage mismatch")
    attempts = report.get("attempts")
    require(type(attempts) is list and len(attempts) == intended and report.get("requests_attempted") == intended,
            "$.report", "attempt count disagrees with selection")
    retained = {(p["page_ref"]["project"], p["page_ref"]["page_id"]): p for p in pages}
    seen = set()
    intended_cells = Counter()
    for i, item in enumerate(attempts):
        loc = f"$.report.attempts[{i}]"
        require(type(item) is dict and item.get("status") in {"retained", "unavailable"},
                loc, "invalid attempt status")
        expected = {"page_ref", "topic_id", "subject", "relation", "requested_at",
                    "http_status", "endpoint", "status", "body_sha256", "response_bytes",
                    "wire_bytes", "wire_sha256", "content_encoding"}
        if item["status"] == "unavailable":
            expected.add("reason")
        exact_keys(item, loc, expected)
        key = page_ref(item["page_ref"], loc + ".page_ref")
        require(key not in seen, loc, "duplicate attempt")
        seen.add(key)
        require(type(item["topic_id"]) is str and TOPIC.fullmatch(item["topic_id"]) is not None,
                loc + ".topic_id", "invalid topic ID")
        require(type(item["subject"]) is str and item["subject"] in SUBJECTS,
                loc + ".subject", "invalid subject")
        require(type(item["relation"]) is str and item["relation"] in RELATIONS,
                loc + ".relation", "invalid relation")
        intended_cells[(key[0], item["subject"])] += 1
        observed_at = timestamp(item["requested_at"], loc + ".requested_at")
        require(observed_at[:10] >= report["selected_at"], loc + ".requested_at",
                "retrieval predates curated selection")
        verify_endpoint(item["endpoint"], *key)
        require(item["http_status"] == 200 and type(item["http_status"]) is int,
                loc, "unexpected HTTP status")
        require(type(item["response_bytes"]) is int and 1 <= item["response_bytes"] <= MAX_BODY,
                loc, "invalid attempt body size")
        require(type(item["body_sha256"]) is str and HEX256.fullmatch(item["body_sha256"]) is not None,
                loc, "invalid attempt SHA-256")
        require(type(item["wire_bytes"]) is int and 1 <= item["wire_bytes"] <= MAX_BODY
                and item["content_encoding"] in {"identity", "gzip"}
                and type(item["wire_sha256"]) is str and HEX256.fullmatch(item["wire_sha256"]) is not None,
                loc, "invalid wire representation metadata")
        if item["content_encoding"] == "identity":
            require(item["wire_bytes"] == item["response_bytes"] and item["wire_sha256"] == item["body_sha256"],
                    loc, "identity wire/entity mismatch")
        if item["status"] == "retained":
            require(key in retained, loc, "retained attempt has no panel page")
            page = retained[key]
            require(all(item[k] == page[k] for k in ("topic_id", "subject", "relation")),
                    loc, "retained attempt scope disagrees with panel page")
            source = page["source"]
            require(all(item[k] == source[v] for k, v in (
                ("endpoint", "endpoint"), ("requested_at", "requested_at"),
                ("body_sha256", "body_sha256"), ("response_bytes", "response_bytes"))),
                loc, "retained attempt differs from page receipt")
        else:
            require(key not in retained and item["reason"] == "invalid_or_missing_identity",
                    loc, "unavailable attempt inconsistent with panel or reason")
    computed_intended = {}
    for (edition, subject), count in sorted(intended_cells.items()):
        computed_intended.setdefault(edition, {})[subject] = count
    require(report["intended_by_edition_subject"] == computed_intended,
            "$.report.intended_by_edition_subject", "intended coverage disagrees with attempts")
    require(sum(item.get("status") == "retained" for item in attempts) == len(pages),
            "$.report", "reported retained attempts mismatch")
    require(all(type(item.get("response_bytes")) is int and item["response_bytes"] > 0
                for item in attempts), "$.report", "attempt bytes missing or invalid")
    require(sum(item["response_bytes"] for item in attempts) == decoded,
            "$.report", "decoded bytes disagree with attempts")
    require(sum(item["wire_bytes"] for item in attempts) == transferred,
            "$.report", "transferred bytes disagree with attempts")
    return {"schema_version": SCHEMA, "panel_id": panel["panel_id"],
            "verified_pages": len(pages), "observed_bytes": computed_proof["total_retained_response_bytes"],
            "manifest_sha256": hashlib.sha256(canonical_bytes(manifest)).hexdigest(),
            "result": "bundle_structurally_and_internally_consistent",
            "limitations": ["No authentication of upstream network origin, ownership of data, or pageview history."]}


def make_manifest_for_complete(root: Path, panel: dict) -> dict:
    """Compute checksums of all mandatory files when the manifest already exists."""
    members = {}
    names = ["panel.json", "collection-report.json", "internal-consistency.json"]
    names.extend("raw/" + name for name in sorted(_raw_names(panel)))
    for name in names:
        path = root / name
        bound = MAX_BODY if name.startswith("raw/") else 256 * 1024
        with path.open("rb") as stream:
            value = stream.read(bound + 1)
        require(0 < len(value) <= bound, str(path), "empty or oversized artifact")
        members[name] = {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    return {"schema_version": SCHEMA, "panel_id": panel["panel_id"], "files": members}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_bundle(args.bundle)
    except (PanelError, OSError, ValueError) as exc:
        parser.exit(2, f"BUNDLE_INVALID: {exc}\n")
    sys.stdout.buffer.write(canonical_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
