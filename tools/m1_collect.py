"""Bounded, one-shot EN/RU Wikipedia article-identity evidence collection.

This is a deliberately narrow metadata probe, NOT a pageview signal collector.
No Wikimedia content is fetched, no original publication is overwritten, and no
upstream transport is asserted by purely synthetic/offline tests.
"""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
from http.client import IncompleteRead
import json
import os
import sys
from pathlib import Path
from collections import Counter
import tempfile
import time
import zlib
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .m1_identity_panel import (
    MAX_PAGES, PanelError, PROJECTS, RELATIONS, SUBJECTS, TOPIC, QID,
    bounded_text, canonical_bytes, date_value, exact_keys, page_ref,
    require, validate_panel,
)
from .m1_source_verify import MAX_BODY, MAX_TOTAL, parse_response, verify_sources
from .m1_bundle_verify import make_manifest, verify_bundle

SEED_SCHEMA = "dayflare.identity-seeds.v1"
COLLECTION_SCHEMA = "dayflare.identity-collection.v2"
USER_AGENT = "DayflareIdentity/0.2 (https://github.com/drevendev/Dayflare) Python-urllib"
MAX_SEED_BYTES = 32 * 1024
MAX_IDENTITY_CALLS = 30  # tighter than validator cap; explicitly curated probe
MIN_SPACING_SECONDS = 2.0
# Wikimedia Action API robot policy: wait five seconds if a call takes >1s
# to serve. Include client/network time in this conservative measurement.
SLOW_ACTION_API_SECONDS = 1.0
SLOW_ACTION_API_PAUSE_SECONDS = 5.0
TIMEOUT_SECONDS = 10


class CollectionFailure(RuntimeError):
    """Transient/provider/budget failure: abort without replacing published files."""


@dataclass(frozen=True)
class HTTPResult:
    """Decoded JSON entity plus measured HTTP representation metadata.

    Wire bodies are not retained: wire hash/count are transport observations,
    not independently authenticated evidence. Source hashes bind decoded bytes.
    """
    status: int
    body: bytes
    wire_bytes: int
    wire_sha256: str
    content_encoding: str


def decode_http_body(wire: bytes, encoding: str) -> bytes:
    """Bound gzip inflation, require CRC/EOF, reject additional members/data."""
    if not 0 < len(wire) <= MAX_BODY:
        raise CollectionFailure("empty or over-budget wire response")
    if encoding == "identity":
        return wire
    if encoding != "gzip":
        raise CollectionFailure("unsupported Content-Encoding")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        body = decoder.decompress(wire, MAX_BODY + 1)
    except zlib.error as exc:
        raise CollectionFailure("corrupt gzip response") from exc
    if len(body) > MAX_BODY or decoder.unconsumed_tail:
        raise CollectionFailure("over-budget decoded response")
    if not body or not decoder.eof or decoder.unused_data:
        raise CollectionFailure("incomplete or trailing gzip response")
    return body


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def wiki_endpoint(project: str, page_id: int) -> str:
    require(project in PROJECTS and type(page_id) is int and page_id > 0,
            "$.page_ref", "unsupported page identity")
    return "https://" + project + ".org/w/api.php?" + urlencode({
        "action": "query", "format": "json", "formatversion": "2",
        "prop": "info|pageprops", "ppprop": "wikibase_item", "pageids": str(page_id),
    })


def validate_seed(seed: object) -> dict:
    obj = exact_keys(seed, "$", {"schema_version", "panel_id", "selected_at", "pages"})
    require(obj["schema_version"] == SEED_SCHEMA, "$.schema_version", "wrong seed version")
    bounded_text(obj["panel_id"], "$.panel_id", 120)
    require(TOPIC.fullmatch(obj["panel_id"]) is not None, "$.panel_id", "invalid slug")
    date_value(obj["selected_at"], "$.selected_at")
    require(obj["selected_at"] <= datetime.now(timezone.utc).date().isoformat(),
            "$.selected_at", "future selection date")
    rows = obj["pages"]
    require(type(rows) is list and 1 <= len(rows) <= min(MAX_PAGES, MAX_IDENTITY_CALLS),
            "$.pages", "requires 1..30 explicitly curated identities")
    refs = set()
    for i, entry in enumerate(rows):
        p = f"$.pages[{i}]"
        exact_keys(entry, p, {"page_ref", "topic_id", "subject", "relation"})
        ref = page_ref(entry["page_ref"], p + ".page_ref")
        require(ref not in refs, p, "duplicate identity")
        refs.add(ref)
        bounded_text(entry["topic_id"], p + ".topic_id", 120)
        require(TOPIC.fullmatch(entry["topic_id"]) is not None, p + ".topic_id", "invalid topic ID")
        require(type(entry["subject"]) is str and entry["subject"] in SUBJECTS,
                p + ".subject", "unsupported subject")
        require(type(entry["relation"]) is str and entry["relation"] in RELATIONS,
                p + ".relation", "unsupported relation")
    return obj


