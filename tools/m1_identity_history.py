"""Compare two dated D03 identity panels without stitching title/pageview histories.

Offline only: input hashes establish byte identity, not Wikimedia authenticity.
The HTML/JSON bundle is immutable and never replaces an existing publication.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sys

from tools.m1_identity_panel import MAX_BYTES, PanelError, canonical_bytes, validate_panel

SCHEMA = "dayflare.identity-history.v1"
METHOD = "d03-observation-diff.v1"
LIMITATION = (
    "Two observations do not establish uninterrupted page identity or an exhaustive event log. "
    "An absent observation is not a deletion, a new observation is not a creation, and "
    "matching titles or Wikidata IDs do not join pages. No pageviews are combined."
)
CONTINUITY_LABELS = {
    "unverified_between_observations": "Unverified between observations",
    "not_comparable": "Not comparable",
    "boundary_present": "Deletion/restoration boundary present",
    "conflicting_evidence": "Conflicting retained evidence",
}
LABELS = {
    "not_observed_before": "Only in later snapshot — creation unknown",
    "not_observed_after": "Not in later snapshot — deletion unknown",
    "title_changed": "Observed title changed",
    "move_reported": "Matching move event reported, not independently verified",
    "mapping_changed": "Wikidata mapping changed",
    "redirect_changed": "Redirect target changed",
    "topic_assignment_changed": "Editorial topic or scope changed",
    "delete_restore_boundary": "Deletion/restoration boundary — do not stitch",
    "conflicting_title_history": "Conflicting retained title observations",
    "mapping_collision": "Non-one-to-one mapping — unresolved",
    "unchanged_observation": "Same local ID and compared fields; continuity unknown",
}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PanelError("duplicate JSON field: " + key)
        result[key] = value
    return result


def _nonfinite(value):
    raise PanelError("non-finite JSON constant: " + value)


def _decode(raw: bytes) -> tuple[dict, str]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise PanelError("history input must be 1..256 KiB of UTF-8 JSON")
    try:
        panel = validate_panel(json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                                          parse_constant=_nonfinite))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise PanelError("malformed or excessively nested history input") from error
    days = {page["titles"][-1]["date"] for page in panel["pages"]}
    if len(days) != 1:
        raise PanelError("each snapshot needs a nonempty panel with one observation day")
    observed = days.pop()
    if observed > date.today().isoformat() or panel["selection"]["selected_at"] > observed:
        raise PanelError("invalid selection/observation chronology")
    for page in panel["pages"]:
        if any(event["date"] > observed for event in page["events"]):
            raise PanelError("event postdates snapshot observation day")
        if page["redirect_to"] and page["redirect_to"]["observed_at"] > observed:
            raise PanelError("redirect postdates snapshot observation day")
    return panel, observed


def _key(page: dict) -> tuple[str, int]:
    return page["page_ref"]["project"], page["page_ref"]["page_id"]


def _mapping(page: dict) -> tuple:
    value = page["wikidata"]
    return value["state"], value["observed_qid"], value["resolved_qid"]


def _target(page: dict):
    edge = page["redirect_to"]
    return edge["target_ref"] if edge else None


def _collisions(panel: dict) -> set[tuple[str, int]]:
    coverage = panel["coverage"]
    return {(item["project"], pid)
            for name in ("non_1_to_1_local_qid_collisions", "non_1_to_1_observed_qid_collisions")
            for item in coverage[name] for pid in item["local_page_ids"]}


def compare_bytes(before_raw: bytes, after_raw: bytes) -> dict:
    """Return deterministic observations, never an authorization to join histories."""
    before, left_day = _decode(before_raw)
    after, right_day = _decode(after_raw)
    if left_day >= right_day:
        raise PanelError("after observation day must be strictly later than before")
    evidence = before["selection"]["evidence_kind"]
    if evidence != after["selection"]["evidence_kind"]:
        raise PanelError("synthetic and reported-retrieval panels cannot be mixed")
    left = {_key(page): page for page in before["pages"]}
    right = {_key(page): page for page in after["pages"]}
    collisions = _collisions(before) | _collisions(after)
    rows = []
    for key in sorted(left.keys() | right.keys()):
        old, new = left.get(key), right.get(key)
        changes = []
        continuity = "unverified_between_observations"
        events = []
        if old is None or new is None:
            changes.append("not_observed_before" if old is None else "not_observed_after")
            continuity = "not_comparable"
        else:
            old_title, new_title = old["titles"][-1]["title"], new["titles"][-1]["title"]
            events = [deepcopy(event) for event in new["events"]
                      if left_day < event["date"] <= right_day]
            if old_title != new_title:
                changes.append("title_changed")
                if any(event["kind"] == "move" and event["old_title"] == old_title
                       and event["new_title"] == new_title for event in events):
                    changes.append("move_reported")
            if _mapping(old) != _mapping(new):
                changes.append("mapping_changed")
            if _target(old) != _target(new):
                changes.append("redirect_changed")
            if any(old[field] != new[field] for field in ("topic_id", "subject", "relation")):
                changes.append("topic_assignment_changed")
            # A boundary anywhere in the retained evidence stays visible; a later
            # panel omitting the old event cannot silently erase that uncertainty.
            if any(event["kind"] in {"delete", "restore"}
                   for page in (old, new) for event in page["events"]):
                changes.append("delete_restore_boundary")
                continuity = "boundary_present"
            history = {item["date"]: item["title"] for item in old["titles"]}
            if any(item["date"] in history and history[item["date"]] != item["title"]
                   for item in new["titles"]):
                changes.append("conflicting_title_history")
                continuity = "conflicting_evidence"
        if key in collisions:
            changes.append("mapping_collision")
        rows.append({"page_ref": {"project": key[0], "page_id": key[1]},
                     "before": deepcopy(old), "after": deepcopy(new),
                     "changes": sorted(changes or ["unchanged_observation"]),
                     "events_between_observations": events, "continuity": continuity,
                     "pageview_join_allowed": False})
    hashes = [sha256(raw).hexdigest() for raw in (before_raw, after_raw)]
    report_id = "identity-history-" + sha256((METHOD + ":" + ":".join(hashes)).encode()).hexdigest()[:24]
    inputs = []
    for panel, day, digest in zip((before, after), (left_day, right_day), hashes):
        inputs.append({"panel_id": panel["panel_id"], "observation_date_utc": day,
                       "input_sha256": digest, "selection": deepcopy(panel["selection"]),
                       "coverage": deepcopy(panel["coverage"])})
    return {"schema_version": SCHEMA, "method_version": METHOD, "report_id": report_id,
            "evidence_kind": evidence, "inputs": inputs, "limitations": LIMITATION,
            "summary": {"identities_in_union": len(rows), "observed_in_both": len(left.keys() & right.keys()),
                        "only_before": len(left.keys() - right.keys()), "only_after": len(right.keys() - left.keys()),
                        "change_counts": dict(sorted(Counter(change for row in rows for change in row["changes"]).items()))},
            "pages": rows}


def _anchor(report: dict, page: dict) -> str:
    ref = page["page_ref"]
    return f'{report["report_id"]}-{ref["project"].split(".")[0]}-{ref["page_id"]}'


def _observation(page: dict | None) -> str:
    if page is None:
        return '<p class="unknown">Not observed in this snapshot. Lifecycle state unknown.</p>'
    title = page["titles"][-1]
    mapping = page["wikidata"]
    target = _target(page)
    redirect = f'{target["project"]}:{target["page_id"]}' if target else "No redirect edge supplied"
    source = page["source"]
    retrieved = source["requested_at"] if source else "Not retrieved — synthetic fixture"
    digest = source["body_sha256"] if source else "Not applicable"
    return (f'<h4>{escape(title["title"])}</h4><dl>'
            f'<dt>Observed on (UTC)</dt><dd>{escape(title["date"])}</dd>'
            f'<dt>Subject / topic</dt><dd>{escape(page["subject"])} / {escape(page["topic_id"])}</dd>'
            f'<dt>Topic relation</dt><dd>{escape(page["relation"])}</dd>'
            f'<dt>Observed QID</dt><dd>{escape(mapping["observed_qid"] or "Unavailable")}</dd>'
            f'<dt>Resolved QID</dt><dd>{escape(mapping["resolved_qid"] or "Unavailable")}</dd>'
            f'<dt>Mapping state</dt><dd>{escape(mapping["state"])}</dd>'
            f'<dt>Redirect target</dt><dd>{escape(redirect)}</dd>'
            f'<dt>Reported continuity</dt><dd>{escape(page["continuity"])}</dd>'
            f'<dt>Retrieval timestamp</dt><dd>{escape(retrieved)}</dd>'
            f'<dt>Reported response SHA-256</dt><dd><code>{escape(digest)}</code></dd></dl>'
            f'<a href="{escape(title["source_url"], quote=True)}">Title observation source</a>')


def render_html(report: dict) -> bytes:
    """Render a compare_bytes result as a self-contained, no-JavaScript report."""
    synthetic = report["evidence_kind"] == "synthetic"
    banner = "SYNTHETIC DEMONSTRATION — not real Wikipedia changes" if synthetic else "REPORTED METADATA — upstream authenticity not verified"
    left, right = report["inputs"]
    summary = report["summary"]
    index, cards = [], []
    for row in report["pages"]:
        ref = row["page_ref"]
        anchor = _anchor(report, row)
        display = f'{ref["project"]}:{ref["page_id"]}'
        labels = "; ".join(LABELS[value] for value in row["changes"])
        index.append(f'<li><a href="#{anchor}">{escape(display)}</a> — {escape(labels)}</li>')
        events = "".join(f'<li>{escape(event["date"])}: {escape(event["kind"])} '
                         f'<a href="{escape(event["source_url"], quote=True)}">Reported event source</a></li>'
                         for event in row["events_between_observations"])
        cards.append(f'<article id="{anchor}" class="card" tabindex="-1">'
                     f'<h2>{escape(display)}</h2><p class="changes">{escape(labels)}</p>'
                     f'<p>Continuity assessment: <strong>{escape(CONTINUITY_LABELS[row["continuity"]])}</strong>. '
                     'Pageview joining: <strong>not allowed</strong>.</p>'
                     f'<div class="pair"><section><h3>Before · {left["observation_date_utc"]}</h3>{_observation(row["before"])}</section>'
                     f'<section><h3>After · {right["observation_date_utc"]}</h3>{_observation(row["after"])}</section></div>'
                     '<details><summary>Exact observations and retained evidence</summary>'
                     f'<p>Events between the two observations:</p><ul>{events or "<li>No event supplied; this is not proof of no event.</li>"}</ul>'
                     f'<pre>{escape(json.dumps(row, ensure_ascii=False, sort_keys=True, indent=2))}</pre></details>'
                     f'<p><a href="#{anchor}">Link to this identity in this exact report</a> · <a href="#index">Back to index</a></p></article>')
    sources = "".join(f'<section><h3>{name} input</h3><p>{escape(item["panel_id"])}</p>'
                      f'<p>Observed: {item["observation_date_utc"]} UTC. '
                      f'Obtained: {item["coverage"]["obtained_count"]} / intended {item["coverage"]["intended_count"]}.</p>'
                      f'<code>{item["input_sha256"]}</code>'
                      f'<details><summary>Selection and coverage diagnostics</summary><pre>{escape(json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True))}</pre></details></section>'
                      for name, item in zip(("Before", "After"), report["inputs"]))
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>Dayflare · Identity history</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f1e9;color:#172e37;font:17px/1.65 system-ui,sans-serif;overflow-wrap:anywhere}}main,header,footer{{max-width:1120px;margin:auto;padding:1.4rem}}a{{color:#005b70;text-underline-offset:.2em}}a:focus-visible,summary:focus-visible,article:focus{{outline:3px solid #b34716;outline-offset:4px}}h1{{font:700 clamp(2rem,6vw,3.8rem)/1.1 Georgia,serif;max-width:20ch}}h2,h3,h4{{line-height:1.3;overflow-wrap:anywhere}}h2{{font-size:1.35rem}}h4{{font-size:1.2rem;margin:.8rem 0}}.banner{{border-left:5px solid #b34716;background:#fff2dd;padding:1rem;font-weight:700}}.pair,.stats{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1.2rem}}.stats{{grid-template-columns:repeat(4,minmax(0,1fr));margin:2rem 0}}.stats p{{min-width:0;margin:0;padding:1rem;background:#fff}}.stats strong{{display:block;font-size:2rem}}.card{{background:#fff;border:1px solid #ccc8be;border-radius:12px;padding:1.4rem;margin:1.2rem 0;scroll-margin-top:1rem}}.pair section{{min-width:0;padding:1rem;background:#f4f6f5}}.changes{{font-weight:650;border-left:4px solid #005b70;padding-left:1rem}}.unknown{{font-style:italic}}dt{{font-size:.85rem;font-weight:700;margin-top:.8rem}}dd{{margin:0;overflow-wrap:anywhere}}code{{overflow-wrap:anywhere;font-size:.85rem}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.8rem;line-height:1.6}}summary{{cursor:pointer;min-height:44px;padding:.7rem 0;font-weight:650}}nav a,.card>p a{{max-width:100%;display:inline-block;min-height:44px;padding:.45rem 0}}.skip{{display:block;padding:.7rem 1.4rem;background:#fff}}.lead{{max-width:70ch}}@media(max-width:650px){{.pair{{grid-template-columns:1fr}}.stats{{grid-template-columns:repeat(2,minmax(0,1fr))}}main,header,footer{{padding:1rem}}.card{{padding:1rem}}}}@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto}}}}
</style></head><body><a class="skip" href="#index">Skip to identity index</a>
<header><p>DAYFLARE / EVIDENCE EXPLORER</p><p class="banner">{banner}</p>
<h1>What changed between observations?</h1><p class="lead">Compare local Wikipedia page identities, not names. Read the before-and-after evidence without silently joining histories.</p>
<p><strong>Observation dates: {left["observation_date_utc"]} → {right["observation_date_utc"]} UTC.</strong> Historical snapshots, not a live feed.</p>
<div class="stats"><p><strong>{summary["identities_in_union"]}</strong>Distinct local IDs</p><p><strong>{summary["observed_in_both"]}</strong>Observed in both</p><p><strong>{summary["only_before"]}</strong>Only before</p><p><strong>{summary["only_after"]}</strong>Only after</p></div>
<p class="lead">{escape(LIMITATION)}</p><nav aria-label="Report data"><a href="history.json">Exact machine-readable report</a> · <a href="manifest.json">Checksums and versions</a></nav></header>
<main><nav id="index" tabindex="-1" aria-label="Identity index"><h2>Find an identity</h2><ul>{"".join(index)}</ul></nav>{"".join(cards)}
<section aria-label="Input provenance"><h2>Where these observations came from</h2><p>Curated panels are not representative coverage. Hashes identify local bytes; they are not signatures of Wikimedia responses.</p><div class="pair">{sources}</div></section></main>
<footer><p>Schema: {SCHEMA} · Method: {METHOD}</p><code>{report["report_id"]}</code><p>No JavaScript, analytics, remote fonts or automatic network requests.</p></footer></body></html>'''
    return html.encode("utf-8")


def write_bundle(before: Path, after: Path, output: Path) -> dict:
    payloads = []
    for path in (before, after):
        if path.is_symlink() or not path.is_file():
            raise PanelError("history input must be a regular, non-symlink file")
        with path.open("rb") as stream:
            payloads.append(stream.read(MAX_BYTES + 1))
    report = compare_bytes(*payloads)
    files = {"history.json": canonical_bytes(report), "index.html": render_html(report)}
    manifest = {"schema_version": SCHEMA, "method_version": METHOD, "report_id": report["report_id"],
                "files": {name: sha256(data).hexdigest() for name, data in sorted(files.items())}}
    # mkdir is the atomic no-overwrite reservation. All validation/rendering is
    # complete first; a concurrent existing candidate is never replaced.
    output.mkdir(parents=False, exist_ok=False)
    for name, data in files.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    # Commit marker is last: a failed partial write is not a complete bundle.
    with (output / "manifest.json").open("xb") as stream:
        stream.write(canonical_bytes(manifest))
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="earlier raw dayflare.identity-panel.v1 JSON")
    parser.add_argument("after", type=Path, help="later raw dayflare.identity-panel.v1 JSON")
    parser.add_argument("output", type=Path, help="new immutable output directory (must not exist)")
    args = parser.parse_args(argv)
    try:
        manifest = write_bundle(args.before, args.after, args.output)
    except (OSError, PanelError, ValueError) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    print(f'BUILT {manifest["report_id"]}; not deployed or live verified')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
