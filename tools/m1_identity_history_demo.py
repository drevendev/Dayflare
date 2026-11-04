"""Build a prominently synthetic, offline identity-history example; never fetch data."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import argparse
import tempfile

from tools.m1_identity_panel import SCHEMA, canonical_bytes
from tools.m1_identity_history import write_bundle

SOURCE = "https://www.mediawiki.org/wiki/Help:Page_ID"


def example_panels() -> tuple[dict, dict]:
    def page(project, pid, title, subject):
        return {"page_ref": {"project": project, "page_id": pid},
                "topic_id": f"synthetic-{project[:2]}-{pid}", "subject": subject,
                "relation": "ambiguous", "titles": [{"date": "2026-10-01", "title": title,
                                                        "source_url": SOURCE}],
                "events": [], "continuity": "ambiguous", "redirect_to": None,
                "wikidata": {"state": "observed", "observed_qid": f"Q{pid + 100}",
                             "resolved_qid": None, "evidence_url": SOURCE}, "source": None}
    before = {"schema_version": SCHEMA, "panel_id": "synthetic-history-before",
              "selection": {"method": "curated", "selected_at": "2026-10-01",
                            "intended_count": 6, "evidence_kind": "synthetic"},
              "pages": [page("en.wikipedia", 1, "Example Theatre", "culture"),
                        page("en.wikipedia", 2, "Example Novel", "books"),
                        page("en.wikipedia", 3, "Example Game", "games"),
                        page("en.wikipedia", 4, "Reused Example Title", "other"),
                        page("ru.wikipedia", 1, "Пример лаборатории", "science"),
                        page("ru.wikipedia", 2, "Пример команды", "sport")]}
    after = deepcopy(before)
    after["panel_id"] = "synthetic-history-after"
    for row in after["pages"]:
        row["titles"].append(dict(row["titles"][-1], date="2026-10-08"))
    changed = after["pages"]
    changed[0]["titles"][-1]["title"] = "Example Stage"
    changed[0]["events"] = [{"date": "2026-10-05", "kind": "move", "source_url": SOURCE,
                             "old_title": "Example Theatre", "new_title": "Example Stage"}]
    changed[1]["wikidata"]["observed_qid"] = "Q103"  # collision is intentional, not resolved
    changed[2]["redirect_to"] = {"target_ref": {"project": "en.wikipedia", "page_id": 1},
                                  "observed_at": "2026-10-08", "source_url": SOURCE}
    changed[3]["page_ref"]["page_id"] = 5  # same title does not stitch different IDs
    changed[3]["topic_id"] = "synthetic-en-5"
    changed[3]["titles"] = [changed[3]["titles"][-1]]
    changed[5]["events"] = [{"date": "2026-10-04", "kind": "delete", "source_url": SOURCE},
                             {"date": "2026-10-06", "kind": "restore", "source_url": SOURCE}]
    changed[5]["continuity"] = "discontinuous"
    return before, after


def build_demo(output: Path) -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        before, after = example_panels()
        (root / "before.json").write_bytes(canonical_bytes(before))
        (root / "after.json").write_bytes(canonical_bytes(after))
        return write_bundle(root / "before.json", root / "after.json", output)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new directory, must not already exist")
    args = parser.parse_args(argv)
    build_demo(args.output)
    print("BUILT SYNTHETIC DEMONSTRATION; not real observations, not a public deployment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
