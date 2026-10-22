"""Fail-closed, offline check of retained decoded MediaWiki JSON entities.

This authenticates **internal agreement of supplied bytes and receipts**, not their
transport origin, licence, or historical accuracy. No network or filesystem writes.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

from .m1_identity_panel import (
    MAX_PAGES, PanelError, canonical_bytes, load_panel, require,
)

REPORT_SCHEMA = "dayflare.source-verification.v1"
MAX_BODY = 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
REQUIRED_QUERY = {
    "action": "query", "format": "json", "formatversion": "2",
    "prop": "info|pageprops", "ppprop": "wikibase_item",
}


def verify_endpoint(url: str, project: str, page_id: int) -> None:
    """Require a single-page, non-redirect-following, canonical Action API query."""
    parsed = urlsplit(url)
    require(
        parsed.scheme == "https"
        and parsed.hostname == project + ".org"
        and parsed.port in (None, 443)
        and not parsed.username and not parsed.password and not parsed.fragment
        and parsed.path == "/w/api.php",
        "$.source.endpoint", "expected exact Wikipedia Action API origin and path",
    )
    try:
        params = parse_qs(parsed.query, strict_parsing=True, keep_blank_values=True)
    except ValueError as exc:
        raise PanelError("$.source.endpoint: invalid query") from exc
    expected = {**REQUIRED_QUERY, "pageids": str(page_id)}
    require(set(params) == set(expected), "$.source.endpoint", "unexpected/missing query parameter, or redirects requested")
    for key, value in expected.items():
        require(params[key] == [value], "$.source.endpoint", f"unexpected {key}")


def parse_response(raw: bytes, project: str, page_id: int, expected_title: str, expected_qid: str | None) -> None:
    def no_duplicates(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise PanelError(f"$.raw: duplicate JSON key: {key}")
            obj[key] = value
        return obj

    def reject_constant(token):
        raise PanelError(f"$.raw: non-finite JSON constant {token}")

    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PanelError("$.raw: invalid UTF-8 JSON") from exc
    require(type(data) is dict, "$.raw", "expected root object")
    require(not any(k in data for k in ("error", "errors")), "$.raw", "API error response")
    query = data.get("query")
    require(type(query) is dict, "$.raw.query", "expected query object")
    require("redirects" not in query and "normalized" not in query, "$.raw.query", "unexpected title redirect/normalization")
    pages = query.get("pages")
    require(type(pages) is list and len(pages) == 1, "$.raw.query.pages", "expected exactly one page")
    page = pages[0]
    require(type(page) is dict, "$.raw.query.pages[0]", "expected page object")
    require(type(page.get("pageid")) is int and page["pageid"] == page_id,
            "$.raw.query.pages[0].pageid", "missing, substituted or mismatched page id")
    require(page.get("ns") == 0 and type(page.get("ns")) is int,
            "$.raw.query.pages[0].ns", "expected article namespace 0")
    require("missing" not in page and "invalid" not in page and "redirect" not in page,
            "$.raw.query.pages[0]", "missing/redirected page is not a verified current identity")
    require(type(page.get("title")) is str and page["title"] == expected_title,
            "$.raw.query.pages[0].title", "current title disagrees with dated observation")
    props = page.get("pageprops", {})
    require(type(props) is dict, "$.raw.query.pages[0].pageprops", "invalid pageprops")
    actual_qid = props.get("wikibase_item")
    require(actual_qid is None or type(actual_qid) is str,
            "$.raw.query.pages[0].pageprops.wikibase_item", "invalid item")
    require(actual_qid == expected_qid, "$.raw.query.pages[0].pageprops.wikibase_item",
            "observed QID disagrees with retained raw body")


def verify_sources(panel_path: Path, raw_root: Path) -> dict:
    panel = load_panel(panel_path)
    require(panel["selection"]["evidence_kind"] == "reported_retrieval", "$.selection.evidence_kind",
            "requires reported_retrieval with receipts, not a synthetic panel")
    require(raw_root.is_dir() and not raw_root.is_symlink(), str(raw_root), "raw-body directory missing or linked")
    entries = panel["pages"]
    expected_names = {f"{entry['page_ref']['project']}.{entry['page_ref']['page_id']}.json" for entry in entries}
    for expected in expected_names:
        member = raw_root / expected
        require(member.is_file() and not member.is_symlink(), str(member), "missing/linked raw body")
    actual_names = {member.name for member in raw_root.iterdir()}
    require(actual_names == expected_names, str(raw_root),
            f"unexpected/missing raw members: extra={sorted(actual_names - expected_names)}, missing={sorted(expected_names - actual_names)}")
    require(0 < len(entries) <= MAX_PAGES, "$.pages", "no retained sources to verify")
    report = []
    total = 0
    for entry in entries:
        project, pid = entry["page_ref"]["project"], entry["page_ref"]["page_id"]
        receipt = entry["source"]
        verify_endpoint(receipt["endpoint"], project, pid)
        requested_at = datetime.fromisoformat(receipt["requested_at"].replace("Z", "+00:00"))
        observed = entry["titles"][-1]
        require(observed["date"] == requested_at.date().isoformat(),
                f"{project}:{pid}.titles", "current title observation must match UTC retrieval date")
        raw_path = raw_root / f"{project}.{pid}.json"
        require(raw_path.is_file() and not raw_path.is_symlink(), str(raw_path), "missing/linked raw body")
        with raw_path.open("rb") as fp:
            body = fp.read(MAX_BODY + 1)
        require(0 < len(body) <= MAX_BODY, str(raw_path), "missing/oversized raw response")
        total += len(body)
        require(total <= MAX_TOTAL, str(raw_root), "combined response budget exceeded")
        require(len(body) == receipt["response_bytes"], str(raw_path), "receipt byte size mismatch")
        digest = hashlib.sha256(body).hexdigest()
        require(digest == receipt["body_sha256"], str(raw_path), "raw body SHA-256 mismatch")
        parse_response(body, project, pid, observed["title"], entry["wikidata"]["observed_qid"])
        report.append({
            "page_ref": entry["page_ref"],
            "raw_body_sha256": digest,
            "response_bytes": len(body),
            "requested_at": receipt["requested_at"],
            "observed_qid_verified_against_body": True,
            "current_title_verified_against_body": True,
            "page_id_verified_against_body": True,
        })
    return {
        "schema_version": REPORT_SCHEMA,
        "panel_id": panel["panel_id"],
        "panel_sha256": hashlib.sha256(canonical_bytes(panel)).hexdigest(),
        "result": "all_retained_bodies_internally_consistent",
        "verified_page_count": len(report),
        "total_retained_response_bytes": total,
        "pages": sorted(report, key=lambda x:(x["page_ref"]["project"], x["page_ref"]["page_id"])),
        "limitations": [
            "Source hashes bind decoded JSON entities, not compressed wire representations.",
            "Supplied bytes and receipts can be fabricated; network origin is NOT authenticated.",
            "Latest titles/QIDs only: move/delete history and resolved QID redirects NOT verified.",
            "This is not live collection, pageview evidence, licensing review or representative coverage.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel", type=Path, help="panel with reported_retrieval receipts")
    parser.add_argument("raw_dir", type=Path, help="retained <project>.<page_id>.json bodies")
    args = parser.parse_args(argv)
    try:
        output = canonical_bytes(verify_sources(args.panel, args.raw_dir))
    except (PanelError, OSError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(output)
    print("SHA256 " + hashlib.sha256(output).hexdigest(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
