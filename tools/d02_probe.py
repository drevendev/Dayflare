#!/usr/bin/env python3
"""Bounded D02 35-day empirical probe over the proven D01 candidate set."""
from __future__ import annotations
from datetime import date, timedelta
import hashlib, json, math, pathlib, statistics, sys, urllib.error, urllib.parse, urllib.request
from tools.d01_probe import BASE, REQUESTS, USER_AGENT, analyze_items, expected_dates, expected_response_project, iso_now

START="20260811"
END="20260914"
# A 35-day pageview series should be far smaller than 1 MiB. Bound both successful
# and HTTP-error responses so an upstream error cannot exhaust Actions memory.
MAX_RESPONSE_BYTES = 1024 * 1024
# Exact counts are exposed to JavaScript; larger integers silently lose precision.
MAX_JS_SAFE_INTEGER = (1 << 53) - 1


def read_bounded_body(stream: object) -> tuple[bytes, bool]:
    """Return a bounded prefix and whether the body exceeded the byte budget.

    A truncated response is never hashed as a complete source or parsed as data.
    """
    raw = stream.read(MAX_RESPONSE_BYTES + 1)
    return raw, len(raw) > MAX_RESPONSE_BYTES


def weekly_metrics(items: list[dict[str, object]]) -> dict[str, object]:
    if len(items) != 35:
        raise ValueError(f"expected 35 daily observations, got {len(items)}")

    validated: list[tuple[date, int]] = []
    for index, row in enumerate(items):
        raw_date=row.get("date")
        raw_views=row.get("views")
        if not isinstance(raw_date,str):
            raise ValueError(f"row {index}: date must be canonical YYYY-MM-DD")
        try:
            parsed_date=date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValueError(f"row {index}: invalid calendar date {raw_date!r}") from exc
        if parsed_date.isoformat() != raw_date:
            raise ValueError(f"row {index}: date must be canonical YYYY-MM-DD, got {raw_date!r}")
        if (isinstance(raw_views,bool) or not isinstance(raw_views,int) or
                raw_views < 0 or raw_views > MAX_JS_SAFE_INTEGER):
            raise ValueError(f"row {index}: views must be a non-negative integer within JavaScript-safe range")
        validated.append((parsed_date,raw_views))

    validated.sort(key=lambda item:item[0])
    dates=[item[0] for item in validated]
    if len(set(dates)) != 35:
        raise ValueError("expected 35 unique daily observations")
    for previous,current in zip(dates,dates[1:]):
        if current - previous != timedelta(days=1):
            raise ValueError(
                f"expected consecutive daily observations, got gap from {previous.isoformat()} to {current.isoformat()}"
            )

    totals=[sum(views for _,views in validated[o:o+7]) for o in range(0,35,7)]
    if any(total > MAX_JS_SAFE_INTEGER for total in totals):
        raise ValueError("weekly Pageviews total exceeds the JavaScript-safe integer range")
    h4,h3,h2,h1,current=totals
    # For four weeks, twice the median is the sum of the two middle totals.
    # Preserve the historical numeric JSON schema (float B/delta) while checking
    # whether the *derived* half-integers are exactly representable as JS Number.
    # Daily/weekly safe integers alone do not guarantee an exact median/delta.
    ordered=sorted((h1,h2,h3,h4))
    baseline_twice=ordered[1]+ordered[2]
    delta_twice=2*current-baseline_twice
    baseline=baseline_twice/2
    delta=current-baseline
    for name, computed, exact_twice in (
        ("median baseline",baseline,baseline_twice),
        ("weekly delta",delta,delta_twice),
    ):
        numerator,denominator=computed.as_integer_ratio()
        if 2*numerator != denominator*exact_twice:
            raise ValueError(f"{name} loses JavaScript numeric precision")
    return {
        "weekly_totals_oldest_to_current":totals,
        "V":current,"H1":h1,"H2":h2,"H3":h3,"H4":h4,
        "B":baseline,"delta":delta,
        "relative_lift":None if baseline == 0 else delta/baseline,
    }


