"""Read-only D02 publication gate: verify an already-collected sample and its receipt.

Usage (from a fresh Dayflare checkout, after ``python -m tools.d02_probe``)::

    python -m tools.verify_d02_artifacts

This does NOT retrieve data, create a publication, or attest that the data are fresh or
representative. A valid fixed-window receipt is evidence integrity, not a public signal.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import zipfile
import zlib
from typing import Any, Mapping, Sequence
from urllib.parse import quote

MAX_CAPSULE_BYTES = 512 * 1024
MAX_PROVENANCE_BYTES = 16 * 1024
MAX_SAFE_INTEGER = 2**53 - 1
MAX_SAMPLE_BYTES = 2 * 1024 * 1024
MAX_RECEIPT_BYTES = 512 * 1024
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class EvidenceError(ValueError):
    """The supplied D02 evidence must not be used for public output."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def parse_json(raw: bytes, *, name: str, max_bytes: int) -> Any:
    require(0 < len(raw) <= max_bytes, f"{name}: invalid byte length")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"{name}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    def bad_constant(value: str) -> Any:
        raise EvidenceError(f"{name}: non-finite JSON constant {value}")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs, parse_constant=bad_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{name}: invalid UTF-8 JSON: {exc}") from exc


def exact_number(actual: Any, expected: Fraction, *, path: str) -> None:
    require(type(actual) in (int, float) and abs(actual) <= MAX_SAFE_INTEGER, f"{path}: not a finite exact-range number")
    require(math.isfinite(actual), f"{path}: not a finite number")
    require(abs(expected) <= MAX_SAFE_INTEGER, f"{path}: outside exact JS numeric range")
    # A half-integer can round even when adjacent integers fit the safe range.
    # Compare the actual representation to the exact rational recomputation.
    require(expected.denominator in (1, 2), f"{path}: unexpected fractional precision")
    require(Fraction(actual) == expected, f"{path}: differs from recomputation")
    require(Fraction(float(actual)) == expected, f"{path}: loses binary64 precision")


def iso_timestamp(value: Any, *, path: str) -> datetime:
    require(type(value) is str, f"{path}: timestamp must be a string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{path}: invalid timestamp") from exc
    require(result.utcoffset() == timedelta(0), f"{path}: expected UTC timestamp")
    return result


