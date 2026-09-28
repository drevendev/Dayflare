#!/usr/bin/env python3
"""Bounded D01 Wikimedia Pageviews runtime probe.

Writes machine-readable request receipts and a normalized sample. It intentionally
tests only a fixed, small EN/RU set and does not claim population or topic coverage.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

OUT = pathlib.Path("artifacts/d01")
OUT.mkdir(parents=True, exist_ok=True)

START = "20260901"
END = "20260914"
REQUESTS = [
    {"project": "en.wikipedia.org", "article": "Artificial_intelligence", "subject": "science/technology"},
    {"project": "en.wikipedia.org", "article": "The_Master_and_Margarita", "subject": "culture/literature"},
    {"project": "en.wikipedia.org", "article": "Chess", "subject": "games/sport"},
    {"project": "ru.wikipedia.org", "article": "Искусственный_интеллект", "subject": "science/technology"},
    {"project": "ru.wikipedia.org", "article": "Мастер_и_Маргарита", "subject": "culture/literature"},
    {"project": "ru.wikipedia.org", "article": "Шахматы", "subject": "games/sport"},
]
USER_AGENT = "Dayflare/0.1 (https://github.com/drevendev/Dayflare)"
BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"

def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def expected_dates(start: str, end: str) -> list[str]:
    first = dt.datetime.strptime(start, "%Y%m%d").date()
    last = dt.datetime.strptime(end, "%Y%m%d").date()
    out = []
    cur = first
    while cur <= last:
        out.append(cur.isoformat())
        cur += dt.timedelta(days=1)
    return out

expected = expected_dates(START, END)
receipts = []
sample = []
run_started = iso_now()

for spec in REQUESTS:
    encoded = urllib.parse.quote(spec["article"], safe="")
    url = f'{BASE}/{spec["project"]}/all-access/user/{encoded}/daily/{START}/{END}'
    req_started = iso_now()
    status = None
    raw = b""
    error = None
    headers = {}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = int(resp.status)
            headers = {k.lower(): v for k, v in resp.headers.items() if k.lower() in {"content-type", "etag", "last-modified"}}
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
        error = f"HTTPError: {exc.reason}"
    except Exception as exc:  # network/DNS/TLS errors are evidence, not zeroes
        error = f"{type(exc).__name__}: {exc}"

    body_sha = hashlib.sha256(raw).hexdigest()
    items = []
    parse_error = None
    if raw:
        try:
            payload = json.loads(raw.decode("utf-8"))
            items = payload.get("items", []) if isinstance(payload, dict) else []
        except Exception as exc:
            parse_error = f"{type(exc).__name__}: {exc}"

    dates_present = []
    normalized_items = []
    for item in items:
        ts = str(item.get("timestamp", ""))
        date = None
        if len(ts) >= 8 and ts[:8].isdigit():
            date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            dates_present.append(date)
        normalized_items.append({
            "date": date,
            "views": item.get("views"),
            "project": item.get("project"),
            "article": item.get("article"),
            "access": item.get("access"),
            "agent": item.get("agent"),
            "granularity": item.get("granularity"),
        })

    missing = sorted(set(expected) - set(dates_present))
    receipt = {
        "project": spec["project"],
        "article_requested": spec["article"],
        "subject_area": spec["subject"],
        "endpoint": url,
        "parameters": {
            "access": "all-access",
            "agent": "user",
            "granularity": "daily",
            "start": START,
            "end": END,
        },
        "request_started_at": req_started,
        "retrieved_at": iso_now(),
        "http_status": status,
        "response_bytes": len(raw),
        "response_sha256": body_sha,
        "response_headers": headers,
        "item_count": len(items),
        "expected_days": len(expected),
        "dates_present": sorted(set(dates_present)),
        "missing_days": missing,
        "error": error,
        "parse_error": parse_error,
    }
    receipts.append(receipt)
    sample.append({"request": spec, "items": normalized_items})

run_finished = iso_now()
sample_bytes = json.dumps(sample, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
manifest = {
    "schema_version": 1,
    "probe": "D01",
    "run_started_at": run_started,
    "run_finished_at": run_finished,
    "observation_window": {"start": START, "end": END, "expected_days": len(expected)},
    "user_agent": USER_AGENT,
    "request_count": len(REQUESTS),
    "receipts": receipts,
    "normalized_sample_sha256": hashlib.sha256(sample_bytes).hexdigest(),
    "success": all(
        r["http_status"] == 200 and not r["error"] and not r["parse_error"] and r["item_count"] > 0 and not r["missing_days"]
        for r in receipts
    ),
    "scope_note": "Fixed EN/RU access probe across three subject areas; not representative coverage.",
}

(OUT / "sample.json").write_bytes(sample_bytes + b"\n")
(OUT / "receipt.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))

if not manifest["success"]:
    sys.exit(2)
