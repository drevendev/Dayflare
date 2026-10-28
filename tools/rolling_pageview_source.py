"""One-shot bounded Wikimedia pageview collection with retained-body verification.

A reviewed title/page-ID seed is REQUIRED. Raw Analytics API observations are
attributed to that supplied title, NOT independently linked to its stable page ID.
This creates offline source evidence and an optional LOCAL candidate only. It never
updates a site, claims upstream proof from hashes, or schedules network requests.
"""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import quote
import zlib

from .rolling_window_gate import (DAYS, MAX_BYTES, MAX_SERIES, SCHEMA as CANDIDATE_SCHEMA,
                                  WindowError, canonical, day, exact, read_candidate,
                                  require, stamp, validate)

SEED_SCHEMA = "dayflare.rolling-pageview-seeds.v1"
RECEIPT_SCHEMA = "dayflare.rolling-source-receipt.v1"
MAX_SEED_BYTES = 32 * 1024
MAX_BODY = 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
TIMEOUT_SECONDS = 12
MIN_SPACING_SECONDS = 2
UA = "DayflarePageviews/0.1 (https://github.com/drevendev/Dayflare) Python-urllib"
SUBJECTS = frozenset({"culture", "books", "games", "science", "sport", "other"})
VERSION_FILES = frozenset({"candidate.json", "source-receipt.json", "seeds.json", "raw"})
HEX = re.compile(r"[0-9a-f]{64}\Z")


class SourceError(ValueError):
    """Invalid seed, unsupported response, incomplete collection or unsafe bundle."""


@dataclass(frozen=True)
class FetchResult:
    status: int
    body: bytes                 # decoded JSON entity, not necessarily wire payload
    wire_bytes: int
    wire_sha256: str
    content_encoding: str


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: bytes, location: str, *, max_bytes: int):
    if not 0 < len(raw) <= max_bytes:
        raise SourceError(f"{location}: empty or oversized JSON")

    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise SourceError(f"{location}: duplicate JSON key {k!r}")
            d[k] = v
        return d

    def no_nonfinite(s):
        raise SourceError(f"{location}: non-finite JSON constant {s}")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=no_nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceError(f"{location}: invalid UTF-8 JSON") from exc


def check_seed(seed, *, now: datetime):
    try:
        exact(seed, ("schema_version", "selected_at", "method_version", "provider_lag_days", "pages"), "seed")
        require(seed["schema_version"] == SEED_SCHEMA, "wrong seed schema")
        selected = day(seed["selected_at"])
        require(selected <= now.date(), "future seed selection")
        method = seed["method_version"]
        require(type(method) is str and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}", method) is not None,
                "invalid method_version")
        lag = seed["provider_lag_days"]
        require(type(lag) is int and 1 <= lag <= 7, "invalid provider lag")
        rows = seed["pages"]
        require(type(rows) is list and 1 <= len(rows) <= MAX_SERIES, "1..30 curated pages required")
        seen = set()
        seen_queries = set()
        for i, item in enumerate(rows):
            exact(item, ("project", "page_id", "title", "subject"), f"seed.pages[{i}]")
            project, pid, title = item["project"], item["page_id"], item["title"]
            require(type(project) is str and project in ("en.wikipedia", "ru.wikipedia"), "invalid edition")
            require(type(pid) is int and 0 < pid < 2**53, "invalid page id")
            require((project, pid) not in seen, "duplicate stable identity")
            seen.add((project, pid))
            require(type(title) is str and 0 < len(title) <= 256 and
                    not any(ord(c) < 32 or ord(c) == 127 for c in title), "invalid observed title")
            # Analytics is title-scoped: two different page IDs must never
            # generate the same edition/title query and duplicate observations.
            # The outbound endpoint maps spaces to underscores, so compare
            # precisely that same path representation (not Unicode casefold).
            query_key = (project, title.replace(" ", "_"))
            require(query_key not in seen_queries,
                    "duplicate title-based Analytics query across page IDs")
            seen_queries.add(query_key)
            require(type(item["subject"]) is str and item["subject"] in SUBJECTS, "invalid subject")
    except WindowError as exc:
        raise SourceError(str(exc)) from exc
    return sorted(rows, key=lambda s: (s["project"], s["page_id"]))


def endpoint(project: str, title: str, start: date, end: date) -> str:
    return ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"{project}.org/all-access/user/{quote(title.replace(' ', '_'), safe='')}/daily/"
            f"{start:%Y%m%d}/{end:%Y%m%d}")


