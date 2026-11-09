"""Create, verify and unpack a bounded, source-retaining identity evidence capsule.

Offline only. Reuses the accepted D03/source/bundle gates; matching hashes prove
internal agreement, NOT Wikimedia origin. Never retrieves or publishes anything.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from zipfile import BadZipFile, ZIP_STORED, ZipFile, ZipInfo

from .m1_bundle_verify import ROOT_MEMBERS, verify_bundle
from .m1_identity_panel import PanelError, canonical_bytes, load_panel

SCHEMA = "dayflare.identity-capsule.v1"
MAX_IDENTITIES = 20
MAX_MEMBER = 1024 * 1024
MAX_SOURCE = 9 * 1024 * 1024
MAX_ARCHIVE = 12 * 1024 * 1024
MAX_MEMBERS = MAX_IDENTITIES + 6
SOURCE_NAMES = frozenset("source/" + n for n in ROOT_MEMBERS if n != "raw")
RAW_NAME = re.compile(r"source/raw/(?:en|ru)\.wikipedia\.[1-9][0-9]{0,15}\.json\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")
RUN = re.compile(r"https://github\.com/drevendev/Dayflare/actions/runs/[1-9][0-9]{0,19}\Z")
KINDS = {"reported_retrieval", "synthetic_test_fixture"}
SUBJECT_ORDER = ("culture", "books", "games", "science", "sport", "other")
PAGE_FIELDS = {"pageid", "ns", "title", "contentmodel", "pagelanguage",
               "pagelanguagehtmlcode", "pagelanguagedir", "touched", "lastrevid",
               "length", "pageprops"}
RIGHTS = ("Metadata only; article text and images are excluded. Wikidata structured "
          "identifiers are CC0. This does not license Wikipedia article content.")


class CapsuleError(ValueError):
    """An invalid or incomplete capsule must not replace accepted evidence."""


def need(condition: bool, message: str) -> None:
    if not condition:
        raise CapsuleError(message)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: bytes) -> dict:
    need(type(raw) is bytes and 0 < len(raw) <= MAX_MEMBER, "empty or oversized JSON")
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "duplicate JSON field: " + key)
            result[key] = value
        return result

    def bad_constant(value):
        raise CapsuleError("nonfinite JSON: " + value)

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=bad_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CapsuleError("invalid or excessively nested JSON") from exc
    need(type(value) is dict, "JSON root must be an object")
    # Do not rely on the embedding interpreter's adjustable recursion limit.
    pending, visited = [(value, 0)], 0
    while pending:
        node, depth = pending.pop()
        visited += 1
        need(depth <= 32 and visited <= 20000, "JSON nesting or node budget exceeded")
        need(type(node) is not float or math.isfinite(node), "nonfinite JSON number")
        children = node.values() if type(node) is dict else node if type(node) is list else ()
        pending.extend((child, depth + 1) for child in children)
    return value


def member_limit(name: str) -> int:
    if name in {"capsule.json", "source/bundle-manifest.json"}:
        return 32 * 1024
    if name in SOURCE_NAMES:
        return 256 * 1024
    return MAX_MEMBER


def check_inventory(files: dict[str, bytes]) -> None:
    need(SOURCE_NAMES <= files.keys(), "missing source bundle files")
    need(len(files) <= MAX_IDENTITIES + 4, "too many source members")
    need(all(n in SOURCE_NAMES or RAW_NAME.fullmatch(n) for n in files),
         "unlisted source path or invalid identity filename")
    need(all(type(b) is bytes and 0 < len(b) <= member_limit(n) for n, b in files.items()),
         "empty or oversized source member")
    need(sum(map(len, files.values())) <= MAX_SOURCE, "source byte budget exceeded")


def read_regular(path: Path, limit: int) -> bytes:
    # Reject linked ancestors as well as final links. O_NOFOLLOW closes the final
    # file race where supported; fstat rejects pipes/devices before any read.
    need(not any(p.is_symlink() for p in (path, *path.parents)), "linked source path")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        need(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "expected regular file")
        raw = stream.read(limit + 1)
    need(0 < len(raw) <= limit, "empty or oversized file")
    return raw


def snapshot_directory(root: Path) -> dict[str, bytes]:
    root = Path(root).absolute()
    need(root.is_dir() and not any(p.is_symlink() for p in (root, *root.parents)),
         "missing or linked bundle directory")
    members = set()
    for number, child in enumerate(root.iterdir(), 1):
        need(number <= len(ROOT_MEMBERS), "too many bundle members")
        members.add(child.name)
    need(members == ROOT_MEMBERS, "unlisted or missing bundle member")
    raw = root / "raw"
    need(raw.is_dir() and not raw.is_symlink(), "missing or linked raw directory")
    names = sorted("source/" + n for n in ROOT_MEMBERS if n != "raw")
    # Bound iteration too; do not materialize an attacker-controlled huge tree.
    for number, child in enumerate(raw.iterdir(), 1):
        need(number <= MAX_IDENTITIES, "more than 20 retained identity bodies")
        name = "source/raw/" + child.name
        need(RAW_NAME.fullmatch(name) is not None, "invalid raw filename")
        names.append(name)
    files = {n: read_regular(root / n.removeprefix("source/"), member_limit(n)) for n in names}
    check_inventory(files)
    return files


def metadata_only(raw: bytes) -> None:
    """Conservative content boundary for the exact info|pageprops endpoint.

    Unknown fields require a deliberate review rather than accidentally retaining
    article extracts, revisions, images, executable content or arbitrary payloads.
    """
    body = strict_json(raw)
    need(set(body) == {"batchcomplete", "query"}, "unreviewed response root fields")
    query = body["query"]
    need(type(query) is dict and set(query) == {"pages"}, "unreviewed query fields")
    pages = query["pages"]
    need(type(pages) is list and len(pages) == 1 and type(pages[0]) is dict,
         "expected one metadata page")
    page = pages[0]
    need(set(page) <= PAGE_FIELDS, "article content or unreviewed page field")
    props = page.get("pageprops", {})
    need(type(props) is dict and set(props) <= {"wikibase_item"}, "unreviewed page properties")
    for key, value in page.items():
        if key == "pageprops":
            continue
        need(type(value) in (str, int), "unreviewed metadata value type")
        if type(value) is str:
            need(len(value) <= 512, "oversized metadata string")


def validate_source(files: dict[str, bytes]) -> tuple[dict, dict]:
    """Validate the FROZEN bytes, never a directory that can change after checking."""
    check_inventory(files)
    # Apply the capsule's stricter encoding/depth/number contract to EVERY frozen
    # source member before legacy validators interpret it or any bytes are staged.
    for raw in files.values():
        strict_json(raw)
    with tempfile.TemporaryDirectory(prefix="dayflare-capsule-check-") as temp:
        root = Path(temp)
        (root / "raw").mkdir()
        for name, raw in files.items():
            (root / name.removeprefix("source/")).write_bytes(raw)
        try:
            verify_bundle(root)
            panel = load_panel(root / "panel.json")
        except (PanelError, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            raise CapsuleError("invalid source bundle: " + str(exc)) from exc
    report = strict_json(files["source/collection-report.json"])
    need(panel["selection"]["intended_count"] <= MAX_IDENTITIES, "selection exceeds 20 identities")
    days = {datetime.fromisoformat(a["requested_at"].replace("Z", "+00:00"))
            .astimezone(timezone.utc).date().isoformat() for a in report["attempts"]}
    need(len(days) == 1, "one complete UTC observation date required; split midnight collections")
    for name, raw in files.items():
        if RAW_NAME.fullmatch(name):
            metadata_only(raw)
    return panel, report


def receipt_for(files: dict[str, bytes], panel: dict, report: dict, *,
                source_revision: str, source_run_url: str | None, evidence_kind: str) -> dict:
    need(type(source_revision) is str and REVISION.fullmatch(source_revision) is not None,
         "exact 40-character source revision required")
    need(source_run_url is None or (type(source_run_url) is str and RUN.fullmatch(source_run_url)),
         "source run must be a Dayflare GitHub Actions run")
    need(type(evidence_kind) is str and evidence_kind in KINDS, "explicit evidence kind required")
    marked_fixture = panel["panel_id"].startswith("synthetic.") or any(
        type(item) is str and "SYNTHETIC TEST FIXTURE" in item for item in report["limitations"])
    need(not marked_fixture or evidence_kind == "synthetic_test_fixture",
         "marked synthetic source cannot be relabelled as reported retrieval")
    requested = sorted(datetime.fromisoformat(a["requested_at"].replace("Z", "+00:00"))
                       .astimezone(timezone.utc) for a in report["attempts"])
    times = [value.isoformat().replace("+00:00", "Z") for value in requested]
    return {
        "schema_version": SCHEMA, "panel_id": panel["panel_id"],
        "evidence_kind": evidence_kind, "source_revision": source_revision,
        "source_run_url": source_run_url, "network_origin_verified": False,
        "status": "OFFLINE_CAPSULE_NOT_PUBLISHED", "observation_date_utc": times[0][:10],
        "first_request_started_at_utc": times[0], "last_request_started_at_utc": times[-1],
        "retrieval_completed_at_utc": None,
        "selection_date": panel["selection"]["selected_at"],
        "intended_count": report["intended_count"], "retained_count": report["retained_count"],
        "unavailable_count": report["unavailable_count"], "rights_scope": RIGHTS,
        "source_files": {n: {"bytes": len(b), "sha256": digest(b)} for n, b in sorted(files.items())},
    }


STYLE = """
:root{color-scheme:light;--ink:#192b36;--muted:#465c67;--paper:#f5f3ed;--line:#c9d2d5;--accent:#863d1b}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.6 system-ui,sans-serif}
main,header,footer{width:min(1100px,calc(100% - 36px));margin:auto;overflow-wrap:anywhere}
header{padding:42px 0 24px}h1{font-size:clamp(2rem,5vw,3.7rem);line-height:1.08;letter-spacing:-.04em;max-width:20ch}
h2{font-size:1.55rem}h3{margin:.3em 0}p{max-width:75ch}.eyebrow{text-transform:uppercase;letter-spacing:.13em;font-size:.8rem}
a{color:#164e73;text-underline-offset:.2em}a:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:3px solid #a44413;outline-offset:4px}
nav{display:flex;flex-wrap:wrap;gap:12px}nav a,.action{display:inline-block;padding:10px 14px;border:1px solid var(--line);border-radius:8px;background:white;min-height:44px}
.notice{border-left:5px solid var(--accent);background:#fff3d7;padding:14px 18px}.muted{color:var(--muted)}
.stats,.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,270px),1fr));gap:16px}
.stat,article{background:white;border:1px solid var(--line);border-radius:12px;padding:20px;min-width:0}
.stat strong{display:block;font-size:1.6rem}.cards article h3{font-size:1.4rem}section{margin:30px 0}article{scroll-margin-top:18px}
code{font-size:.88em;overflow-wrap:anywhere}dl{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr);gap:8px;margin:16px 0}
dt{color:var(--muted)}dd{margin:0;min-width:0}summary{cursor:pointer;padding:10px 0;min-height:44px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;min-width:0;font-size:.8rem;background:#f1f4f5;padding:12px;border-radius:6px}
table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:.92rem}th,td{padding:10px 6px;border-bottom:1px solid var(--line);text-align:left;overflow-wrap:anywhere}
caption{text-align:left;padding:10px 0;color:var(--muted)}footer{padding:30px 0}.skip{position:absolute;left:12px;top:-100px;background:white;padding:12px;z-index:1}.skip:focus{top:10px}
@media(max-width:400px){body{font-size:16px}header{padding-top:28px}dl{grid-template-columns:1fr}dd{margin-bottom:8px}}
"""


def render(panel: dict, report: dict, receipt: dict, files: dict[str, bytes]) -> bytes:
    e = lambda value: escape(str(value), quote=True)
    synthetic = receipt["evidence_kind"] == "synthetic_test_fixture"
    badge = "SYNTHETIC TEST FIXTURE — NOT WIKIPEDIA OBSERVATIONS" if synthetic else "REPORTED RETRIEVAL — UPSTREAM ORIGIN NOT AUTHENTICATED"
    cells = []
    for subject in SUBJECT_ORDER:
        if not any(subject in report["intended_by_edition_subject"].get(p, {}) for p in ("en.wikipedia", "ru.wikipedia")):
            continue
        values = []
        for project in ("en.wikipedia", "ru.wikipedia"):
            intended = report["intended_by_edition_subject"].get(project, {}).get(subject)
            obtained = report["obtained_by_edition_subject"].get(project, {}).get(subject, 0)
            values.append("Not selected" if intended is None else f"{obtained} / {intended}")
        cells.append(f"<tr><th scope='row'>{e(subject.title())}</th><td>{values[0]}</td><td>{values[1]}</td></tr>")
    collisions = {
        (item["project"], item["qid"])
        for field in ("non_1_to_1_observed_qid_collisions", "non_1_to_1_local_qid_collisions")
        for item in panel["coverage"][field]
    }
    source_fingerprint = digest(files["source/bundle-manifest.json"])
    cards = []
    for row in panel["pages"]:
        project, pid = row["page_ref"]["project"], row["page_ref"]["page_id"]
        anchor = f"identity-{source_fingerprint}-{project}-{pid}"
        raw_name = f"source/raw/{project}.{pid}.json"
        observed = row["titles"][-1]
        source = row["source"]
        mapping = row["wikidata"]
        collision = any((project, mapping[field]) in collisions for field in ("observed_qid", "resolved_qid"))
        warning = '<p class="notice">Non-1:1 QID mapping in this edition: multiple selected identities share this identifier. Equivalence remains unresolved.</p>' if collision else ''
        cards.append(f"""<article id="{anchor}" tabindex="-1">
