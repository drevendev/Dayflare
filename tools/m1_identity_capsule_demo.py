"""Fictional transport fixture for offline capsule tests; NEVER real source evidence."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .m1_bundle_verify import make_manifest, verify_bundle
from .m1_identity_panel import canonical_bytes, load_panel
from .m1_source_verify import verify_sources
from .m1_identity_capsule import build_capsule, digest, unpack_capsule, write_capsule

SYNTHETIC_REVISION = "0" * 40
SUBJECTS = ("culture", "books", "games", "science", "sport")


def fixture_bundle(destination: Path, *, day: str = "2026-10-01", count: int = 20,
                   unavailable: bool = True, title_override: str | None = None) -> Path:
    """Create invented HTTP-shaped data, explicitly for controlled local tests.

    reported_retrieval is the input schema being exercised, not evidence of a
    request. Every public capsule built from this fixture MUST use the separate
    synthetic_test_fixture disclosure. No HTTP client is involved.
    """
    destination.mkdir()
    (destination / "raw").mkdir()
    pages, attempts = [], []
    intended, obtained = {}, {}
    total_bytes = retained_bytes = 0
    for i in range(count):
        project = "en.wikipedia" if i % 2 == 0 else "ru.wikipedia"
        subject = SUBJECTS[(i // 2) % len(SUBJECTS)]
        pid = 900000001 + i
        title = (f"Fictional {subject} example {i + 1}" if i % 2 == 0
                 else f"Вымышленный пример {i + 1} ({subject})")
        if i == 0 and title_override is not None:
            title = title_override
        qid = f"Q{900000001 + i}" if i % 3 == 0 else None
        endpoint = (f"https://{project}.org/w/api.php?action=query&format=json&formatversion=2"
                    f"&prop=info%7Cpageprops&ppprop=wikibase_item&pageids={pid}")
        requested = f"{day}T12:00:{i:02d}Z"
        missing = unavailable and i == count - 1
        page = {"pageid": pid, "ns": 0, "title": title, "pageprops": {"wikibase_item": qid} if qid else {}}
        if missing:
            page = {"pageid": pid, "missing": True}
        body = canonical_bytes({"batchcomplete": True, "query": {"pages": [page]}})
        ref = {"project": project, "page_id": pid}
        scope = {"topic_id": f"synthetic-{i + 1}", "subject": subject, "relation": "ambiguous"}
        receipt = {"endpoint": endpoint, "requested_at": requested, "http_status": 200,
                   "response_bytes": len(body), "body_sha256": digest(body)}
        attempt = {"page_ref": ref, **scope, **receipt,
                   "status": "unavailable" if missing else "retained", "wire_bytes": len(body),
                   "wire_sha256": digest(body), "content_encoding": "identity"}
        intended.setdefault(project, Counter())[subject] += 1
        total_bytes += len(body)
        if missing:
            attempt["reason"] = "invalid_or_missing_identity"
        else:
            retained_bytes += len(body)
            obtained.setdefault(project, Counter())[subject] += 1
            (destination / "raw" / f"{project}.{pid}.json").write_bytes(body)
            pages.append({"page_ref": ref, **scope,
                          "titles": [{"date": day, "title": title, "source_url": endpoint}],
                          "events": [], "continuity": "ambiguous", "redirect_to": None,
                          "wikidata": {"state": "observed" if qid else "missing", "observed_qid": qid,
                                       "resolved_qid": None, "evidence_url": endpoint if qid else None},
                          "source": receipt})
        attempts.append(attempt)
    raw_panel = {"schema_version": "dayflare.identity-panel.v1", "panel_id": "synthetic.capsule-evidence",
                 "selection": {"method": "curated", "selected_at": day, "intended_count": count,
                               "evidence_kind": "reported_retrieval"}, "pages": pages}
    (destination / "panel.json").write_bytes(canonical_bytes(raw_panel))
    report = {"schema_version": "dayflare.identity-collection.v2", "panel_id": raw_panel["panel_id"],
              "selected_at": day, "intended_count": count, "retained_count": len(pages),
              "unavailable_count": count - len(pages), "requests_attempted": count,
              "transferred_bytes": total_bytes, "decoded_bytes": total_bytes,
              "body_representation": "decoded-json-entity", "retained_bytes": retained_bytes,
              "intended_by_edition_subject": intended, "obtained_by_edition_subject": obtained,
              "attempts": attempts, "limitations": ["SYNTHETIC TEST FIXTURE: no upstream requests were made."]}
    (destination / "collection-report.json").write_bytes(canonical_bytes(report))
    (destination / "internal-consistency.json").write_bytes(canonical_bytes(verify_sources(destination / "panel.json", destination / "raw")))
    (destination / "bundle-manifest.json").write_bytes(canonical_bytes(make_manifest(destination, load_panel(destination / "panel.json"))))
    verify_bundle(destination)
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new directory, never overwritten")
    args = parser.parse_args(argv)
    args.destination.mkdir()
    bundle = fixture_bundle(args.destination / "synthetic-source")
    raw = build_capsule(bundle, source_revision=SYNTHETIC_REVISION, evidence_kind="synthetic_test_fixture")
    pin = write_capsule(args.destination / "synthetic-capsule.zip", raw)
    unpack_capsule(raw, pin, args.destination / "preview")
    (args.destination / "SHA256SUMS").write_text(pin + "  synthetic-capsule.zip\n", encoding="ascii")
    print("BUILT SYNTHETIC TEST FIXTURE; NO NETWORK; NOT PUBLISHED; sha256=" + pin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
