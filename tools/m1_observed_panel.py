"""Strict offline gate for the dated 20-ID identity-only publication slice.

Checks the internally retained metadata projection. It does not authenticate TLS
origin, historical page continuity, pageviews or cross-edition equivalence.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re

SCHEMA = "dayflare.m1.observed-identity-panel.v1"
DATASET = "m1-20261024-enru-curated-20"
ORIGINAL_ZIP_SHA = "12a5d7fbb78cea7b5931b88de9dadf442729c5e0a680c45665c4940d33b9c6dc"
ORIGINAL_PANEL_SHA = "b10dd769497f9023462a02b4925c1de34dd57f71f9bcf8327050743abfd6bc5d"
EDITIONS = {"en.wikipedia", "ru.wikipedia"}
SUBJECTS = {"culture", "books", "games", "science", "sport"}
ROOT_FIELDS = {"schema_version","dataset_id","observation_date_utc","retrieved_at_utc",
               "status","selection","intended_count","obtained_count","source_run_url",
               "source_bundle_zip_sha256","original_panel_sha256","authenticity","pageviews",
               "cross_edition_mapping","pages"}
ROW_FIELDS = {"project","page_id","subject","title","topic_id","observed_qid",
              "raw_response_sha256","requested_utc"}


class ObservedIdentityError(ValueError):
    """Invalid or unreviewed metadata may not enter a release."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ObservedIdentityError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate JSON field: " + key)
        result[key] = value
    return result


def _bad_constant(value):
    raise ObservedIdentityError("nonfinite JSON constant: " + value)


def validate_bytes(raw: bytes) -> dict:
    require(type(raw) is bytes and 0 < len(raw) <= 65536, "missing or oversized identity panel")
    try:
        panel = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_bad_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ObservedIdentityError("malformed identity JSON") from error
    require(type(panel) is dict and set(panel) == ROOT_FIELDS, "unexpected root schema")
    require(panel["schema_version"] == SCHEMA and panel["dataset_id"] == DATASET, "incompatible dataset version")
    require(panel["observation_date_utc"] == "2026-10-24", "unexpected observation date")
    require(panel["retrieved_at_utc"] == "2026-10-24T20:29:11Z", "unexpected retrieval timestamp")
    require(panel["status"] == "RETAINED_METADATA_ONLY_UNPUBLISHED", "invalid publication state")
    require(panel["selection"] == "editorial_curated_not_representative", "selection bias lost")
    require(type(panel["intended_count"]) is int and panel["intended_count"] == 20 and
            type(panel["obtained_count"]) is int and panel["obtained_count"] == 20,
            "invalid intended/obtained coverage")
    require(panel["source_run_url"] ==
            "https://github.com/drevendev/Dayflare/actions/runs/40129874259", "unreviewed source run")
    require(panel["source_bundle_zip_sha256"] == ORIGINAL_ZIP_SHA and
            panel["original_panel_sha256"] == ORIGINAL_PANEL_SHA, "unreviewed retained source hashes")
    require(panel["authenticity"] == "retained_source_internal_agreement_only", "unsupported origin claim")
    require(panel["pageviews"] == "NOT_COLLECTED_FOR_THIS_PANEL", "unsupported popularity claim")
    require(panel["cross_edition_mapping"] == "AMBIGUOUS_NOT_RESOLVED", "unsupported edition mapping")
    require(type(panel["pages"]) is list and len(panel["pages"]) == 20, "expected 20 selected observations")
    ids, topics, counts = set(), set(), Counter()
    retrieved = datetime.fromisoformat(panel["retrieved_at_utc"].replace("Z","+00:00"))
    for row in panel["pages"]:
        require(type(row) is dict and set(row) == ROW_FIELDS, "unreviewed page fields")
        edition, pid = row["project"], row["page_id"]
        require(type(edition) is str and edition in EDITIONS, "unsupported Wikipedia edition")
        require(type(pid) is int and 0 < pid < 2**53, "invalid numeric page ID")
        require((edition,pid) not in ids, "duplicate local identity")
        ids.add((edition,pid))
        require(type(row["subject"]) is str and row["subject"] in SUBJECTS, "invalid subject")
        counts[(edition,row["subject"])] += 1
        require(type(row["title"]) is str and 0 < len(row["title"]) <= 160, "invalid observed title")
        require(type(row["topic_id"]) is str and
                re.fullmatch(r"[a-z][a-z0-9-]{0,79}",row["topic_id"]) is not None,
                "invalid editorial tag")
        require((edition,row["topic_id"]) not in topics, "duplicate editorial tag in edition")
        topics.add((edition,row["topic_id"]))
        require(type(row["observed_qid"]) is str and
                re.fullmatch(r"Q[1-9][0-9]*", row["observed_qid"]) is not None, "invalid observed QID")
        require(type(row["raw_response_sha256"]) is str and
                re.fullmatch(r"[0-9a-f]{64}", row["raw_response_sha256"]) is not None,
                "invalid retained response hash")
        require(type(row["requested_utc"]) is str and
                re.fullmatch(r"2026-10-24T20:(28|29):[0-5][0-9]Z", row["requested_utc"]) is not None,
                "invalid request timestamp")
        observed = datetime.fromisoformat(row["requested_utc"].replace("Z","+00:00"))
        require(observed <= retrieved, "source timestamp after retrieved time")
    require(all(counts[(e,s)] == 2 for e in EDITIONS for s in SUBJECTS),
            "incomplete edition/subject coverage")
    return panel


def load(path: Path) -> dict:
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "missing or linked identity panel")
    with path.open("rb") as stream:
        raw = stream.read(65537)
    return validate_bytes(raw)