<p class="eyebrow">{e(project)} · {e(row['subject'])}</p><h3>{e(observed['title'])}</h3>
<p><code>{e(project)}:{pid}</code> · <a href="#{anchor}">Link to this identity</a></p>
<dl><dt>Observed on</dt><dd>{e(observed['date'])} UTC</dd><dt>Observed QID</dt><dd>{e(mapping['observed_qid'] or 'Unavailable')}</dd>
<dt>Resolved QID</dt><dd>{e(mapping['resolved_qid'] or 'Not resolved')}</dd><dt>Mapping state</dt><dd>{e(mapping['state'])}</dd>
<dt>Continuity</dt><dd>{e(row['continuity'])}; not established by this snapshot</dd></dl>{warning}
<p><a class="action" href="{raw_name}">Retained source JSON</a> <a class="action" href="{e(source['endpoint'])}">Original request URL</a></p>
<details><summary>Exact source evidence for {e(project)}:{pid}</summary>
<p>Requested at {e(source['requested_at'])}; HTTP {source['http_status']}; {source['response_bytes']} decoded bytes.</p>
<p>SHA-256 <code>{e(source['body_sha256'])}</code></p><pre>{e(files[raw_name].decode('utf-8'))}</pre></details></article>""")
    failures = [a for a in report["attempts"] if a["status"] == "unavailable"]
    unavailable = "" if not failures else "<section><h2>Unavailable selected identities</h2><p>These are not deletions or zero interest. Their raw bodies were not retained by the collector.</p><ul>" + "".join(
        f"<li><code>{e(a['page_ref']['project'])}:{a['page_ref']['page_id']}</code> — {e(a['reason'])}</li>" for a in failures) + "</ul></section>"
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Dayflare · Identity evidence · {e(receipt['observation_date_utc'])}</title><style>{STYLE}</style></head><body>
<a class="skip" href="#identities">Skip to observed identities</a><header><p class="eyebrow">Dayflare / source-retaining snapshot</p>
<h1>Inspect the evidence behind a page identity.</h1><p>Explore the retained English and Russian Wikipedia metadata, with the exact source response beside each identity. No live requests are made by this page.</p>
<p class="notice"><strong>{badge}</strong><br>Historical observation date: {e(receipt['observation_date_utc'])} UTC. Not a live atlas or a published release.</p>
<nav aria-label="Evidence navigation"><a href="#identities">Explore observed IDs</a><a href="source/panel.json">Raw input panel</a><a href="capsule.json">Capsule receipt</a></nav></header>
<main><section class="stats" aria-label="Coverage summary"><div class="stat"><strong>{receipt['retained_count']} / {receipt['intended_count']}</strong>retained / selected identities</div>
<div class="stat"><strong>{receipt['unavailable_count']}</strong>selected identities unavailable</div><div class="stat"><strong>{e(receipt['observation_date_utc'])}</strong>observation date UTC</div></section>
<section><h2>Scope, dates and coverage</h2><p>First request started: <time>{e(receipt['first_request_started_at_utc'])}</time>. Last request started: <time>{e(receipt['last_request_started_at_utc'])}</time>. Selection date: {e(receipt['selection_date'])}.</p>
<p>Retrieval completion time: unavailable in the retained source receipts. The last request start is not the end of retrieval or a successful publication time.</p>
<table><caption>Retained / selected local page identities. Counts are not pageviews. Editions are not populations.</caption><thead><tr><th scope="col">Subject</th><th scope="col">English</th><th scope="col">Russian</th></tr></thead><tbody>{''.join(cells)}</tbody></table>
<p>Curated selection; not representative. Missing mappings are unavailable, not absence of interest. Titles and QIDs do not establish historical identity continuity.</p></section>
<section id="identities" tabindex="-1"><h2>Observed identities</h2><div class="cards">{''.join(cards)}</div></section>{unavailable}
<section id="limits"><h2>What this evidence does not prove</h2><p>Checksums and the original request URLs establish internal byte agreement, not authenticated network origin. Current metadata does not verify moves, deletion/restoration, resolved QID redirects, historical pageviews, or causation.</p>
<p>Raw responses are retained as decoded JSON entities, not compressed wire bytes. All original collection receipts remain available; failed response bodies are unavailable.</p>
<nav aria-label="Technical evidence"><a href="source/collection-report.json">Collection receipt</a><a href="source/internal-consistency.json">Source consistency</a><a href="source/bundle-manifest.json">Source manifest</a></nav>
<p>{e(RIGHTS)}</p><p>Source revision: <code>{e(receipt['source_revision'])}</code>. Publication status: {e(receipt['status'])}.</p></section></main>
<footer>Dayflare · Evidence you can inspect offline. No scripts, analytics, fonts, images or automatic external requests.</footer></body></html>"""
    return html.encode("utf-8")


def zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, raw)
    return output.getvalue()


def build_capsule(root: Path, *, source_revision: str, source_run_url: str | None = None,
                  evidence_kind: str) -> bytes:
    files = snapshot_directory(root)
    panel, report = validate_source(files)
    receipt = receipt_for(files, panel, report, source_revision=source_revision,
                          source_run_url=source_run_url, evidence_kind=evidence_kind)
    public = dict(files, **{"capsule.json": canonical_bytes(receipt),
                           "index.html": render(panel, report, receipt, files)})
    need(all(len(b) <= member_limit(n) for n, b in public.items()), "generated member byte budget exceeded")
    raw = zip_bytes(public)
    need(len(raw) <= MAX_ARCHIVE, "capsule byte budget exceeded")
    return raw


def verify_capsule(raw: bytes, expected_sha256: str) -> tuple[dict[str, bytes], dict]:
    need(type(expected_sha256) is str and SHA.fullmatch(expected_sha256) is not None,
         "independently recorded SHA-256 pin required")
    need(type(raw) is bytes and 0 < len(raw) <= MAX_ARCHIVE, "empty or oversized capsule")
    need(digest(raw) == expected_sha256, "capsule SHA-256 differs from approval pin")
    files = {}
    total = 0
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            need(1 <= len(infos) <= MAX_MEMBERS, "invalid capsule member count")
            for info in infos:
                name = info.filename
                need(name in SOURCE_NAMES or RAW_NAME.fullmatch(name) or name in {"capsule.json", "index.html"}, "unlisted capsule member")
                need(name not in files and not info.is_dir(), "duplicate member or directory")
                need(stat.S_ISREG(info.external_attr >> 16) and info.compress_type == ZIP_STORED
                     and not info.flag_bits & 1, "linked, compressed, encrypted or nonregular member")
                need(0 < info.file_size <= member_limit(name), "empty or oversized capsule member")
                total += info.file_size
                need(total <= MAX_ARCHIVE, "capsule expansion budget exceeded")
                with archive.open(info) as member:
                    data = member.read(member_limit(name) + 1)
                need(len(data) == info.file_size, "capsule member length mismatch")
                files[name] = data
    except (BadZipFile, RuntimeError, OSError, EOFError, NotImplementedError) as exc:
        raise CapsuleError("unreadable capsule ZIP") from exc
    need({"capsule.json", "index.html"} <= files.keys(), "incomplete capsule")
    need(zip_bytes(files) == raw, "noncanonical ZIP framing or metadata")
    sources = {n: b for n, b in files.items() if n.startswith("source/")}
    panel, report = validate_source(sources)
    receipt = strict_json(files["capsule.json"])
    expected = receipt_for(sources, panel, report,
                           source_revision=receipt.get("source_revision"),
                           source_run_url=receipt.get("source_run_url"),
                           evidence_kind=receipt.get("evidence_kind"))
    need(files["capsule.json"] == canonical_bytes(expected), "capsule receipt differs from source")
    need(files["index.html"] == render(panel, report, expected, sources), "unreviewed evidence page")
    return files, expected


