"""Offline, deterministic D03 identity-panel validator (no network/publishing).

The validator checks *reported* provenance metadata but does not authenticate Wikimedia
responses or assert that any page/ref/QID actually exists. Only independently retrieved
source evidence can upgrade an output from synthetic to a measured panel.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

SCHEMA = "dayflare.identity-panel.v1"
MAX_BYTES = 256 * 1024
MAX_PAGES = 100
MAX_SAFE_ID = (1 << 53) - 1
PROJECTS = frozenset({"en.wikipedia", "ru.wikipedia"})
SUBJECTS = frozenset({"culture", "books", "games", "science", "sport", "other"})
RELATIONS = frozenset({"equivalent", "broader", "narrower", "related", "ambiguous", "missing"})
MAPPING_STATES = frozenset({"missing", "observed", "resolved", "ambiguous"})
CONTINUITIES = frozenset({"confirmed", "ambiguous", "discontinuous"})
QID = re.compile(r"Q[1-9][0-9]*\Z")
TOPIC = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
HEX256 = re.compile(r"[a-f0-9]{64}\Z")


class PanelError(ValueError):
    """The input panel cannot be safely interpreted under the v1 contract."""


def require(test: bool, path: str, why: str) -> None:
    if not test:
        raise PanelError(f"{path}: {why}")


def exact_keys(obj: object, path: str, required: set[str], optional: set[str] = frozenset()) -> dict:
    require(type(obj) is dict, path, "expected an object")
    require(required <= obj.keys(), path, f"missing fields {sorted(required - obj.keys())}")
    require(obj.keys() <= required | optional, path, f"unrecognized fields {sorted(obj.keys() - required - optional)}")
    return obj


def date_value(value: object, path: str) -> str:
    require(type(value) is str, path, "expected ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise PanelError(f"{path}: invalid date") from exc
    require(parsed.isoformat() == value, path, "date must be canonical YYYY-MM-DD")
    return value


def timestamp(value: object, path: str) -> str:
    require(type(value) is str and len(value) <= 40, path, "expected bounded timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PanelError(f"{path}: invalid timestamp") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, path, "timezone required")
    require(parsed.utcoffset().total_seconds() == 0, path, "UTC timestamp required")
    require(parsed <= datetime.now(timezone.utc), path, "future retrieval timestamp")
    return value


def bounded_text(value: object, path: str, limit: int) -> str:
    require(type(value) is str and 0 < len(value) <= limit and value == value.strip(), path, "invalid or unbounded text")
    require(not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value), path, "control or surrogate character")
    return value


def source_url(value: object, path: str) -> str:
    bounded_text(value, path, 1500)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise PanelError(f"{path}: invalid source URL") from exc
    require(parsed.scheme == "https" and parsed.hostname is not None and not parsed.username and not parsed.password, path, "HTTPS source URL required")
    host = parsed.hostname.lower()
    allowed = ("wikipedia.org", "wikimedia.org", "wikidata.org", "mediawiki.org")
    require(any(host == domain or host.endswith("." + domain) for domain in allowed), path, "source must be Wikimedia/MediaWiki")
    require(port in (None, 443), path, "nonstandard port")
    return value


def page_ref(obj: object, path: str) -> tuple[str, int]:
    exact_keys(obj, path, {"project", "page_id"})
    require(type(obj["project"]) is str and obj["project"] in PROJECTS, path + ".project", "unsupported edition")
    num = obj["page_id"]
    require(type(num) is int and 0 < num <= MAX_SAFE_ID, path + ".page_id", "positive JS-safe integer required")
    return (obj["project"], num)


def qid(value: object, path: str) -> None:
    require(value is None or (type(value) is str and len(value) <= 32 and QID.fullmatch(value)), path, "QID or null required")


def validate_panel(raw: object) -> dict:
    panel = exact_keys(raw, "$", {"schema_version", "panel_id", "selection", "pages"})
    require(panel["schema_version"] == SCHEMA, "$.schema_version", "unsupported schema")
    bounded_text(panel["panel_id"], "$.panel_id", 120)
    require(TOPIC.fullmatch(panel["panel_id"]) is not None, "$.panel_id", "stable slug required")
    selection = exact_keys(panel["selection"], "$.selection", {"method", "selected_at", "intended_count", "evidence_kind"})
    require(selection["method"] == "curated", "$.selection.method", "only explicitly selected panels supported")
    date_value(selection["selected_at"], "$.selection.selected_at")
    require(selection["selected_at"] <= date.today().isoformat(), "$.selection.selected_at", "future selection date")
    require(type(selection["evidence_kind"]) is str and selection["evidence_kind"] in {"synthetic", "reported_retrieval"}, "$.selection.evidence_kind", "unknown evidence kind")
    count = selection["intended_count"]
    require(type(count) is int and 1 <= count <= MAX_PAGES, "$.selection.intended_count", "invalid planned count")
    pages = panel["pages"]
    require(type(pages) is list and len(pages) <= MAX_PAGES, "$.pages", "bounded page list required")
    require(len(pages) <= count, "$.pages", "obtained count exceeds intended count")
    seen = set()
    topic_projects: dict[str, set[str]] = defaultdict(set)
    qid_projects: dict[tuple[str, str], list[int]] = defaultdict(list)
    redirects = []
    normalized_pages = []
    for i, entry in enumerate(pages):
        p = f"$.pages[{i}]"
        exact_keys(entry, p, {"page_ref", "topic_id", "subject", "relation", "titles", "events", "continuity", "redirect_to", "wikidata", "source"})
        ref = page_ref(entry["page_ref"], p + ".page_ref")
        require(ref not in seen, p + ".page_ref", "duplicate project/page_id identity")
        seen.add(ref)
        tid = bounded_text(entry["topic_id"], p + ".topic_id", 120)
        require(TOPIC.fullmatch(tid) is not None, p + ".topic_id", "invalid stable topic_id")
        require(type(entry["subject"]) is str and entry["subject"] in SUBJECTS, p + ".subject", "unsupported subject")
        require(type(entry["relation"]) is str and entry["relation"] in RELATIONS, p + ".relation", "unknown topic scope")
        topic_projects[tid].add(ref[0])
        titles = entry["titles"]
        require(type(titles) is list and 1 <= len(titles) <= 30, p + ".titles", "expected 1..30 observed titles")
        prev_date = ""
        for j, row in enumerate(titles):
            t = f"{p}.titles[{j}]"
            exact_keys(row, t, {"date", "title", "source_url"})
            day = date_value(row["date"], t + ".date")
            require(day > prev_date, t + ".date", "observations must be dated and strictly increasing")
            prev_date = day
            bounded_text(row["title"], t + ".title", 255)
            source_url(row["source_url"], t + ".source_url")
        require(type(entry["continuity"]) is str and entry["continuity"] in CONTINUITIES, p + ".continuity", "explicit continuity required")
        events = entry["events"]
        require(type(events) is list and len(events) <= 30, p + ".events", "bounded event history required")
        prev_date = ""
        has_delete_boundary = False
        for j, evt in enumerate(events):
            e = f"{p}.events[{j}]"
            exact_keys(evt, e, {"date", "kind", "source_url"}, {"old_title", "new_title"})
            require(type(evt["kind"]) is str and evt["kind"] in {"move", "delete", "restore"}, e + ".kind", "unknown event")
            day = date_value(evt["date"], e + ".date")
            require(day >= prev_date, e + ".date", "events must be chronological")
            prev_date = day
            source_url(evt["source_url"], e + ".source_url")
            if evt["kind"] == "move":
                require("old_title" in evt and "new_title" in evt, e, "move needs old/new title")
                bounded_text(evt["old_title"], e + ".old_title", 255)
                bounded_text(evt["new_title"], e + ".new_title", 255)
                require(evt["old_title"] != evt["new_title"], e, "move must change title")
            else:
                require("old_title" not in evt and "new_title" not in evt, e, "delete/restore cannot infer title transition")
                has_delete_boundary = True
        require(not (has_delete_boundary and entry["continuity"] == "confirmed"), p + ".continuity", "deletion/restore cannot imply confirmed continuity without separate adjudication")
        redirect = entry["redirect_to"]
        if redirect is not None:
            exact_keys(redirect, p + ".redirect_to", {"target_ref", "observed_at", "source_url"})
            dest = page_ref(redirect["target_ref"], p + ".redirect_to.target_ref")
            date_value(redirect["observed_at"], p + ".redirect_to.observed_at")
            source_url(redirect["source_url"], p + ".redirect_to.source_url")
            require(dest != ref, p + ".redirect_to", "redirect cycle to self")
            require(dest[0] == ref[0], p + ".redirect_to", "cross-wiki redirect is not a local redirect edge")
            redirects.append((ref, dest, redirect["observed_at"]))
        mapping = exact_keys(entry["wikidata"], p + ".wikidata", {"state", "observed_qid", "resolved_qid", "evidence_url"})
        require(type(mapping["state"]) is str and mapping["state"] in MAPPING_STATES, p + ".wikidata.state", "mapping state required")
        qid(mapping["observed_qid"], p + ".wikidata.observed_qid")
        qid(mapping["resolved_qid"], p + ".wikidata.resolved_qid")
        if mapping["evidence_url"] is not None:
            source_url(mapping["evidence_url"], p + ".wikidata.evidence_url")
        if selection["evidence_kind"] == "reported_retrieval" and (mapping["observed_qid"] or mapping["resolved_qid"]):
            require(mapping["evidence_url"] is not None, p + ".wikidata.evidence_url", "Wikidata claim requires source URL")
        if mapping["state"] == "missing":
            require(mapping["observed_qid"] is None and mapping["resolved_qid"] is None and mapping["evidence_url"] is None, p + ".wikidata", "missing state cannot invent a QID or evidence")
        if mapping["state"] == "observed":
            require(mapping["observed_qid"] is not None and mapping["resolved_qid"] is None, p + ".wikidata", "observed QID without resolved mapping required")
        if mapping["state"] == "resolved":
            require(mapping["observed_qid"] is not None and mapping["resolved_qid"] is not None, p + ".wikidata", "preserve observed and resolved QIDs")
        if mapping["resolved_qid"]:
            qid_projects[(ref[0], mapping["resolved_qid"])].append(ref[1])
        provenance = entry["source"]
        if selection["evidence_kind"] == "synthetic":
            require(provenance is None, p + ".source", "synthetic fixture may not claim retrieval")
        else:
            exact_keys(provenance, p + ".source", {"endpoint", "requested_at", "http_status", "body_sha256", "response_bytes"})
            source_url(provenance["endpoint"], p + ".source.endpoint")
            timestamp(provenance["requested_at"], p + ".source.requested_at")
            require(provenance["http_status"] == 200 and type(provenance["http_status"]) is int, p + ".source.http_status", "successful HTTP evidence required")
            require(type(provenance["body_sha256"]) is str and HEX256.fullmatch(provenance["body_sha256"]), p + ".source.body_sha256", "SHA-256 required")
            require(type(provenance["response_bytes"]) is int and 1 <= provenance["response_bytes"] <= 1024 * 1024, p + ".source.response_bytes", "bounded response required")
        normalized_pages.append(entry)
    # Redirect edges are date-specific observations. A -> B observed on one day
    # and B -> A on another do NOT establish a simultaneous redirect cycle.
    # Report same-day cycles as unresolved evidence, never as identity merging.
    by_day = defaultdict(dict)
    for source_ref, target_ref, observed_at in redirects:
        if target_ref in seen:
            by_day[observed_at][source_ref] = target_ref
    cycles = set()
    for observed_at, outgoing in sorted(by_day.items()):
        visited = set()
        for start in sorted(outgoing):
            if start in visited:
                continue
            path, positions = [], {}
            current = start
            while current in outgoing and current not in visited:
                positions[current] = len(path)
                path.append(current)
                visited.add(current)
                current = outgoing[current]
                if current in positions:
                    cycle = tuple(sorted(path[positions[current]:]))
                    cycles.add((observed_at, cycle))
                    break
    cycle_report = [
        {"observed_at": when,
         "page_refs": [{"project": project, "page_id": pid} for project, pid in members],
         "status": "unresolved_redirect_cycle"}
        for when, members in sorted(cycles)
    ]
    dangling = sorted(
        (dict(source_project=s[0], source_page_id=s[1], target_project=t[0], target_page_id=t[1])
         for s, t, _ in redirects if t not in seen),
        key=lambda e: (e["source_project"], e["source_page_id"], e["target_project"], e["target_page_id"]),
    )
    collisions = [dict(project=k[0], qid=k[1], local_page_ids=sorted(v)) for k, v in sorted(qid_projects.items()) if len(v) > 1]
    counts_project = dict(sorted(Counter(page["page_ref"]["project"] for page in pages).items()))
    counts_subject = dict(sorted(Counter(page["subject"] for page in pages).items()))
    # Only count observed entries; never infer zero interest for an unobserved
    # edition/subject cell. These are *panel counts*, not Wikipedia pageviews.
    counts_cells = defaultdict(Counter)
    for page in pages:
        counts_cells[page["page_ref"]["project"]][page["subject"]] += 1
    counts_cells = {edition: dict(sorted(subjects.items())) for edition, subjects in sorted(counts_cells.items())}
    # Expose selected-but-not-obtained without fabricating missing records as zero pageviews.
    return {
        "schema_version": SCHEMA,
        "panel_id": panel["panel_id"],
        "selection": selection,
        "pages": sorted(normalized_pages, key=lambda p: (p["page_ref"]["project"], p["page_ref"]["page_id"])),
        "coverage": {
            "intended_count": count,
            "obtained_count": len(pages),
            "unresolved_count": count - len(pages),
            "by_edition": counts_project,
            "by_subject": counts_subject,
            "observed_panel_counts_by_edition_subject": counts_cells,
            "cross_edition_topic_ids": sorted(t for t, projects in topic_projects.items() if len(projects) > 1),
            "non_1_to_1_local_qid_collisions": collisions,
            "redirect_targets_outside_panel": dangling,
            "same_day_redirect_cycles": cycle_report,
            "selection_bias": "curated panel; not representative Wikipedia coverage",
            "provenance_verification": "synthetic_only" if selection["evidence_kind"] == "synthetic" else "reported_not_upstream_verified",
        },
    }


def canonical_bytes(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def load_panel(path: Path) -> dict:
    with path.open("rb") as stream:
        payload = stream.read(MAX_BYTES + 1)
    require(len(payload) <= MAX_BYTES, str(path), "input exceeds 256 KiB")

    def no_duplicates(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise PanelError(f"duplicate JSON key: {key}")
            obj[key] = value
        return obj

    def reject_constant(const):
        raise PanelError(f"non-finite JSON constant: {const}")

    try:
        doc = json.loads(payload.decode("utf-8"), object_pairs_hook=no_duplicates, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PanelError(f"invalid UTF-8 JSON: {exc}") from exc
    return validate_panel(doc)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="bounded identity-panel JSON")
    args = parser.parse_args(argv)
    try:
        result = load_panel(args.input)
        output = canonical_bytes(result)
    except (OSError, PanelError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(output)
    print("SHA256 " + hashlib.sha256(output).hexdigest(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