def decode_current_page(raw: bytes, project: str, page_id: int) -> tuple[str, str | None]:
    """Read candidate fields, then validate entire raw body with strict verifier.

    Candidate extraction is not trusted: `parse_response` detects duplicate keys,
    alternate identities, redirects, missing pages and malformed namespace/QIDs.
    """
    try:
        value = json.loads(raw.decode("utf-8"))
        entry = value["query"]["pages"][0]
        title = entry["title"]
        props = entry.get("pageprops", {})
        observed_qid = props.get("wikibase_item")
    except (UnicodeDecodeError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise PanelError("$.raw: malformed or incomplete Action API identity body") from None
    parse_response(raw, project, page_id, title, observed_qid)
    bounded_text(title, "$.raw.query.pages[0].title", 255)
    require(observed_qid is None or (type(observed_qid) is str and QID.fullmatch(observed_qid) is not None),
            "$.raw.query.pages[0].pageprops.wikibase_item", "invalid QID")
    return title, observed_qid


def _fetch_once(url: str) -> HTTPResult:
    """One standard-library GET, with all redirects rejected and bounded bytes."""
    request = Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "gzip",
    }, method="GET")
    opener = build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            if status != 200:
                raise CollectionFailure(f"HTTP {status} from upstream; no retry")
            # urllib does not guarantee that a declared Content-Length was actually
            # delivered. A prematurely closed HTTP 200 must not receive a complete
            # source hash or become a publishable identity receipt.
            declared = None
            header_length = response.headers.get("Content-Length")
            if header_length is not None:
                if not header_length.isascii() or not header_length.isdecimal() or len(header_length) > 7 or (len(header_length) > 1 and header_length[0] == "0"):
                    raise CollectionFailure("invalid Content-Length")
                declared = int(header_length)
                if declared <= 0 or declared > MAX_BODY:
                    raise CollectionFailure("empty or over-budget Content-Length")
            content_type = response.headers.get_content_type()
            if content_type not in ("application/json", "application/vnd.mediawiki.api+json"):
                raise CollectionFailure("unexpected Content-Type: " + content_type)
            body = response.read(MAX_BODY + 1)
            if not 0 < len(body) <= MAX_BODY:
                raise CollectionFailure("empty or over-budget response")
            if declared is not None and len(body) != declared:
                raise CollectionFailure("incomplete or excess HTTP body vs Content-Length")
            encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
            encoding = encoding or "identity"
            entity = decode_http_body(body, encoding)
            return HTTPResult(status, entity, len(body), hashlib.sha256(body).hexdigest(), encoding)
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        suffix = f"; Retry-After={retry_after}" if retry_after else ""
        raise CollectionFailure(f"HTTP {exc.code} from upstream{suffix}; no retry or fallback") from exc
    except IncompleteRead as exc:
        raise CollectionFailure("incomplete upstream HTTP body") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise CollectionFailure("network failure: " + type(exc).__name__) from exc