def write_capsule(destination: Path, raw: bytes) -> str:
    """Atomic, no-clobber hard-link promotion; never replaces an existing file."""
    destination = Path(destination).absolute()
    need(not any(p.is_symlink() for p in destination.parents), "linked output parent")
    need(not destination.exists() and not destination.is_symlink(), "output already exists")
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".dayflare-capsule-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.chmod(temporary, 0o644)
        os.link(temporary, destination)  # Atomic EEXIST, including competing writers.
    finally:
        temporary.unlink(missing_ok=True)
    return digest(raw)


def unpack_capsule(raw: bytes, expected_sha256: str, destination: Path) -> dict:
    files, receipt = verify_capsule(raw, expected_sha256)
    destination = Path(destination).absolute()
    need(not any(p.is_symlink() for p in destination.parents), "linked output parent")
    destination.mkdir()  # Exclusive; failures are never allowed to overwrite a prior result.
    (destination / "source" / "raw").mkdir(parents=True)
    # index.html is the last completion marker. A partial I/O failure leaves no
    # usable visitor page; the original ZIP and any previous output stay intact.
    for name in sorted(files, key=lambda n: (n == "index.html", n)):
        with (destination / name).open("xb") as output:
            output.write(files[name])
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    pack = commands.add_parser("pack")
    pack.add_argument("bundle", type=Path)
    pack.add_argument("output", type=Path)
    pack.add_argument("--source-revision", required=True)
    pack.add_argument("--source-run-url")
    pack.add_argument("--evidence-kind", choices=sorted(KINDS), required=True)
    for verb in ("verify", "unpack"):
        command = commands.add_parser(verb)
        command.add_argument("capsule", type=Path)
        command.add_argument("--expected-sha256", required=True)
        if verb == "unpack":
            command.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.operation == "pack":
            raw = build_capsule(args.bundle, source_revision=args.source_revision,
                                source_run_url=args.source_run_url, evidence_kind=args.evidence_kind)
            result = {"sha256": write_capsule(args.output, raw), "bytes": len(raw),
                      "status": "BUILT_NOT_PUBLISHED", "evidence_kind": args.evidence_kind}
        else:
            raw = read_regular(args.capsule, MAX_ARCHIVE)
            if args.operation == "unpack":
                result = unpack_capsule(raw, args.expected_sha256, args.destination)
            else:
                _, result = verify_capsule(raw, args.expected_sha256)
        print(canonical_bytes(result).decode("utf-8"), end="")
    except (CapsuleError, OSError, ValueError, RecursionError) as exc:
        print(f"CAPSULE_INVALID: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