def validate_artifacts(
    sample_bytes: bytes,
    receipt_bytes: bytes,
    *,
    requests: Sequence[Mapping[str, str]],
    start: str,
    end: str,
    base_url: str,
) -> dict[str, Any]:
    """Fail closed if one part of the fixed D02 evidence contradicts another.

    ``requests``, ``start``, ``end``, and ``base_url`` must come from the authoritative
    D01/D02 modules, not copied configuration in a second control file.
    """
    sample = parse_json(sample_bytes, name="sample", max_bytes=MAX_SAMPLE_BYTES)
    receipt = parse_json(receipt_bytes, name="receipt", max_bytes=MAX_RECEIPT_BYTES)
    require(type(sample) is list and type(receipt) is dict, "unexpected top-level JSON shapes")
    require(type(requests) in (tuple, list) and len(requests) == 6, "expected the fixed six source requests")
    try:
        first = datetime.strptime(start, "%Y%m%d").date()
        last = datetime.strptime(end, "%Y%m%d").date()
    except ValueError as exc:
        raise EvidenceError("invalid source window") from exc
    days = (last - first).days + 1
    require(days == 35, "fixed D02 window must have exactly 35 days")
    expected_dates = [(first + timedelta(days=day)).isoformat() for day in range(days)]
    require(len(sample) == len(requests) == 6, "incorrect series count")

    canonical = json.dumps(sample, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    require(sample_bytes == canonical + b"\n", "sample bytes are not the collector's canonical JSON")
    require(receipt.get("schema_version") == 1 and type(receipt.get("schema_version")) is int, "unsupported receipt schema")
    require(receipt.get("probe") == "D02", "not a D02 receipt")
    require(receipt.get("method_version") == "v0-empirical-35d", "unsupported method version")
    require(receipt.get("success") is True, "source retrieval did not succeed")
    require(receipt.get("thresholds_frozen") is False, "unvalidated thresholds cannot be frozen")
    require(receipt.get("request_count") == 6 and type(receipt.get("request_count")) is int, "incorrect request count")
    require(receipt.get("observation_window") == {"start": start, "end": end, "expected_days": days}, "window mismatch")
    require(receipt.get("window_semantics") == {
        "window_days": 7,
        "V": "most recent complete 7-day total",
        "H1_H4": "four immediately preceding complete 7-day totals, newest to oldest",
        "B": "median(H1,H2,H3,H4)",
        "delta": "V-B",
        "relative_lift": "(V-B)/B, undefined when B=0",
    }, "method window semantics changed")
    require(type(receipt.get("receipts")) is list and len(receipt["receipts"]) == 6, "missing request receipts")
    require(type(receipt.get("series_metrics")) is list and len(receipt["series_metrics"]) == 6, "missing metrics")
    claimed_hash = receipt.get("normalized_sample_sha256")
    require(type(claimed_hash) is str and HASH_PATTERN.fullmatch(claimed_hash) is not None, "invalid sample digest")
    require(hashlib.sha256(canonical).hexdigest() == claimed_hash, "sample checksum mismatch")
    started = iso_timestamp(receipt.get("run_started_at"), path="run_started_at")
    ended = iso_timestamp(receipt.get("run_finished_at"), path="run_finished_at")
    require(started <= ended, "inverted run timestamps")

    observations = 0
    for index, spec in enumerate(requests):
        require(type(spec) is dict, f"series[{index}]: invalid source spec")
        require(all(type(spec.get(k)) is str for k in ("project", "article", "subject")), "invalid source spec")
        row = sample[index]
        req = receipt["receipts"][index]
        metric_row = receipt["series_metrics"][index]
        prefix = f"series[{index}]"
        require(type(row) is dict and type(req) is dict and type(metric_row) is dict, f"{prefix}: invalid shapes")
        require(row.get("request") == spec and metric_row.get("request") == spec, f"{prefix}: request identity mismatch")
        require(req.get("project") == spec["project"] and req.get("article_requested") == spec["article"], f"{prefix}: receipt identity mismatch")
        require(req.get("subject_area") == spec["subject"], f"{prefix}: subject mismatch")
        require(req.get("endpoint") == f'{base_url}/{spec["project"]}/all-access/user/{quote(spec["article"], safe="")}/daily/{start}/{end}', f"{prefix}: endpoint mismatch")
        require(req.get("parameters") == {"access": "all-access", "agent": "user", "granularity": "daily", "start": start, "end": end}, f"{prefix}: incompatible filters")
        require(req.get("expected_response") == {"project": spec["project"].removesuffix(".org"), "article": spec["article"], "access": "all-access", "agent": "user", "granularity": "daily"}, f"{prefix}: response identity mismatch")
        require(req.get("http_status") == 200 and type(req.get("http_status")) is int, f"{prefix}: HTTP response not successful")
        require(req.get("payload_valid") is True and req.get("semantic_valid") is True and req.get("normalized_complete") is True, f"{prefix}: source validation failed")
        require(not req.get("error") and not req.get("parse_error") and req.get("unresolved_days") == [] and req.get("semantic_errors") == [], f"{prefix}: unresolved source failure")
        if "response_body_complete" in req:
            require(req["response_body_complete"] is True, f"{prefix}: incomplete HTTP response body")
        if "body_complete" in req:
            require(req["body_complete"] is True, f"{prefix}: incomplete HTTP response body")
        if "response_truncated" in req:
            require(req["response_truncated"] is False, f"{prefix}: truncated HTTP response body")
        require(type(req.get("response_bytes")) is int and 0 < req["response_bytes"] <= 1024 * 1024, f"{prefix}: invalid response budget")
        require(type(req.get("response_sha256")) is str and HASH_PATTERN.fullmatch(req["response_sha256"]) is not None, f"{prefix}: missing raw-response checksum")
        t0 = iso_timestamp(req.get("request_started_at"), path=f"{prefix}.request_started_at")
        t1 = iso_timestamp(req.get("retrieved_at"), path=f"{prefix}.retrieved_at")
        require(started <= t0 <= t1 <= ended, f"{prefix}: request/retrieval timestamps out of bounds")

        items = row.get("items")
        require(type(items) is list and len(items) == days, f"{prefix}: incomplete daily sample")
        require(req.get("expected_days") == days and type(req.get("expected_days")) is int, f"{prefix}: expected-days mismatch")
        require(req.get("item_count_normalized") == days and type(req.get("item_count_normalized")) is int, f"{prefix}: normalized count mismatch")
        omitted = []
        weekly = [0] * 5
        for day, item in enumerate(items):
            require(type(item) is dict, f"{prefix}.items[{day}]: expected object")
            path = f"{prefix}.items[{day}]"
            require(item.get("date") == expected_dates[day], f"{path}: missing/duplicate/reordered date")
            require(type(item.get("views")) is int and 0 <= item["views"] <= MAX_SAFE_INTEGER, f"{path}: invalid/inexact view count")
            require(item.get("project") == spec["project"].removesuffix(".org") and item.get("article") == spec["article"], f"{path}: page identity mismatch")
            require(item.get("access") == "all-access" and item.get("agent") == "user" and item.get("granularity") == "daily", f"{path}: filter mismatch")
            if item.get("value_state") == "documented_omitted_zero":
                require(item["views"] == 0 and item.get("fill_reason") == "wikimedia_time_series_omitted_zero", f"{path}: invalid zero normalization")
                omitted.append(item["date"])
            else:
                require(item.get("value_state") == "observed" and item.get("fill_reason") is None, f"{path}: invalid observation state")
            weekly[day // 7] += item["views"]
        require(all(v <= MAX_SAFE_INTEGER for v in weekly), f"{prefix}: inexact weekly total")
        require(req.get("missing_days_raw") == omitted and req.get("omitted_zero_days") == omitted, f"{prefix}: omitted zero dates mismatch")
        require(type(req.get("item_count_raw")) is int and req["item_count_raw"] == days - len(omitted), f"{prefix}: source item count mismatch")

        metrics = metric_row.get("metrics")
        require(type(metrics) is dict, f"{prefix}: missing numeric metrics")
        require(metrics.get("weekly_totals_oldest_to_current") == weekly, f"{prefix}: incorrect weekly totals")
        for idx, key in enumerate(("H4", "H3", "H2", "H1", "V")):
            exact_number(metrics.get(key), Fraction(weekly[idx]), path=f"{prefix}.metrics.{key}")
        older = sorted(weekly[:4])
        baseline = Fraction(older[1] + older[2], 2)
        delta = Fraction(weekly[4]) - baseline
        exact_number(metrics.get("B"), baseline, path=f"{prefix}.metrics.B")
        exact_number(metrics.get("delta"), delta, path=f"{prefix}.metrics.delta")
        relative = metrics.get("relative_lift")
        if baseline == 0:
            require(relative is None, f"{prefix}: zero baseline needs null lift")
        else:
            require(type(relative) in (float, int), f"{prefix}: invalid relative lift")
            calculated = float(delta / baseline)
            require(math.isfinite(calculated) and relative == calculated, f"{prefix}: relative lift mismatch")
        observations += days

    return {"valid": True, "schema_version": 1, "method_version": "v0-empirical-35d", "series": len(sample), "observations": observations, "sample_sha256": claimed_hash, "observation_window": receipt["observation_window"], "retrieval_finished_at": receipt["run_finished_at"], "scope": "fixed, selected, historical EN/RU Wikimedia experiment—not current or representative coverage"}


def read_limited(path: Path, limit: int) -> bytes:
    """Read no more than the declared budget plus one detection byte."""
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, f"{path.name}: invalid byte length")
    return raw


def read_retained(directory: Path) -> tuple[bytes, bytes, dict[str, Any]]:
    """Read a two-JSON capsule in memory. Never extract files or execute content.

    Hashes bind the checked-in files, not a third-party authenticity signature.
    The original provider archive digest and the repacked capsule digest differ.
    """
    provenance = parse_json(read_limited(directory / "provenance.json", MAX_PROVENANCE_BYTES),
                            name="provenance", max_bytes=MAX_PROVENANCE_BYTES)
    require(type(provenance) is dict and type(provenance.get("schema_version")) is int
            and provenance["schema_version"] == 1, "unsupported provenance schema")
    capsule = provenance.get("capsule")
    require(type(capsule) is dict and capsule.get("file") == "source.zip", "invalid capsule path")
    claims = capsule.get("members")
    limits = {"sample.json": MAX_SAMPLE_BYTES, "receipt.json": MAX_RECEIPT_BYTES}
    require(type(claims) is dict and set(claims) == set(limits), "invalid capsule member claims")
    raw = read_limited(directory / "source.zip", MAX_CAPSULE_BYTES)
    require(hashlib.sha256(raw).hexdigest() == capsule.get("sha256"), "capsule checksum mismatch")
    loaded = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            require(len(infos) == 2 and {i.filename for i in infos} == set(limits),
                    "capsule must contain exactly sample.json and receipt.json")
            for info in infos:
                require(not info.is_dir() and not info.flag_bits & 1,
                        "capsule member must be an unencrypted data file")
                require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        "unsupported capsule compression")
                limit = limits[info.filename]
                require(0 < info.file_size <= limit, "capsule member exceeds byte budget")
                with archive.open(info) as stream:
                    data = stream.read(limit + 1)
                require(len(data) == info.file_size and len(data) <= limit, "incomplete capsule member")
                claim = claims[info.filename]
                require(type(claim) is dict and type(claim.get("bytes")) is int
                        and claim["bytes"] == len(data)
                        and claim.get("sha256") == hashlib.sha256(data).hexdigest(),
                        f"{info.filename}: member checksum/size mismatch")
                loaded[info.filename] = data
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
        raise EvidenceError(f"invalid capsule: {exc}") from exc
    return loaded["sample.json"], loaded["receipt.json"], provenance


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--retained", type=Path,
                        help="Read-only validation of a checked-in source.zip/provenance.json directory")
    args = parser.parse_args(argv)
    if args.retained and (args.sample or args.receipt):
        parser.error("--retained cannot be combined with --sample or --receipt")
    from tools.d01_probe import BASE, REQUESTS
    from tools.d02_probe import START, END
    try:
        provenance = None
        if args.retained:
            sample, receipt, provenance = read_retained(args.retained)
        else:
            sample = read_limited(args.sample or Path("artifacts/d02/sample.json"), MAX_SAMPLE_BYTES)
            receipt = read_limited(args.receipt or Path("artifacts/d02/receipt.json"), MAX_RECEIPT_BYTES)
        result = validate_artifacts(sample, receipt, requests=REQUESTS, start=START, end=END, base_url=BASE)
        if provenance:
            require(result["sample_sha256"] == provenance.get("normalized_sample_sha256"),
                    "retained normalized sample checksum mismatch")
            result["dataset_id"] = provenance.get("dataset_id")
            result["raw_http_body_verification"] = "NOT_POSSIBLE_FROM_NORMALIZED_SAMPLE"
    except (EvidenceError, OSError) as exc:
        print(f"D02_ARTIFACT_INVALID: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
