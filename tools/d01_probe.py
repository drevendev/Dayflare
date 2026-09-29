#!/usr/bin/env python3
"""Bounded D01 Wikimedia Pageviews runtime probe.

Writes machine-readable request receipts and a normalized sample. It intentionally
tests only a fixed, small EN/RU set and does not claim population or topic coverage.

Wikimedia documents that successful time-series responses can omit zero-valued
dates. Those gaps are normalized to explicit zero observations only when the HTTP
200 payload also passes Dayflare's semantic validation for the requested series.
Transport errors, parse failures, semantic mismatches, duplicate/out-of-window
timestamps, and other unresolved responses remain unavailable rather than being
guessed as zero.
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


def expected_response_project(request_project: str) -> str:
    """Normalize Wikimedia REST request project to the response's project form."""
    return request_project.removesuffix(".org")


def parse_daily_timestamp(value: object) -> tuple[str | None, str | None]:
    """Return ISO date plus an error for the documented daily timestamp shape."""
    if not isinstance(value, str) or len(value) != 10 or not value.isdigit() or not value.endswith("00"):
        return None, "timestamp must be a 10-digit YYYYMMDD00 string"
    try:
        day = dt.datetime.strptime(value[:8], "%Y%m%d").date()
    except ValueError:
        return None, "timestamp contains an invalid calendar date"
    return day.isoformat(), None


def analyze_items(items: list[object], spec: dict[str, str], expected: list[str]) -> dict[str, object]:
    """Validate one successful Wikimedia series and normalize documented omitted zeros.

    Any semantic mismatch fails the whole requested series closed. In that case no
    observed or synthesized values are emitted and every requested day remains
    unresolved. This prevents a malformed HTTP 200 response from becoming trusted
    evidence or from enabling zero-fill.
    """
    expected_set = set(expected)
    response_project = expected_response_project(spec["project"])
    dates_present: list[str] = []
    seen_dates: set[str] = set()
    semantic_errors: list[str] = []
    observed_items: list[dict[str, object]] = []

    for index, raw_item in enumerate(items):
        prefix = f"items[{index}]"
        if not isinstance(raw_item, dict):
            semantic_errors.append(f"{prefix}: item must be an object")
            continue

        date, timestamp_error = parse_daily_timestamp(raw_item.get("timestamp"))
        if timestamp_error:
            semantic_errors.append(f"{prefix}.timestamp: {timestamp_error}")
        elif date not in expected_set:
            semantic_errors.append(f"{prefix}.timestamp: date {date} is outside the requested window")
        else:
            dates_present.append(date)
            if date in seen_dates:
                semantic_errors.append(f"{prefix}.timestamp: duplicate requested date {date}")
            seen_dates.add(date)

        if raw_item.get("project") != response_project:
            semantic_errors.append(
                f"{prefix}.project: expected {response_project!r}, got {raw_item.get('project')!r}"
            )
        if raw_item.get("article") != spec["article"]:
            semantic_errors.append(
                f"{prefix}.article: expected {spec['article']!r}, got {raw_item.get('article')!r}"
            )
        if raw_item.get("access") != "all-access":
            semantic_errors.append(
                f"{prefix}.access: expected 'all-access', got {raw_item.get('access')!r}"
            )
        if raw_item.get("agent") != "user":
            semantic_errors.append(f"{prefix}.agent: expected 'user', got {raw_item.get('agent')!r}")
        if raw_item.get("granularity") != "daily":
            semantic_errors.append(
                f"{prefix}.granularity: expected 'daily', got {raw_item.get('granularity')!r}"
            )

        views = raw_item.get("views")
        if type(views) is not int or views < 0:
            semantic_errors.append(f"{prefix}.views: expected a non-negative integer, got {views!r}")

        if (
            date in expected_set
            and raw_item.get("project") == response_project
            and raw_item.get("article") == spec["article"]
            and raw_item.get("access") == "all-access"
            and raw_item.get("agent") == "user"
            and raw_item.get("granularity") == "daily"
            and type(views) is int
            and views >= 0
        ):
            observed_items.append(
                {
                    "date": date,
                    "views": views,
                    "project": raw_item.get("project"),
                    "article": raw_item.get("article"),
                    "access": raw_item.get("access"),
                    "agent": raw_item.get("agent"),
                    "granularity": raw_item.get("granularity"),
                    "value_state": "observed",
                    "fill_reason": None,
                }
            )

    missing_raw = sorted(expected_set - set(dates_present))
    semantic_valid = not semantic_errors

    if not semantic_valid:
        return {
            "semantic_valid": False,
            "semantic_errors": semantic_errors,
            "dates_present_raw": sorted(set(dates_present)),
            "missing_days_raw": missing_raw,
            "omitted_zero_days": [],
            "unresolved_days": list(expected),
            "normalized_items": [],
            "normalized_complete": False,
        }

    normalized_items = observed_items[:]
    omitted_zero_days = missing_raw
    for date in omitted_zero_days:
        normalized_items.append(
            {
                "date": date,
                "views": 0,
                "project": response_project,
                "article": spec["article"],
                "access": "all-access",
                "agent": "user",
                "granularity": "daily",
                "value_state": "documented_omitted_zero",
                "fill_reason": "wikimedia_time_series_omitted_zero",
            }
        )

    normalized_items.sort(key=lambda item: str(item["date"]))
    normalized_dates = [str(item["date"]) for item in normalized_items]
    normalized_complete = len(normalized_items) == len(expected) and normalized_dates == expected

    return {
        "semantic_valid": True,
        "semantic_errors": [],
        "dates_present_raw": sorted(set(dates_present)),
        "missing_days_raw": missing_raw,
        "omitted_zero_days": omitted_zero_days,
        "unresolved_days": [],
        "normalized_items": normalized_items,
        "normalized_complete": normalized_complete,
    }


