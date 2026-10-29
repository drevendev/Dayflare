"""Fail-closed offline acceptance of the exact *branch* M1 HTML release.

This checks source-branch bytes, not Pages HTTP/deployment, and does not
independently authenticate upstream Wikimedia responses. Keep the accepted
manifest digest pinned outside the candidate under test (e.g. in reviewed CI).
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re

EXPECTED_KEYS = frozenset({
    "schema_version", "dataset_id", "method_version", "observation_end",
    "retrieved_at", "candidate_sha256", "html_sha256", "source_receipt_sha256",
    "source_seed_sha256", "series", "daily_observations", "status",
})
SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_HTML = 512 * 1024
MAX_MANIFEST = 16 * 1024


class ReleaseError(ValueError):
    """The publication branch cannot be accepted as a valid M1 candidate."""


class ReleaseHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards: list[str] = []
        self.details: list[str] = []
        self.comparison: list[str] = []
        self.week_ranges: list[tuple[str, str]] = []
        self.daily_rows = 0
        self.elements: dict[str, dict] = {}
        self.table: str | None = None
        self.in_body = False
        self.table_stack: list[str | None] = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        identifier = data.get("id")
        if identifier:
            if identifier in self.elements:
                raise ReleaseError(f"duplicate HTML id: {identifier}")
            self.elements[identifier] = data
        if tag == "div" and "card" in (data.get("class") or "").split():
            self.cards.append(data.get("data-series") or "")
            if data.get("data-edition") not in ("en.wikipedia", "ru.wikipedia"):
                raise ReleaseError("card lacks supported edition")
            if data.get("data-subject") not in ("books", "culture", "games", "science", "sport"):
                raise ReleaseError("card lacks supported subject")
        if tag == "article":
            self.details.append(identifier or "")
        if tag == "table":
            self.table_stack.append(self.table)
            self.table = identifier or "detail"
        if tag == "tbody":
            self.in_body = True
        if tag == "tr" and self.in_body:
            if self.table == "compare-table":
                self.comparison.append(data.get("data-series") or "")
            elif self.table == "detail":
                self.daily_rows += 1
        if tag == "th" and "data-week-start" in data:
            self.week_ranges.append((data["data-week-start"], data.get("data-week-end") or ""))

    def handle_endtag(self, tag):
        if tag == "tbody":
            self.in_body = False
        if tag == "table":
            self.table = self.table_stack.pop() if self.table_stack else None


def _unique(rows: list[str], count: int, label: str) -> set[str]:
    if len(rows) != count or not all(rows) or len(set(rows)) != count:
        raise ReleaseError(f"{label}: missing or duplicate entries (expected {count})")
    return set(rows)


def _json_unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ReleaseError(f"duplicate manifest field: {key}")
        obj[key] = value
    return obj


def verify(site_root: Path, accepted_manifest_sha256: str) -> dict:
    if not isinstance(accepted_manifest_sha256, str) or not SHA.fullmatch(accepted_manifest_sha256):
        raise ReleaseError("accepted manifest SHA-256 is required from independent review")
    root = site_root / "m1"
    manifest_path = root / "release-manifest.json"
    html_path = root / "index.html"
    for path, cap in ((manifest_path, MAX_MANIFEST), (html_path, MAX_HTML)):
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= cap:
            raise ReleaseError(f"missing, symlinked, empty or oversized release member: {path.name}")
    raw = manifest_path.read_bytes()
    if sha256(raw).hexdigest() != accepted_manifest_sha256:
        raise ReleaseError("branch manifest differs from the independently accepted SHA-256")
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_json_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(ReleaseError("nonfinite JSON")))
    except (UnicodeError, ValueError) as error:
        raise ReleaseError("invalid release manifest JSON") from error
    if type(manifest) is not dict or set(manifest) != EXPECTED_KEYS:
        raise ReleaseError("unexpected M1 release manifest schema")
    if (manifest["schema_version"] != "dayflare.m1.static-snapshot.v1" or
        manifest["method_version"] != "v0-empirical-35d" or
        manifest["status"] != "DATED_ARCHIVE_NOT_LIVE" or
        type(manifest["series"]) is not int or manifest["series"] != 20 or
        type(manifest["daily_observations"]) is not int or manifest["daily_observations"] != 700):
        raise ReleaseError("unexpected method, status or bounded coverage")
    for field in ("html_sha256", "candidate_sha256", "source_receipt_sha256", "source_seed_sha256"):
        if type(manifest[field]) is not str or not SHA.fullmatch(manifest[field]):
            raise ReleaseError(f"invalid {field}")
    if (type(manifest["dataset_id"]) is not str or
        not re.fullmatch(r"run-\d{8}-\d{6}-[0-9a-f]{12}", manifest["dataset_id"])):
        raise ReleaseError("invalid dataset ID")
    try:
        end = date.fromisoformat(manifest["observation_end"])
        retrieved = datetime.fromisoformat(manifest["retrieved_at"].replace("Z", "+00:00"))
        if retrieved.utcoffset() != timedelta(0) or end > retrieved.date():
            raise ValueError("observation exceeds retrieval time or non-UTC retrieval")
    except (TypeError, AttributeError, ValueError) as error:
        raise ReleaseError("invalid UTC evidence dates") from error
    html = html_path.read_bytes()
    if sha256(html).hexdigest() != manifest["html_sha256"]:
        raise ReleaseError("branch HTML bytes do not match accepted manifest")
    try:
        decoded = html.decode("utf-8")
    except UnicodeError as error:
        raise ReleaseError("invalid UTF-8 HTML") from error
    parser = ReleaseHTML()
    parser.feed(decoded)
    parser.close()
    cards = _unique(parser.cards, 20, "cards")
    _unique(parser.details, 20, "detail articles")
    if set(parser.details) != cards:
        raise ReleaseError("cards and stable-ID detail destinations differ")
    if _unique(parser.comparison, 20, "comparison rows") != cards:
        raise ReleaseError("comparison does not cover exactly the selected cards")
    if parser.daily_rows != 700:
        raise ReleaseError(f"expected 700 exact daily rows, found {parser.daily_rows}")
    for element in ("main", "overview", "compare-table", "atlas-filters", "atlas-query",
                    "atlas-edition", "atlas-subject", "atlas-empty", "compare-empty",
                    "compare-csv", "compare-csv-status", "atlas-filter-warning", "share-restore"):
        if element not in parser.elements:
            raise ReleaseError(f"missing visitor element: {element}")
    share = parser.elements["share-restore"]
    if (share.get("data-dataset") != manifest["candidate_sha256"] or
        share.get("data-method") != manifest["method_version"] or
        share.get("data-end") != manifest["observation_end"]):
        raise ReleaseError("share restoration not bound to release manifest")
    weeks = parser.week_ranges
    if len(weeks) != 5:
        raise ReleaseError("must include exactly five dated complete weeks")
    try:
        spans = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in weeks]
    except ValueError as error:
        raise ReleaseError("invalid weekly header dates") from error
    if (spans[-1][1] != end or any(b-a != timedelta(days=6) for a, b in spans) or
        any(spans[i+1][0] != spans[i][1] + timedelta(days=1) for i in range(4))):
        raise ReleaseError("incomplete or nonconsecutive UTC weekly windows")
    if ("DATED SOURCE EVIDENCE" not in decoded or "not</strong> a live feed" not in decoded or
        manifest["retrieved_at"] not in decoded or manifest["observation_end"] not in decoded):
        raise ReleaseError("stale/source limitations or evidence dates missing from UI")
    return {"status": "BRANCH_BYTES_VERIFIED_NOT_DEPLOYED", "manifest_sha256": accepted_manifest_sha256,
            "html_sha256": manifest["html_sha256"], "dataset_id": manifest["dataset_id"],
            "observation_end": manifest["observation_end"], "retrieved_at": manifest["retrieved_at"],
            "cards": len(cards), "daily_rows": parser.daily_rows, "comparison_rows": len(parser.comparison)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site-root", required=True, type=Path)
    ap.add_argument("--accepted-manifest-sha256", required=True)
    args = ap.parse_args()
    print(json.dumps(verify(args.site_root, args.accepted_manifest_sha256), sort_keys=True))


if __name__ == "__main__":
    main()
