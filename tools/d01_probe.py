#!/usr/bin/env python3
"""Bounded D01 Wikimedia Pageviews runtime probe.

Writes machine-readable request receipts and a normalized sample. It intentionally
tests only a fixed, small EN/RU set and does not claim population or topic coverage.

Wikimedia documents that successful time-series responses can omit zero-valued
dates. Those gaps are normalized to explicit zero observations only for a valid
HTTP 200 time-series response; HTTP errors, network errors, parse failures, and
other unresolved gaps remain unavailable rather than being guessed as zero.
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
    payload_valid = False
    if raw:
        try:
            payload = json.loads(raw.decode("utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                items = payload["items"]
                payload_valid = True
            else:
                parse_error = "PayloadError: expected JSON object with an items list"
        except Exception as exc:
            parse_error = f"{type(exc).__name__}: {exc}"
    elif status == 200:
        parse_error = "PayloadError: empty HTTP 200 response body"

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
            "value_state": "observed",
            "fill_reason": None,
        })

    missing_raw = sorted(set(expected) - set(dates_present))
    clean_time_series = status == 200 and not error and not parse_error and payload_valid
    omitted_zero_days = missing_raw if clean_time_series else []
    unresolved_days = [] if clean_time_series else missing_raw

    for date in omitted_zero_days:
        normalized_items.append({
            "date": date,
            "views": 0,
            "project": spec["project"],
            "article": spec["article"],
            "access": "all-access",
            "agent": "user",
            "granularity": "daily",
            "value_state": "documented_omitted_zero",
            "fill_reason": "wikimedia_time_series_omitted_zero",
        })

    normalized_items.sort(key=lambda item: item["date"] or "")
    normalized_dates = [item["date"] for item in normalized_items if item["date"]]
    normalized_complete = len(normalized_items) == len(expected) and set(normalized_dates) == set(expected)

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
        "payload_valid": payload_valid,
        "item_count_raw": len(items),
        "item_count_normalized": len(normalized_items),
        "expected_days": len(expected),
        "dates_present_raw": sorted(set(dates_present)),
        "missing_days_raw": missing_raw,
        "omitted_zero_days": omitted_zero_days,
        "unresolved_days": unresolved_days,
        "normalized_complete": normalized_complete,
        "error": error,
        "parse_error": parse_error,
    }
    receipts.append(receipt)
    sample.append({"request": spec, "items": normalized_items})

run_finished = iso_now()
sample_bytes = json.dumps(sample, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
manifest = {
    "schema_version": 2,
    "probe": "D01",
    "run_started_at": run_started,
    "run_finished_at": run_finished,
    "observation_window": {"start": START, "end": END, "expected_days": len(expected)},
    "user_agent": USER_AGENT,
    "request_count": len(REQUESTS),
    "receipts": receipts,
    "normalized_sample_sha256": hashlib.sha256(sample_bytes).hexdigest(),
    "success": all(
        r["http_status"] == 200
        and not r["error"]
        and not r["parse_error"]
        and r["payload_valid"]
        and not r["unresolved_days"]
        and r["normalized_complete"]
        for r in receipts
    ),
    "scope_note": "Fixed EN/RU access probe across three subject areas; not representative coverage.",
    "zero_fill_policy": (
        "Only gaps inside a valid HTTP 200 Wikimedia time-series response are normalized as "
        "documented omitted zeros. HTTP errors, network errors, parse failures, and unresolved "
        "responses are never converted to zero."
    ),
}

(OUT / "sample.json").write_bytes(sample_bytes + b"\n")
(OUT / "receipt.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))

if not manifest["success"]:
    sys.exit(2)