def lifecycle_metrics(
    older_normal_totals: list[int | float],
    recent_quiet_totals: list[int | float],
    current: int | float,
    *,
    q_max: float,
    r_min: float,
    min_current_volume: int | float = 0,
    min_absolute_change: int | float = 0,
) -> dict[str, object]:
    """Calculate a parameterized return-from-quiet state without freezing block sizes."""

    def validated_block(name: str, values: list[int | float]) -> list[int | float]:
        if not values:
            raise ValueError(f"{name} must contain at least one complete window")
        cleaned: list[int | float] = []
        for index, value in enumerate(values):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value < 0
                or (isinstance(value, float) and not math.isfinite(value))
            ):
                raise ValueError(f"{name}[{index}] must be a non-negative finite number")
            if isinstance(value, int) and value > MAX_JS_SAFE_INTEGER:
                raise ValueError(f"{name}[{index}] exceeds the JavaScript-safe integer range")
            cleaned.append(value)
        return cleaned

    normal = validated_block("older_normal_totals", older_normal_totals)
    quiet = validated_block("recent_quiet_totals", recent_quiet_totals)

    numeric_inputs = {
        "current": current,
        "q_max": q_max,
        "r_min": r_min,
        "min_current_volume": min_current_volume,
        "min_absolute_change": min_absolute_change,
    }
    for name, value in numeric_inputs.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value < 0
            or (isinstance(value, float) and not math.isfinite(value))
        ):
            raise ValueError(f"{name} must be a non-negative finite number")
        if isinstance(value, int) and value > MAX_JS_SAFE_INTEGER:
            raise ValueError(f"{name} exceeds the JavaScript-safe integer range")

    normal_level = statistics.median(normal)
    quiet_level = statistics.median(quiet)
    quiet_ratio = None if normal_level == 0 else quiet_level / normal_level
    return_ratio = None if normal_level == 0 else current / normal_level
    return_delta = current - quiet_level
    # Finite inputs can still overflow during median or division (for example,
    # a subnormal positive normal level). Never emit Infinity/NaN as a signal or
    # silently classify such a series; strict JSON cannot represent them.
    for name, value in (
        ("normal median", normal_level), ("quiet median", quiet_level),
        ("quiet ratio", quiet_ratio), ("return ratio", return_ratio),
        ("return delta", return_delta),
    ):
        if value is not None and not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    eligible = (
        current >= min_current_volume
        and return_delta >= min_absolute_change
    )
    returning = bool(
        normal_level > 0
        and quiet_ratio is not None
        and return_ratio is not None
        and quiet_ratio <= q_max
        and return_ratio >= r_min
        and eligible
    )

    return {
        "normal_windows": len(normal),
        "quiet_windows": len(quiet),
        "N": normal_level,
        "Q": quiet_level,
        "V": current,
        "quiet_ratio": quiet_ratio,
        "return_ratio": return_ratio,
        "return_delta": return_delta,
        "eligible": eligible,
        "returning": returning,
        "thresholds": {
            "q_max": q_max,
            "r_min": r_min,
            "min_current_volume": min_current_volume,
            "min_absolute_change": min_absolute_change,
        },
    }

