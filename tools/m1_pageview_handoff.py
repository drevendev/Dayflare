"""Prepare title-scoped pageview seeds from a verified M1 page-identity bundle.

Identity receipts prove only internal consistency of reported source bytes, not
remote origin or historical title continuity. No network or publication occurs.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timezone
import json
from pathlib import Path
import re
import sys
import tempfile

SEED_SCHEMA = "dayflare.rolling-pageview-seeds.v1"
HANDOFF_SCHEMA = "dayflare.identity-pageview-handoff.v1"
EDITIONS = {"en.wikipedia", "ru.wikipedia"}
SUBJECTS = {"culture", "books", "games", "science", "sport", "other"}
SHA = re.compile(r"[a-f0-9]{64}\Z")
METHOD = "v0-empirical-35d"
MAX_PAGES = 30


class HandoffError(ValueError):
    """The reported identity bundle cannot safely seed title-based pageviews."""


def demand(condition: bool, reason: str) -> None:
    if not condition:
        raise HandoffError(reason)


def make_handoff(panel: dict, proof: dict, *, today: date, lag_days: int = 2,
                 max_age_days: int = 1) -> tuple[dict, dict]:
    """Select only recently observed, non-redirected title candidates.

    NOT a stable-page-ID time series: even a verified current (project,page_id)
    cannot establish title continuity over the historical Analytics window.
    """
    demand(type(today) is date, "UTC date required")
    demand(type(lag_days) is int and 1 <= lag_days <= 7, "invalid provider lag")
    demand(type(max_age_days) is int and 0 <= max_age_days <= 2, "invalid title age bound")
    demand(type(panel) is dict and type(proof) is dict, "verified panel/proof required")
    demand(proof.get("result") == "bundle_structurally_and_internally_consistent",
           "not an identity bundle verification result")
    demand(proof.get("panel_id") == panel.get("panel_id"), "wrong identity panel")
    digest = proof.get("manifest_sha256")
    demand(type(digest) is str and SHA.fullmatch(digest) is not None,
           "missing independently recalculated bundle manifest checksum")
    selection = panel.get("selection")
    demand(type(selection) is dict and selection.get("evidence_kind") == "reported_retrieval",
           "synthetic or unverified identity panel cannot seed source collection")
    rows = panel.get("pages")
    demand(type(rows) is list and 1 <= len(rows) <= 100, "invalid identity-panel coverage")
    demand(type(panel.get("panel_id")) is str and bool(panel["panel_id"]), "invalid panel ID")
    # Collision detection precedes any filtering. A title-based endpoint cannot
    # disambiguate two independently claimed identities with the same title.
    seen_refs: set[tuple[str, int]] = set()
    all_titles: dict[tuple[str, str], int] = {}
    for row in rows:
        demand(type(row) is dict and type(row.get("page_ref")) is dict, "invalid page reference")
        ref = row["page_ref"]
        project, pid = ref.get("project"), ref.get("page_id")
        demand(project in EDITIONS and type(pid) is int and 0 < pid < 2**53,
               "invalid stable page reference")
        key = (project, pid)
        demand(key not in seen_refs, "duplicate stable page reference")
        seen_refs.add(key)
        titles = row.get("titles")
        demand(type(titles) is list and titles, "missing title observations")
        title = titles[-1].get("title") if type(titles[-1]) is dict else None
        demand(type(title) is str and 0 < len(title) <= 256 and
               not any(ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in title),
               "invalid observed title")
        tk = (project, title.replace(" ", "_").casefold())
        all_titles[tk] = all_titles.get(tk, 0) + 1
    demand(all(v == 1 for v in all_titles.values()),
           "same edition/title assigned to multiple stable IDs")

    selected: list[dict] = []
    exclusions: list[dict] = []
    uncertain: list[dict] = []
    for row in sorted(rows, key=lambda r: (r["page_ref"]["project"], r["page_ref"]["page_id"])):
        ref = row["page_ref"]
        titles = row["titles"]
        last = titles[-1]
        title = last["title"]
        reason = None
        try:
            observed = date.fromisoformat(last["date"])
            demand(observed.isoformat() == last["date"], "noncanonical title date")
        except (KeyError, TypeError, ValueError) as exc:
            raise HandoffError("invalid last title observation date") from exc
        source = row.get("source")
        demand(type(source) is dict and type(source.get("requested_at")) is str,
               "missing reported source request")
        try:
            request = datetime.fromisoformat(source["requested_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise HandoffError("invalid source request timestamp") from exc
        demand(request.tzinfo is not None and request.utcoffset() is not None and
               request.utcoffset().total_seconds() == 0,
               "source timestamp not UTC")
        demand(observed == request.date(), "title date differs from identity retrieval date")
        if observed > today or (today - observed).days > max_age_days:
            reason = "stale_or_future_title_observation"
        elif row.get("redirect_to") is not None or row.get("events"):
            reason = "redirect_or_identity_event_requires_historical_review"
        elif row.get("subject") not in SUBJECTS:
            reason = "unknown_subject"
        if reason:
            exclusions.append({"page_ref": ref, "reason": reason})
            continue
        selected.append({"project": ref["project"], "page_id": ref["page_id"],
                         "title": title, "subject": row["subject"]})
        if row.get("continuity") != "confirmed":
            uncertain.append(ref)
    demand(1 <= len(selected) <= MAX_PAGES,
           "no eligible pages or pageview request budget exceeded (30)")
    seed = {"schema_version": SEED_SCHEMA, "selected_at": today.isoformat(),
            "method_version": METHOD, "provider_lag_days": lag_days,
            "pages": selected}
    handoff = {"schema_version": HANDOFF_SCHEMA, "panel_id": panel["panel_id"],
               "identity_manifest_sha256": digest, "created_date_utc": today.isoformat(),
               "candidate_count": len(selected), "excluded_count": len(exclusions),
               "exclusions": exclusions, "uncertain_continuity": uncertain,
               "evidence_status": "reported_transport_not_independently_authenticated",
               "metric_scope": "title_scoped_views_not_stable_page_id_history",
               "publication_status": "LOCAL_SEEDS_ONLY_NOT_PUBLISHED",
               "limits": ["No verified historical title/redirect continuity.",
                          "Reported source body hashes do not authenticate Wikimedia origin.",
                          "New pageview requests and independent evidence/rights review required."]}
    return seed, handoff


def from_bundle(bundle: Path, *, today: date | None = None, lag_days: int = 2) -> tuple[dict, dict]:
    """Reverify raw identity evidence before trusting the panel for a seed handoff."""
    from .m1_bundle_verify import verify_bundle
    from .m1_identity_panel import load_panel
    from .rolling_pageview_source import check_seed
    bundle = Path(bundle)
    proof = verify_bundle(bundle)
    panel = load_panel(bundle / "panel.json")
    today = today or datetime.now(timezone.utc).date()
    seed, receipt = make_handoff(panel, proof, today=today, lag_days=lag_days)
    check_seed(seed, now=datetime.combine(today, time(12), timezone.utc))
    return seed, receipt


def canonical(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def export(bundle: Path, out: Path, *, today: date | None = None, lag_days: int = 2) -> dict:
    """Save the two-file handoff to a new directory; never overwrite existing work."""
    from .rolling_pageview_source import _atomic_new_dir
    seed, receipt = from_bundle(bundle, today=today, lag_days=lag_days)
    out = Path(out)
    demand(out.parent.is_dir() and not out.parent.is_symlink(), "output parent must exist")
    demand(not out.exists() and not out.is_symlink(), "handoff directory already exists")
    with tempfile.TemporaryDirectory(prefix=".dayflare-handoff-", dir=out.parent) as place:
        temp = Path(place)
        (temp / "seeds.json").write_bytes(canonical(seed))
        (temp / "handoff.json").write_bytes(canonical(receipt))
        _atomic_new_dir(temp, out)
    return receipt


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("identity_bundle", type=Path)
    p.add_argument("new_directory", type=Path)
    p.add_argument("--provider-lag-days", type=int, default=2)
    args = p.parse_args(argv)
    try:
        report = export(args.identity_bundle, args.new_directory,
                        lag_days=args.provider_lag_days)
    except (HandoffError, OSError, ValueError) as exc:
        p.exit(2, f"INVALID HANDOFF: {exc}\n")
    print(canonical(report).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