def decode_entity(wire: bytes, encoding: str) -> bytes:
    if not 0 < len(wire) <= MAX_BODY:
        raise SourceError("empty/oversized wire body")
    if encoding == "identity":
        return wire
    if encoding != "gzip":
        raise SourceError("unsupported upstream Content-Encoding")
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        entity = decoder.decompress(wire, MAX_BODY + 1)
    except zlib.error as exc:
        raise SourceError("invalid gzip body") from exc
    if (not entity or len(entity) > MAX_BODY or decoder.unconsumed_tail or
            not decoder.eof or decoder.unused_data):
        raise SourceError("truncated, oversized or extra gzip member")
    return entity


def fetch_once(url: str) -> FetchResult:
    """Exact HTTPS GET, no redirects/retries/cookies, with bounded wire/entity."""
    request = Request(url, method="GET", headers={"User-Agent": UA,
                     "Accept": "application/json", "Accept-Encoding": "gzip"})
    try:
        with build_opener(NoRedirect).open(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            if status != 200:
                raise SourceError(f"upstream HTTP {status}; no retry")
            if response.headers.get_content_type() != "application/json":
                raise SourceError("upstream Content-Type is not application/json")
            length = response.headers.get("Content-Length")
            if length is not None:
                if not length.isascii() or not length.isdecimal() or len(length) > 7 or (len(length) > 1 and length[0] == "0"):
                    raise SourceError("invalid Content-Length")
                if not 0 < int(length) <= MAX_BODY:
                    raise SourceError("upstream Content-Length exceeds limit")
            wire = response.read(MAX_BODY + 1)
            if length is not None and len(wire) != int(length):
                raise SourceError("incomplete/excess HTTP wire body")
            encoding = response.headers.get("Content-Encoding", "identity").strip().lower() or "identity"
            entity = decode_entity(wire, encoding)
            return FetchResult(status, entity, len(wire), sha(wire), encoding)
    except HTTPError as exc:
        after = exc.headers.get("Retry-After") if exc.headers else None
        raise SourceError(f"upstream HTTP {exc.code}; Retry-After={after!r}; no automatic retry") from exc
    except IncompleteRead as exc:
        raise SourceError("truncated HTTP response") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise SourceError(f"network failure: {type(exc).__name__}") from exc


def parse_pageviews(raw: bytes, page: dict, start: date, end: date) -> list[dict]:
    doc = strict_json(raw, "source", max_bytes=MAX_BODY)
    if type(doc) is not dict or set(doc) != {"items"} or type(doc["items"]) is not list:
        raise SourceError("source: expected exact pageviews items object")
    if len(doc["items"]) != DAYS:
        raise SourceError("source: incomplete 35-day history; no zero inference")
    result = []
    for i, row in enumerate(doc["items"]):
        if type(row) is not dict or set(row) != {"project", "article", "access", "agent", "granularity", "timestamp", "views"}:
            raise SourceError(f"source.items[{i}]: unexpected/missing fields")
        if (row["project"] != page["project"] or row["access"] != "all-access" or
                row["agent"] != "user" or row["granularity"] != "daily" or
                type(row["article"]) is not str or
                row["article"].replace(" ", "_") != page["title"].replace(" ", "_")):
            raise SourceError(f"source.items[{i}]: mismatched title, edition or filters")
        expected = start + timedelta(days=i)
        if (type(row["timestamp"]) is not str or
                row["timestamp"] != f"{expected:%Y%m%d}00"):
            raise SourceError(f"source.items[{i}]: missing/out-of-order date")
        n = row["views"]
        if type(n) is not int or not 0 <= n < 2**53:
            raise SourceError(f"source.items[{i}]: invalid/non-finite views")
        result.append({"date": expected.isoformat(), "views": n, "value_state": "observed"})
    return result


def _now(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise SourceError("UTC-aware clock required")
    return value


def build(seed, *, fetch=fetch_once, now=None, sleep=time.sleep, injected=False):
    """Run one bounded series of HTTP attempts; nothing persisted until full success."""
    clock = now or (lambda: datetime.now(timezone.utc))
    started = _now(clock())
    pages = check_seed(seed, now=started)
    end = started.date() - timedelta(days=seed["provider_lag_days"] + 1)
    start = end - timedelta(days=DAYS - 1)
    series, receipt_sources, bodies = [], [], {}
    wire_sum = decoded_sum = 0
    for i, page in enumerate(pages):
        if i:
            sleep(MIN_SPACING_SECONDS)
        url = endpoint(page["project"], page["title"], start, end)
        requested_at = _now(clock()).isoformat(timespec="seconds").replace("+00:00", "Z")
        response = fetch(url)
        if type(response) is not FetchResult or type(response.status) is not int or response.status != 200:
            raise SourceError("unsuccessful/malformed HTTP response; stop without publication")
        raw = response.body
        if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BODY or
                type(response.wire_bytes) is not int or not 0 < response.wire_bytes <= MAX_BODY or
                type(response.wire_sha256) is not str or HEX.fullmatch(response.wire_sha256) is None or
                response.content_encoding not in ("identity", "gzip")):
            raise SourceError("invalid bounded upstream transport metadata")
        if response.content_encoding == "identity" and (response.wire_bytes != len(raw) or response.wire_sha256 != sha(raw)):
            raise SourceError("identity wire/entity mismatch")
        wire_sum += response.wire_bytes
        decoded_sum += len(raw)
        if wire_sum > MAX_TOTAL or decoded_sum > MAX_TOTAL:
            raise SourceError("aggregate source size exceeded")
        daily = parse_pageviews(raw, page, start, end)
        source = {"endpoint": url, "requested_at": requested_at, "http_status": 200,
                  "body_sha256": sha(raw), "response_bytes": len(raw)}
        series.append({"project": page["project"], "page_id": page["page_id"],
                       "title": page["title"], "access": "all-access", "agent": "user",
                       "source": source, "daily": daily})
        name = f"{page['project']}.{page['page_id']}.json"
        bodies[name] = raw
        receipt_sources.append({"project": page["project"], "page_id": page["page_id"],
                                "subject": page["subject"], "raw_member": "raw/" + name,
                                "wire_bytes": response.wire_bytes, "wire_sha256": response.wire_sha256,
                                "content_encoding": response.content_encoding,
                                **source})
    finished = _now(clock())
    if finished.date() != started.date():
        raise SourceError("UTC day changed during collection; discard incomplete candidate")
    retrieved_at = finished.isoformat(timespec="seconds").replace("+00:00", "Z")
    source_seed_sha = sha(canonical(seed))
    dataset_id = "run-" + finished.strftime("%Y%m%d-%H%M%S-") + source_seed_sha[:12]
    candidate = {"schema_version": CANDIDATE_SCHEMA, "dataset_id": dataset_id,
                 "method_version": seed["method_version"], "retrieved_at": retrieved_at,
                 "provider_lag_days": seed["provider_lag_days"], "observation_end": end.isoformat(),
                 "series": series}
    try:
        validate(candidate, now=finished)
    except WindowError as exc:
        raise SourceError(f"candidate gate rejected retrieval: {exc}") from exc
    receipt = {"schema_version": RECEIPT_SCHEMA, "seed_sha256": source_seed_sha,
               "candidate_sha256": sha(canonical(candidate)), "retrieved_at": retrieved_at,
               "observation_start": start.isoformat(), "observation_end": end.isoformat(),
               "requests_attempted": len(series), "total_wire_bytes": wire_sum,
               "total_decoded_bytes": decoded_sum, "sources": receipt_sources,
               "provenance_status": ("synthetic_injected_not_upstream_evidence" if injected else
                                      "runtime_reported_transport_not_independently_authenticated"),
               "publication_status": "LOCAL_EVIDENCE_ONLY_NOT_PUBLISHED"}
    return candidate, receipt, bodies


def _bytes(path: Path, limit: int):
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise SourceError(f"unsafe/missing file: {path}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise SourceError(f"empty/oversized file: {path}")
    return raw


def verify_bundle(root: Path, *, now=None):
    """Offline byte and content agreement; NOT independent transport provenance."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or {p.name for p in root.iterdir()} != VERSION_FILES:
        raise SourceError("unexpected/unsafe evidence bundle inventory")
    raw_dir = root / "raw"
    if raw_dir.is_symlink() or not raw_dir.is_dir():
        raise SourceError("unsafe raw directory")
    candidate_raw = _bytes(root / "candidate.json", MAX_BYTES)
    seed_raw = _bytes(root / "seeds.json", MAX_SEED_BYTES)
    receipt_raw = _bytes(root / "source-receipt.json", MAX_BYTES)
    candidate = read_candidate(root / "candidate.json")
    seed = strict_json(seed_raw, "seed", max_bytes=MAX_SEED_BYTES)
    receipt = strict_json(receipt_raw, "receipt", max_bytes=MAX_BYTES)
    if candidate_raw != canonical(candidate) or seed_raw != canonical(seed) or receipt_raw != canonical(receipt):
        raise SourceError("bundle JSON is not canonical")
    try:
        validate(candidate, now=now)
    except WindowError as exc:
        raise SourceError(f"candidate gate failure: {exc}") from exc
    if type(receipt) is not dict:
        raise SourceError("receipt must be object")
    exact(receipt, ("schema_version", "seed_sha256", "candidate_sha256", "retrieved_at",
                    "observation_start", "observation_end", "requests_attempted",
                    "total_wire_bytes", "total_decoded_bytes", "sources", "provenance_status",
                    "publication_status"), "receipt")
    if (receipt["schema_version"] != RECEIPT_SCHEMA or receipt["seed_sha256"] != sha(seed_raw) or
            receipt["candidate_sha256"] != sha(candidate_raw) or
            receipt["retrieved_at"] != candidate["retrieved_at"] or
            receipt["observation_end"] != candidate["observation_end"] or
            receipt["publication_status"] != "LOCAL_EVIDENCE_ONLY_NOT_PUBLISHED" or
            receipt["provenance_status"] not in ("synthetic_injected_not_upstream_evidence",
                                                 "runtime_reported_transport_not_independently_authenticated")):
        raise SourceError("receipt metadata does not match canonical source/candidate")
    chosen = check_seed(seed, now=stamp(candidate["retrieved_at"]))
    expected_start = day(candidate["observation_end"]) - timedelta(days=DAYS - 1)
    if (receipt["observation_start"] != expected_start.isoformat() or
            candidate["method_version"] != seed["method_version"] or
            candidate["provider_lag_days"] != seed["provider_lag_days"] or
            len(chosen) != len(candidate["series"]) or
            type(receipt["sources"]) is not list or len(receipt["sources"]) != len(chosen) or
            type(receipt["requests_attempted"]) is not int or receipt["requests_attempted"] != len(chosen)):
        raise SourceError("receipt/seed candidate scope or chronology mismatch")
    expected_raw = {f"{p['project']}.{p['page_id']}.json" for p in chosen}
    if {p.name for p in raw_dir.iterdir()} != expected_raw:
        raise SourceError("missing/extra raw response body")
    wire_sum = decoded_sum = 0
    for page, row, meta in zip(chosen, candidate["series"], receipt["sources"]):
        exact(meta, ("project", "page_id", "subject", "raw_member", "wire_bytes",
                     "wire_sha256", "content_encoding", "endpoint", "requested_at",
                     "http_status", "body_sha256", "response_bytes"), "source receipt")
        name = f"{page['project']}.{page['page_id']}.json"
        if ({k: page[k] for k in ("project", "page_id", "title")} !=
                {k: row[k] for k in ("project", "page_id", "title")} or
                meta["project"] != page["project"] or meta["page_id"] != page["page_id"] or
                meta["subject"] != page["subject"] or meta["raw_member"] != "raw/" + name or
                {k: meta[k] for k in ("endpoint", "requested_at", "http_status", "body_sha256", "response_bytes")} != row["source"]):
            raise SourceError("seed, source, and candidate identity/receipt mismatch")
        raw = _bytes(raw_dir / name, MAX_BODY)
        if sha(raw) != row["source"]["body_sha256"] or len(raw) != row["source"]["response_bytes"]:
            raise SourceError("retained raw-body size/hash mismatch")
        parsed = parse_pageviews(raw, page, expected_start, day(candidate["observation_end"]))
        if parsed != row["daily"]:
            raise SourceError("candidate observations differ from retained body")
        size, digest, enc = meta["wire_bytes"], meta["wire_sha256"], meta["content_encoding"]
        if (type(size) is not int or not 0 < size <= MAX_BODY or type(digest) is not str or
                HEX.fullmatch(digest) is None or enc not in ("identity", "gzip")):
            raise SourceError("invalid wire receipt")
        if enc == "identity" and (size != len(raw) or digest != sha(raw)):
            raise SourceError("inconsistent identity wire receipt")
        wire_sum += size
        decoded_sum += len(raw)
    if (type(receipt["total_wire_bytes"]) is not int or receipt["total_wire_bytes"] != wire_sum or
            type(receipt["total_decoded_bytes"]) is not int or receipt["total_decoded_bytes"] != decoded_sum or
            wire_sum > MAX_TOTAL or decoded_sum > MAX_TOTAL):
        raise SourceError("aggregate source byte counts inconsistent")
    return {"result": "all_retained_bodies_internally_consistent",
            "candidate_sha256": sha(candidate_raw), "seed_sha256": sha(seed_raw),
            "series": len(chosen), "observations": DAYS * len(chosen),
            "provenance_status": receipt["provenance_status"],
            "publication_status": "NOT_PUBLISHED",
            "limitation": "Hashes and retained bodies do not independently authenticate Wikimedia origin, title/page-ID history or license."}


def _atomic_new_dir(source: Path, target: Path):
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        func = getattr(libc, "renameat2", None)
        if func is None:
            raise SourceError("atomic no-replace directory operation not available")
        func.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        func.restype = ctypes.c_int
        if func(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(target))
    elif os.name == "nt":
        os.rename(source, target)
    else:
        raise SourceError("no supported atomic no-replace directory operation")


def collect_to_new_directory(seed_path: Path, out: Path, *, fetch=fetch_once, now=None, sleep=time.sleep,
                             injected=False):
    seed_raw = _bytes(Path(seed_path), MAX_SEED_BYTES)
    seed = strict_json(seed_raw, "seed", max_bytes=MAX_SEED_BYTES)
    out = Path(out)
    if out.exists() or out.is_symlink():
        raise SourceError("evidence destination already exists; refusing overwrite")
    candidate, receipt, bodies = build(seed, fetch=fetch, now=now, sleep=sleep, injected=injected)
    if not out.parent.is_dir() or out.parent.is_symlink():
        raise SourceError("evidence parent directory must preexist and be real")
    with tempfile.TemporaryDirectory(prefix=".dayflare-rolling-", dir=out.parent) as location:
        root = Path(location)
        (root / "raw").mkdir()
        (root / "candidate.json").write_bytes(canonical(candidate))
        (root / "source-receipt.json").write_bytes(canonical(receipt))
        (root / "seeds.json").write_bytes(canonical(seed))
        for name, raw in sorted(bodies.items()):
            (root / "raw" / name).write_bytes(raw)
        verify_bundle(root, now=_now((now or (lambda: datetime.now(timezone.utc)))()))
        _atomic_new_dir(root, out)
    return verify_bundle(out, now=_now((now or (lambda: datetime.now(timezone.utc)))()))


def stage_verified_bundle(bundle: Path, staging: Path, *, now=None):
    """Offline review of raw source bodies before existing LOCAL-only staging."""
    proof = verify_bundle(bundle, now=now)
    # A fixture can be internally consistent yet explicitly synthetic. Do not
    # launder that label into the stage's generic self-reported provenance.
    if proof["provenance_status"] != "runtime_reported_transport_not_independently_authenticated":
        raise SourceError("synthetic/test source cannot advance local rolling staging")
    from .stage_rolling_version import stage
    # Stage only the exact candidate bytes checked against the retained bodies.
    # A second unchecked read could promote a swapped, still-schema-valid file.
    candidate_bytes = _bytes(Path(bundle) / "candidate.json", MAX_BYTES)
    if sha(candidate_bytes) != proof["candidate_sha256"]:
        raise SourceError("candidate changed after source verification; no staging")
    doc = strict_json(candidate_bytes, "candidate", max_bytes=MAX_BYTES)
    # The immutable v2 stage retains and replays these source bytes under its
    # own digest-bound version, even if this external bundle is later removed.
    result = stage(doc, staging, now=now, source_bundle=Path(bundle))
    return {"source_bundle": proof, "local_stage": result}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="command", required=True)
    a = sp.add_parser("collect"); a.add_argument("seeds", type=Path); a.add_argument("out", type=Path)
    b = sp.add_parser("verify"); b.add_argument("bundle", type=Path)
    c = sp.add_parser("stage"); c.add_argument("bundle", type=Path); c.add_argument("stage_root", type=Path)
    args = p.parse_args(argv)
    try:
        if args.command == "collect":
            result = collect_to_new_directory(args.seeds, args.out)
        elif args.command == "verify":
            result = verify_bundle(args.bundle)
        else:
            result = stage_verified_bundle(args.bundle, args.stage_root)
    except (SourceError, WindowError, ValueError, OSError) as exc:
        print(f"NO_PUBLICATION: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