def main() -> int:
    out_dir=pathlib.Path("artifacts/d02"); out_dir.mkdir(parents=True,exist_ok=True)
    expected=expected_dates(START,END)
    receipts=[]; sample=[]; series_metrics=[]; run_started=iso_now()
    for spec in REQUESTS:
        encoded=urllib.parse.quote(spec["article"],safe="")
        url=f'{BASE}/{spec["project"]}/all-access/user/{encoded}/daily/{START}/{END}'
        req_started=iso_now(); status=None; raw=b""; truncated=False; body_complete=False; error=None; headers={}
        try:
            req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=30) as resp:
                status=int(resp.status)
                headers={k.lower():v for k,v in resp.headers.items() if k.lower() in {"content-type","etag","last-modified"}}
                raw,truncated=read_bounded_body(resp)
                body_complete=not truncated
                if truncated:
                    error=f"ResponseTooLarge: body exceeds {MAX_RESPONSE_BYTES} bytes"
        except urllib.error.HTTPError as exc:
            status=int(exc.code)
            error=f"HTTPError: {exc.reason}"
            try:
                raw,truncated=read_bounded_body(exc)
                body_complete=not truncated
                if truncated:
                    error+=f"; ResponseTooLarge: body exceeds {MAX_RESPONSE_BYTES} bytes"
            except Exception as body_error:
                # An error response can itself be interrupted. Preserve its HTTP
                # status and emit a receipt, not a fabricated empty-body checksum.
                error+=f"; {type(body_error).__name__}: {body_error}"
            finally:
                exc.close()
        except Exception as exc:
            error=f"{type(exc).__name__}: {exc}"

        body_sha=hashlib.sha256(raw).hexdigest() if body_complete else None
        items=[]; parse_error=None; payload_valid=False
        if raw and not truncated:
            try:
                payload=json.loads(raw.decode("utf-8"))
                if isinstance(payload,dict) and isinstance(payload.get("items"),list):
                    items=payload["items"]; payload_valid=True
                else:
                    parse_error="PayloadError: expected JSON object with an items list"
            except Exception as exc:
                parse_error=f"{type(exc).__name__}: {exc}"
        elif status == 200 and not truncated:
            parse_error="PayloadError: empty HTTP 200 response body"

        clean=status == 200 and not error and not parse_error and payload_valid
        analysis=analyze_items(items,spec,expected) if clean else {
            "semantic_valid":False,"semantic_errors":[],"dates_present_raw":[],
            "missing_days_raw":list(expected),"omitted_zero_days":[],
            "unresolved_days":list(expected),"normalized_items":[],
            "normalized_complete":False,
        }
        normalized=analysis["normalized_items"]
        receipts.append({
            "project":spec["project"],"article_requested":spec["article"],"subject_area":spec["subject"],
            "endpoint":url,"parameters":{"access":"all-access","agent":"user","granularity":"daily","start":START,"end":END},
            "expected_response":{"project":expected_response_project(spec["project"]),"article":spec["article"],"access":"all-access","agent":"user","granularity":"daily"},
            "request_started_at":req_started,"retrieved_at":iso_now(),"http_status":status,
            "response_bytes":len(raw),"response_sha256":body_sha,"response_truncated":truncated,"response_body_complete":body_complete,"response_headers":headers,
            "payload_valid":payload_valid,"semantic_valid":analysis["semantic_valid"],
            "semantic_errors":analysis["semantic_errors"],"expected_days":len(expected),
            "item_count_raw":len(items),"item_count_normalized":len(normalized),
            "missing_days_raw":analysis["missing_days_raw"],"omitted_zero_days":analysis["omitted_zero_days"],
            "unresolved_days":analysis["unresolved_days"],"normalized_complete":analysis["normalized_complete"],
            "error":error,"parse_error":parse_error,
        })
        sample.append({"request":spec,"items":normalized})
        # A structurally valid response can still exceed the exact numeric range
        # of the public JSON/JavaScript contract. Keep raw source evidence, but
        # report the computation failure and never mark this run publishable.
        metrics=None
        if analysis["normalized_complete"]:
            try:
                metrics=weekly_metrics(normalized)
            except ValueError as exc:
                receipts[-1]["error"] = f"MetricError: {exc}"
        series_metrics.append({"request":spec,"metrics":metrics})

    sample_bytes=json.dumps(sample,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    success=all(r["http_status"] == 200 and not r["error"] and not r["parse_error"] and r["payload_valid"] and r["semantic_valid"] and not r["unresolved_days"] and r["normalized_complete"] for r in receipts)
    manifest={
        "schema_version":1,"probe":"D02","method_version":"v0-empirical-35d",
        "run_started_at":run_started,"run_finished_at":iso_now(),
        "observation_window":{"start":START,"end":END,"expected_days":35},
        "window_semantics":{"window_days":7,"V":"most recent complete 7-day total","H1_H4":"four immediately preceding complete 7-day totals, newest to oldest","B":"median(H1,H2,H3,H4)","delta":"V-B","relative_lift":"(V-B)/B, undefined when B=0"},
        "thresholds_frozen":False,
        "scope_note":"Same six fixed EN/RU D01 access candidates across three subject areas; not representative coverage and not yet the low-traffic/seasonal/returning edge-case set.",
        "request_count":len(REQUESTS),"receipts":receipts,"series_metrics":series_metrics,
        "normalized_sample_sha256":hashlib.sha256(sample_bytes).hexdigest(),"success":success,
    }
    (out_dir/"sample.json").write_bytes(sample_bytes+b"\n")
    (out_dir/"receipt.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True))
    return 0 if success else 2

if __name__ == "__main__":
    sys.exit(main())