def collect(seed: dict, fetch=_fetch_once, now=None, sleep=time.sleep) -> tuple[dict, dict, dict[str, bytes]]:
    """Collect in memory; caller publishes only after complete validation.

    `fetch` returns HTTPResult. Offline injections may return (status, entity)
    tuples, explicitly interpreted as identity representation. 429/5xx/network/budget errors abort; other
    bad identities are counted explicitly as unavailable, never as zero views.
    """
    seed = validate_seed(seed)
    now = now or (lambda: datetime.now(timezone.utc))
    entries = sorted(seed["pages"], key=lambda x: (x["page_ref"]["project"], x["page_ref"]["page_id"]))
    pages, attempts, bodies = [], [], {}
    transferred_bytes = 0
    decoded_bytes = 0
    retained_bytes = 0
    next_pause = MIN_SPACING_SECONDS
    previous_requested = None
    for i, entry in enumerate(entries):
        if i:
            sleep(next_pause)
        project, pid = entry["page_ref"]["project"], entry["page_ref"]["page_id"]
        endpoint = wiki_endpoint(project, pid)
        requested = now()
        require(isinstance(requested, datetime) and requested.tzinfo is not None and requested.utcoffset() is not None and requested.utcoffset().total_seconds() == 0,
                "$.clock", "UTC-aware clock required")
        # Selection must predate (or coincide with) retrieval. Never put a
        # provenance-impossible identity observation into a public bundle.
        require(requested.date().isoformat() >= seed["selected_at"],
                "$.clock", "retrieval predates curated selection")
        require(previous_requested is None or requested >= previous_requested,
                "$.clock", "retrieval timestamps moved backward; abort before the next request")
        previous_requested = requested
        timestamp = requested.isoformat(timespec="seconds").replace("+00:00", "Z")
        started = time.monotonic()
        try:
            result = fetch(endpoint)
            if isinstance(result, HTTPResult):
                status, raw = result.status, result.body
                wire_bytes, wire_sha = result.wire_bytes, result.wire_sha256
                encoding = result.content_encoding
            else:
                # Legacy test injection: unencoded entity, never proof of HTTP.
                status, raw = result
                wire_bytes = len(raw) if type(raw) is bytes else 0
                wire_sha = hashlib.sha256(raw).hexdigest() if type(raw) is bytes else ""
                encoding = "identity"
        except CollectionFailure:
            raise
        except (TimeoutError, OSError) as exc:
            raise CollectionFailure(f"network failure for {project}:{pid}: {type(exc).__name__}") from exc
        elapsed = time.monotonic() - started
        if not math.isfinite(elapsed) or elapsed < 0:
            raise CollectionFailure("invalid monotonic request duration; no next request")
        next_pause = (SLOW_ACTION_API_PAUSE_SECONDS if elapsed > SLOW_ACTION_API_SECONDS
                      else MIN_SPACING_SECONDS)
        require(type(status) is int and 100 <= status <= 599 and type(raw) is bytes,
                "$.transport", "invalid transport result")
        if status != 200:
            # Fail closed; caller must respect any provider Retry-After before
            # independently scheduling a new bounded attempt. No auto-retry.
            raise CollectionFailure(f"HTTP {status} from {project}:{pid}; stop collection; respect provider Retry-After before a future attempt")
        if not 0 < len(raw) <= MAX_BODY:
            raise CollectionFailure(f"oversized or empty body for {project}:{pid}")
        require(type(wire_bytes) is int and 0 < wire_bytes <= MAX_BODY
                and encoding in {"identity", "gzip"} and type(wire_sha) is str
                and len(wire_sha) == 64 and all(c in "0123456789abcdef" for c in wire_sha),
                "$.transport", "invalid wire representation metadata")
        if encoding == "identity":
            require(wire_bytes == len(raw) and wire_sha == hashlib.sha256(raw).hexdigest(),
                    "$.transport", "identity wire/entity mismatch")
        ref = entry["page_ref"]
        attempt = {"page_ref": ref, "topic_id": entry["topic_id"],
                   "subject": entry["subject"], "relation": entry["relation"],
                   "requested_at": timestamp, "http_status": status,
                   "endpoint": endpoint, "status": "unavailable",
                   "wire_bytes": wire_bytes, "wire_sha256": wire_sha, "content_encoding": encoding}
        transferred_bytes += wire_bytes
        decoded_bytes += len(raw)
        if transferred_bytes > MAX_TOTAL or decoded_bytes > MAX_TOTAL:
            raise CollectionFailure("combined wire or decoded-source size exceeds 8 MiB")
        digest = hashlib.sha256(raw).hexdigest()
        try:
            title, qid = decode_current_page(raw, project, pid)
        except PanelError:
            attempt["reason"] = "invalid_or_missing_identity"
            attempt["response_bytes"] = len(raw)
            attempt["body_sha256"] = digest
            attempts.append(attempt)
            continue
        page = {
            "page_ref": ref, "topic_id": entry["topic_id"], "subject": entry["subject"],
            "relation": entry["relation"], "titles": [{"date": requested.date().isoformat(),
                "title": title, "source_url": endpoint}], "events": [],
            "continuity": "ambiguous", "redirect_to": None,
            "wikidata": {"state": "observed" if qid else "missing",
                         "observed_qid": qid, "resolved_qid": None,
                         "evidence_url": (f"https://www.wikidata.org/wiki/{qid}" if qid else None)},
            "source": {"endpoint": endpoint, "requested_at": timestamp, "http_status": 200,
                       "body_sha256": digest, "response_bytes": len(raw)},
        }
        pages.append(page)
        bodies[f"{project}.{pid}.json"] = raw
        retained_bytes += len(raw)
        attempt.update(status="retained", body_sha256=digest, response_bytes=len(raw))
        attempts.append(attempt)
    panel = {"schema_version": "dayflare.identity-panel.v1", "panel_id": seed["panel_id"],
             "selection": {"method": "curated", "selected_at": seed["selected_at"],
                           "intended_count": len(entries), "evidence_kind": "reported_retrieval"},
             "pages": pages}
    if not pages:
        raise CollectionFailure("no valid identities retained; nothing publishable")
    normalized = validate_panel(panel)
    intended_cells = Counter((row["page_ref"]["project"], row["subject"]) for row in entries)
    intended_by_cell = {}
    for (project, subject), count in sorted(intended_cells.items()):
        intended_by_cell.setdefault(project, {})[subject] = count
    report = {"schema_version": COLLECTION_SCHEMA, "panel_id": seed["panel_id"],
              "selected_at": seed["selected_at"], "intended_count": len(entries),
              "retained_count": len(pages), "unavailable_count": len(entries) - len(pages),
              "transferred_bytes": transferred_bytes, "decoded_bytes": decoded_bytes,
              "body_representation": "decoded-json-entity", "retained_bytes": retained_bytes,
              "requests_attempted": len(attempts),
              "intended_by_edition_subject": intended_by_cell,
              "obtained_by_edition_subject": normalized["coverage"]["observed_panel_counts_by_edition_subject"],
              "attempts": attempts,
              "limitations": [
                  "Selection is curated, not representative; missing identities are not zero views.",
                  "Only current page-ID/title/observed-QID metadata; no histories or pageview counts.",
                  "Standalone receipts and bytes must be independently checked for authentic provider origin.",
                  "Source hashes and response_bytes bind decoded JSON entities, not compressed wire bodies.",
                  "Wire hashes/counts are recorded transport observations; wire bodies are not retained.",
              ]}
    return normalized, report, bodies