def main() -> int:
    out_dir = pathlib.Path("artifacts/d01")
    out_dir.mkdir(parents=True, exist_ok=True)

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
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = int(resp.status)
                headers = {
                    k.lower(): v
                    for k, v in resp.headers.items()
                    if k.lower() in {"content-type", "etag", "last-modified"}
                }
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
            error = f"HTTPError: {exc.reason}"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        body_sha = hashlib.sha256(raw).hexdigest()
        items: list[object] = []
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

        clean_payload = status == 200 and not error and not parse_error and payload_valid
        if clean_payload:
            analysis = analyze_items(items, spec, expected)
        else:
            analysis = {
                "semantic_valid": False,
                "semantic_errors": [],
                "dates_present_raw": [],
                "missing_days_raw": list(expected),
                "omitted_zero_days": [],
                "unresolved_days": list(expected),
                "normalized_items": [],
                "normalized_complete": False,
            }

        normalized_items = analysis["normalized_items"]
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
            "expected_response": {
                "project": expected_response_project(spec["project"]),
                "article": spec["article"],
                "access": "all-access",
                "agent": "user",
                "granularity": "daily",
                "timestamp_shape": "YYYYMMDD00",
                "views": "non-negative integer",
            },
            "request_started_at": req_started,
            "retrieved_at": iso_now(),
            "http_status": status,
            "response_bytes": len(raw),
            "response_sha256": body_sha,
            "response_headers": headers,
            "payload_valid": payload_valid,
            "semantic_valid": analysis["semantic_valid"],
            "semantic_errors": analysis["semantic_errors"],
            "item_count_raw": len(items),
            "item_count_normalized": len(normalized_items),
            "expected_days": len(expected),
            "dates_present_raw": analysis["dates_present_raw"],
            "missing_days_raw": analysis["missing_days_raw"],
            "omitted_zero_days": analysis["omitted_zero_days"],
            "unresolved_days": analysis["unresolved_days"],
            "normalized_complete": analysis["normalized_complete"],
            "error": error,
            "parse_error": parse_error,
        }
        receipts.append(receipt)
        sample.append({"request": spec, "items": normalized_items})

    run_finished = iso_now()
    sample_bytes = json.dumps(
        sample,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest = {
        "schema_version": 3,
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
            and r["semantic_valid"]
            and not r["unresolved_days"]
            and r["normalized_complete"]
            for r in receipts
        ),
        "scope_note": "Fixed EN/RU access probe across three subject areas; not representative coverage.",
        "zero_fill_policy": (
            "Only missing dates inside an HTTP 200 payload that passes structural and semantic "
            "validation are normalized as documented omitted zeros. Transport/HTTP/parse/schema "
            "errors, semantic mismatches (including wrong article identity), duplicate timestamps, "
            "out-of-window timestamps, and invalid view counts fail the whole requested series "
            "closed: no zero-fill is emitted "
            "and every requested day remains unresolved."
        ),
    }

    (out_dir / "sample.json").write_bytes(sample_bytes + b"\n")
    (out_dir / "receipt.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))

    return 0 if manifest["success"] else 2


if __name__ == "__main__":
    sys.exit(main())
