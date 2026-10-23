"""Fail-closed, offline completeness gate for bounded EN/RU rolling candidates.

This is NOT a source collector, publication/promotion action, or upstream authenticity
check. Its input contains reported request provenance; separate raw-body and
publisher verification remain necessary before public release.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit

SCHEMA = "dayflare.rolling-candidate.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_SERIES = 30
DAYS = 35
HEX = re.compile(r"[0-9a-f]{64}\Z")
UTC_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")
ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")


class WindowError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise WindowError(message)


def exact(obj, fields, where):
    require(type(obj) is dict and set(obj) == set(fields), f"{where}: unexpected or missing fields")


def day(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
            "noncanonical observation date")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise WindowError("invalid observation date") from exc
    require(result.isoformat() == value, "noncanonical observation date")
    return result


def stamp(value):
    require(type(value) is str and UTC_TIME.fullmatch(value) is not None, "invalid UTC retrieval timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise WindowError("invalid UTC retrieval timestamp") from exc


def canonical(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def validate(doc, *, now=None):
    now = now or datetime.now(timezone.utc)
    require(type(now) is datetime and now.tzinfo is not None and now.utcoffset() == timedelta(0),
            "now must be UTC")
    exact(doc, ("schema_version", "dataset_id", "method_version", "retrieved_at",
                "provider_lag_days", "observation_end", "series"), "candidate")
    require(doc["schema_version"] == SCHEMA, "unsupported candidate schema")
    for key in ("dataset_id", "method_version"):
        require(type(doc[key]) is str and ID.fullmatch(doc[key]) is not None, f"invalid {key}")
    lag = doc["provider_lag_days"]
    require(type(lag) is int and 1 <= lag <= 7, "invalid bounded provider lag")
    end = day(doc["observation_end"])
    require(end <= now.date() - timedelta(days=lag + 1), "observation window not provider-lag complete")
    require(end >= now.date() - timedelta(days=90), "observation window too old for rolling candidate")
    start = end - timedelta(days=DAYS - 1)
    retrieved = stamp(doc["retrieved_at"])
    require(datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc)
            <= retrieved <= now + timedelta(minutes=5), "retrieval before observation end or in future")
    series = doc["series"]
    require(type(series) is list and 1 <= len(series) <= MAX_SERIES, "invalid series count")
    refs = set()
    counts = {"en.wikipedia": 0, "ru.wikipedia": 0}
    for index, item in enumerate(series):
        prefix = f"series[{index}]"
        exact(item, ("project", "page_id", "title", "access", "agent",
                     "source", "daily"), prefix)
        project = item["project"]
        require(type(project) is str and project in counts, f"{prefix}: unsupported edition")
        page_id = item["page_id"]
        require(type(page_id) is int and 1 <= page_id < 2**53, f"{prefix}: invalid page ID")
        ref = (project, page_id)
        require(ref not in refs, f"{prefix}: duplicate stable page identity")
        refs.add(ref)
        title = item["title"]
        require(type(title) is str and 0 < len(title) <= 256 and not any(ord(c) < 32 for c in title),
                f"{prefix}: invalid observed title")
        require(item["access"] == "all-access" and item["agent"] == "user",
                f"{prefix}: incomparable access/agent filters")
        receipt = item["source"]
        exact(receipt, ("endpoint", "requested_at", "http_status", "body_sha256", "response_bytes"),
              prefix + ".source")
        endpoint = receipt["endpoint"]
        require(type(endpoint) is str, f"{prefix}: invalid endpoint")
        url = urlsplit(endpoint)
        expected_path = (f"/api/rest_v1/metrics/pageviews/per-article/{project}.org/"
                         f"all-access/user/{quote(title.replace(' ', '_'), safe='')}/daily/"
                         f"{start:%Y%m%d}/{end:%Y%m%d}")
        require(url.scheme == "https" and url.netloc == "wikimedia.org" and
                url.path == expected_path and not url.query and not url.fragment,
                f"{prefix}: endpoint does not match project/title/filters/window")
        requested = stamp(receipt["requested_at"])
        require(datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc)
                <= requested <= retrieved, f"{prefix}: invalid request chronology")
        require(type(receipt["http_status"]) is int and receipt["http_status"] == 200,
                f"{prefix}: unsuccessful source response")
        require(type(receipt["body_sha256"]) is str and HEX.fullmatch(receipt["body_sha256"]) is not None,
                f"{prefix}: invalid reported source hash")
        require(type(receipt["response_bytes"]) is int and 1 <= receipt["response_bytes"] <= 1024 * 1024,
                f"{prefix}: invalid source byte count")
        daily = item["daily"]
        require(type(daily) is list and len(daily) == DAYS, f"{prefix}: incomplete 35-day history")
        for offset, row in enumerate(daily):
            exact(row, ("date", "views", "value_state"), f"{prefix}.daily[{offset}]")
            require(day(row["date"]) == start + timedelta(days=offset),
                    f"{prefix}: missing, duplicated or out-of-order day")
            require(row["value_state"] == "observed", f"{prefix}: unobserved day is not zero")
            require(type(row["views"]) is int and 0 <= row["views"] < 2**53,
                    f"{prefix}: invalid view count")
        counts[project] += 1
    data_hash = hashlib.sha256(canonical(doc)).hexdigest()
    return {
        "schema_version": "dayflare.rolling-gate-report.v1",
        "dataset_id": doc["dataset_id"], "method_version": doc["method_version"],
        "candidate_sha256": data_hash, "observation_start": start.isoformat(),
        "observation_end": end.isoformat(), "retrieved_at": doc["retrieved_at"],
        "provider_lag_days": lag, "window_days": DAYS,
        "complete_series": len(series), "observations": DAYS * len(series),
        "by_edition": {k: v for k, v in counts.items() if v},
        "provenance_status": "self_reported_not_independently_verified",
        "publication_status": "NOT_STAGED_NOT_DEPLOYED",
        "selection_bias": "curated identities; not representative of either Wikipedia edition",
    }


def read_candidate(path):
    with path.open("rb") as stream:
        payload = stream.read(MAX_BYTES + 1)
    require(len(payload) <= MAX_BYTES, "candidate exceeds 2 MiB")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda x: (_ for _ in ()).throw(WindowError("non-finite number")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WindowError("invalid UTF-8 JSON") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate(read_candidate(args.candidate))
    except (OSError, WindowError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