def _rename_directory_no_replace(source: Path, target: Path) -> None:
    """Atomically expose a complete bundle, never replacing an existing path.

    Linux rename(2) normally *replaces an empty destination directory*, even
    after a successful `target.exists()` preflight. That check is not an atomic
    publication guard. Use renameat2(RENAME_NOREPLACE) on the target Ubuntu
    runtime and fail closed where that primitive is unavailable. Windows
    os.rename() already refuses an existing destination.
    """
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise CollectionFailure("atomic no-replace directory promotion unavailable")
        renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_uint)
        renameat2.restype = ctypes.c_int
        if renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(target))
        return
    if os.name == "nt":
        os.rename(source, target)
        return
    raise CollectionFailure("atomic no-replace directory promotion unavailable")

def collect_to_new_directory(seed_path: Path, out: Path, fetch=_fetch_once, now=None, sleep=time.sleep) -> dict:
    """All-or-nothing unique output. Do not replace prior successful publication."""
    if out.exists():
        raise CollectionFailure(f"destination already exists, refusing overwrite: {out}")
    raw_seed = seed_path.read_bytes()
    if len(raw_seed) > MAX_SEED_BYTES:
        raise PanelError("$.seeds: seed exceeds 32 KiB")
    def no_duplicate_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise PanelError("$.seeds: duplicate JSON field: " + key)
            value[key] = item
        return value
    seed = json.loads(raw_seed.decode("utf-8"), object_pairs_hook=no_duplicate_keys)
    panel, report, bodies = collect(seed, fetch=fetch, now=now, sleep=sleep)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dayflare-identity-", dir=out.parent) as temp_path:
        root = Path(temp_path)
        raw_dir = root / "raw"
        raw_dir.mkdir()
        # Coverage is a derived validator output, not a field in the strict
        # input panel schema that the existing source verifier reads.
        raw_panel = {key: panel[key] for key in ("schema_version", "panel_id", "selection", "pages")}
        (root / "panel.json").write_bytes(canonical_bytes(raw_panel))
        (root / "collection-report.json").write_bytes(canonical_bytes(report))
        for name, body in sorted(bodies.items()):
            (raw_dir / name).write_bytes(body)
        proof = verify_sources(root / "panel.json", raw_dir)
        (root / "internal-consistency.json").write_bytes(canonical_bytes(proof))
        (root / "bundle-manifest.json").write_bytes(canonical_bytes(make_manifest(root, raw_panel)))
        verify_bundle(root)
        # Atomic promotion must refuse even a destination created *after* the
        # preflight check (including an existing empty directory).
        _rename_directory_no_replace(root, out)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seed", type=Path, help="curated seed identities (no titles or article text)")
    parser.add_argument("out", type=Path, help="new, unique output directory; must not exist")
    args = parser.parse_args(argv)
    try:
        receipt = collect_to_new_directory(args.seed, args.out)
    except (PanelError, CollectionFailure, OSError, ValueError, UnicodeDecodeError) as exc:
        parser.exit(2, f"COLLECTION_NOT_PUBLISHED: {exc}\n")
    print(json.dumps({"out": str(args.out), "retained": receipt["retained_count"],
                     "unavailable": receipt["unavailable_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
