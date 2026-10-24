"""Resolve curated EN/RU titles to *candidate* Wikipedia numeric page IDs.

A current title lookup never proves historical continuity, Wikidata equivalence,
provider-origin authenticity, or the popularity of the candidate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA = "dayflare.curated-title-discovery.v1"
SEED_SCHEMA = "dayflare.identity-seeds.v1"
RECEIPT_SCHEMA = "dayflare.title-id-discovery.v1"
PROJECTS = frozenset({"en.wikipedia", "ru.wikipedia"})
SUBJECTS = frozenset({"culture", "books", "games", "science", "sport", "other"})
RELATIONS = frozenset({"equivalent", "broader", "narrower", "related", "ambiguous", "missing"})
MAX_PAGES = 30
MAX_BODY = 1_048_576
MAX_TOTAL = 8_388_608


class DiscoveryError(ValueError):
    """Unsafe candidate input, provider response, or replay evidence."""


def require(ok, message):
    if not ok:
        raise DiscoveryError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def unique_dict(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "duplicate JSON key")
        out[key] = value
    return out


def read_json(path, limit=32_768):
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= limit,
            "missing/unsafe/oversized JSON member")
    return json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=unique_dict,
                      parse_constant=lambda _: (_ for _ in ()).throw(DiscoveryError("nonfinite JSON")))


def validate_curated(doc, utc_day):
    require(type(doc) is dict and set(doc) == {"schema_version", "panel_id", "selected_at", "pages"},
            "invalid curated-input fields")
    require(doc["schema_version"] == SCHEMA, "wrong input version")
    require(type(doc["panel_id"]) is str and re.fullmatch(r"[a-z][a-z0-9._-]{0,119}", doc["panel_id"]),
            "invalid panel ID")
    require(type(doc["selected_at"]) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc["selected_at"]),
            "noncanonical selection date")
    try:
        selected = datetime.strptime(doc["selected_at"], "%Y-%m-%d").date()
    except ValueError as exc:
        raise DiscoveryError("invalid selection date") from exc
    require(selected <= utc_day, "future curated selection")
    rows = doc["pages"]
    require(type(rows) is list and 1 <= len(rows) <= MAX_PAGES, "requires 1..30 titles")
    seen = set()
    for row in rows:
        require(type(row) is dict and set(row) == {"project", "title", "topic_id", "subject", "relation"},
                "invalid candidate fields")
        project, title = row["project"], row["title"]
        require(type(project) is str and project in PROJECTS, "unsupported edition")
        require(type(title) is str and 0 < len(title) <= 255 and title == title.strip() and
                not any(ch in title for ch in ("_", "|", "#", "\n", "\r")) and
                not any(0xD800 <= ord(ch) <= 0xDFFF for ch in title),
                "invalid canonical title")
        require(type(row["topic_id"]) is str and
                re.fullmatch(r"[a-z][a-z0-9._-]{0,119}", row["topic_id"]), "invalid topic ID")
        require(type(row["subject"]) is str and row["subject"] in SUBJECTS and
                type(row["relation"]) is str and row["relation"] in RELATIONS, "invalid relation/subject")
        require((project, title.casefold()) not in seen, "duplicate edition/title")
        seen.add((project, title.casefold()))
    return sorted(rows, key=lambda item: (item["project"], item["title"].casefold(), item["title"]))


def endpoint(project, title):
    require(project in PROJECTS, "unsupported origin")
    return f"https://{project}.org/w/api.php?" + urlencode({
        "action": "query", "format": "json", "formatversion": "2",
        "prop": "info|pageprops", "ppprop": "wikibase_item", "titles": title,
    })


def fetch_once(url):
    req = Request(url, headers={
        "User-Agent": "DayflareIdentity/0.2 (https://github.com/drevendev/Dayflare)",
        "Accept": "application/json", "Accept-Encoding": "identity",
    })
    with urlopen(req, timeout=10) as response:
        require(response.status == 200 and
                response.headers.get("Content-Encoding", "identity") == "identity",
                "non-200 or compressed source response")
        raw = response.read(MAX_BODY + 1)
    require(0 < len(raw) <= MAX_BODY, "missing/oversized response")
    return raw


def parse(raw, requested_title):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, "invalid response bytes")
    doc = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_dict,
                     parse_constant=lambda _: (_ for _ in ()).throw(DiscoveryError("nonfinite JSON")))
    require(type(doc) is dict and doc.get("batchcomplete") is True and
            not any(key in doc for key in ("error", "errors", "continue", "query-continue")),
            "incomplete/errored Action API response")
    query = doc.get("query")
    require(type(query) is dict and type(query.get("pages")) is list and len(query["pages"]) == 1,
            "ambiguous page response")
    if "normalized" in query or "redirects" in query:
        return None, "normalization_or_redirect_requires_review"
    page = query["pages"][0]
    require(type(page) is dict, "invalid page object")
    if any(key in page for key in ("missing", "invalid", "redirect")):
        return None, "missing_invalid_or_redirect"
    if type(page.get("ns")) is not int or page["ns"] != 0 or page.get("title") != requested_title:
        return None, "different_title_or_namespace"
    page_id = page.get("pageid")
    require(type(page_id) is int and 0 < page_id < 2**53, "invalid stable numeric page ID")
    props = page.get("pageprops", {})
    require(type(props) is dict, "invalid pageprops")
    qid = props.get("wikibase_item")
    require(qid is None or (type(qid) is str and re.fullmatch(r"Q[1-9][0-9]*", qid)),
            "invalid observed QID")
    return (page_id, qid), None


def discover(curated, fetch=fetch_once, clock=lambda: datetime.now(timezone.utc),
             sleep=time.sleep):
    before = clock()
    require(isinstance(before, datetime) and before.tzinfo is not None and
            before.utcoffset() is not None and before.utcoffset().total_seconds() == 0,
            "aware UTC clock required")
    rows = validate_curated(curated, before.date())
    observed_ids, seeds, receipts, retained = set(), [], [], {}
    total = 0
    previous = before
    for index, row in enumerate(rows):
        if index:
            sleep(2)
        url = endpoint(row["project"], row["title"])
        raw = fetch(url)
        require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, "unsafe response size")
        total += len(raw)
        require(total <= MAX_TOTAL, "aggregate response budget exceeded")
        now = clock()
        require(isinstance(now, datetime) and now.tzinfo is not None and
                now.utcoffset() is not None and now.utcoffset().total_seconds() == 0 and
                now.date() == before.date() and now >= previous, "inconsistent UTC retrieval time")
        previous = now
        candidate, reason = parse(raw, row["title"])
        filename = f"{index:02d}.json"
        retained[filename] = raw
        record = {"project": row["project"], "requested_title": row["title"], "endpoint": url,
                  "retrieved_at": now.isoformat(), "status": "candidate" if candidate else "excluded",
                  "reason": reason, "raw_member": filename,
                  "raw_bytes": len(raw), "raw_sha256": sha256(raw).hexdigest()}
        if candidate:
            page_id, qid = candidate
            require((row["project"], page_id) not in observed_ids,
                    "multiple titles resolve to the same page ID")
            observed_ids.add((row["project"], page_id))
            record.update(page_id=page_id, observed_qid=qid)
            seeds.append({"page_ref": {"project": row["project"], "page_id": page_id},
                          "topic_id": row["topic_id"], "subject": row["subject"],
                          "relation": row["relation"]})
        receipts.append(record)
    require(bool(seeds), "no unambiguous current page IDs")
    seed = {"schema_version": SEED_SCHEMA, "panel_id": curated["panel_id"],
            "selected_at": curated["selected_at"],
            "pages": sorted(seeds, key=lambda item: (item["page_ref"]["project"],
                                                    item["page_ref"]["page_id"]))}
    report = {"schema_version": RECEIPT_SCHEMA,
              "curated_sha256": sha256(canonical(curated)).hexdigest(),
              "observed_date_utc": before.date().isoformat(),
              "requested_count": len(rows), "candidate_count": len(seeds),
              "excluded_count": len(rows) - len(seeds), "retained_decoded_bytes": total,
              "status": "LOCAL_ONLY_CANDIDATE_IDS_REQUIRE_INDEPENDENT_ID_REQUERY",
              "attempts": receipts,
              "limitations": ["Curated titles are selected, not representative coverage.",
                              "Self-consistent checksums do not independently prove Wikimedia origin.",
                              "Current page IDs do not establish historical moves/redirect continuity.",
                              "Independently re-query each ID using tools.m1_collect."]}
    return seed, report, retained


def verify(curated_path, bundle):
    require(bundle.is_dir() and not bundle.is_symlink(), "missing/unsafe bundle")
    require({p.name for p in bundle.iterdir()} ==
            {"identity-seeds.json", "discovery-report.json", "raw"},
            "unlisted/missing bundle members")
    curated = read_json(curated_path)
    report = read_json(bundle / "discovery-report.json", 256_000)
    seed = read_json(bundle / "identity-seeds.json", 256_000)
    require(canonical(report) == (bundle / "discovery-report.json").read_bytes() and
            canonical(seed) == (bundle / "identity-seeds.json").read_bytes(),
            "noncanonical seed/report")
    raw_dir = bundle / "raw"
    require(raw_dir.is_dir() and not raw_dir.is_symlink(), "missing/unsafe raw directory")
    attempts = report.get("attempts")
    require(type(attempts) is list and 1 <= len(attempts) <= MAX_PAGES, "invalid receipt list")
    require({p.name for p in raw_dir.iterdir()} ==
            {f"{i:02d}.json" for i in range(len(attempts))}, "unlisted raw member")
    bodies = []
    timestamps = []
    for i, record in enumerate(attempts):
        path = raw_dir / f"{i:02d}.json"
        require(path.is_file() and not path.is_symlink() and
                0 < path.stat().st_size <= MAX_BODY, "unsafe raw member")
        bodies.append(path.read_bytes())
        require(type(record) is dict and type(record.get("retrieved_at")) is str,
                "bad timestamp receipt")
        try:
            timestamps.append(datetime.fromisoformat(record["retrieved_at"]))
        except ValueError as exc:
            raise DiscoveryError("invalid receipt UTC timestamp") from exc
    require(type(report.get("observed_date_utc")) is str, "missing UTC observation date")
    try:
        first = datetime.fromisoformat(report["observed_date_utc"] + "T00:00:00+00:00")
    except ValueError as exc:
        raise DiscoveryError("invalid UTC observation date") from exc
    order = iter([first, *timestamps])
    index = 0
    def replay(url):
        nonlocal index
        require(index < len(attempts) and url == attempts[index].get("endpoint"),
                "unexpected replay endpoint")
        data = bodies[index]
        index += 1
        return data
    rebuilt_seed, rebuilt_report, rebuilt_raw = discover(
        curated, fetch=replay, clock=lambda: next(order), sleep=lambda _: None)
    require(index == len(attempts) and canonical(seed) == canonical(rebuilt_seed) and
            canonical(report) == canonical(rebuilt_report), "seed/receipt replay mismatch")
    require(all(bodies[int(name[:-5])] == body for name, body in rebuilt_raw.items()),
            "raw member mismatch")
    return report


def run(curated_path, destination):
    require(destination.parent.is_dir() and not destination.parent.is_symlink() and
            not destination.exists() and not destination.is_symlink(),
            "output must be a new directory under a real existing parent")
    curated = read_json(curated_path)
    seed, report, raw = discover(curated)
    from .rolling_pageview_source import _atomic_new_dir
    with tempfile.TemporaryDirectory(prefix=".dayflare-title-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        (stage / "raw").mkdir()
        for name, body in raw.items():
            (stage / "raw" / name).write_bytes(body)
        (stage / "identity-seeds.json").write_bytes(canonical(seed))
        (stage / "discovery-report.json").write_bytes(canonical(report))
        verify(curated_path, stage)
        _atomic_new_dir(stage, destination)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="replay a retained bundle without network")
    parser.add_argument("curated", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = verify(args.curated, args.output) if args.verify else run(args.curated, args.output)
    except (DiscoveryError, OSError, RuntimeError, ValueError, UnicodeError) as exc:
        parser.exit(2, f"NOT_PUBLISHED: {exc}\n")
    print(canonical(receipt).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
