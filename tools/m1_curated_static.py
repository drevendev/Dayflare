"""Fail-closed gate for the 20 archived, title-scoped Wikimedia histories.

Observed numeric page IDs describe a different date; they never establish
historical ID continuity or cross-language subject equivalence.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from hashlib import sha256
from html import escape
import json
import math
import re
from urllib.parse import quote

from tools.m1_observed_panel import validate_bytes as validate_observed

SCHEMA = "dayflare.m1-curated-title-views.v1"
DATASET = "m1-curated-20261023-d96477427ece"
CANDIDATE_SHA = "d96477427ece441302b11485f56a79703f77615b4a2b8cc98b4afaec078fc091"
RECEIPT_SHA = "8363c92d23d496d8552f86025d2fec5a6e091c7a2269344cd22ef40f77168ee3"
DAILY_SHA = "0016e1a453010399747567050e4edbfa52e3a0cbb6bac60102ae15d479e4eb53"
RAW_SHA_LIST_SHA = "dd75931d8ff6a76c3d3100e44cafe9190efde0cf2e9dda8e436f5a6e3bed5827"
TIMESTAMP_LIST_SHA = "27ad88f0434a6a9d3b516bb487c53a372b0113a4ea24bc30e94e20ed312ac2d3"
START, END = date(2026, 9, 19), date(2026, 10, 23)
PROJECTS = ("en.wikipedia", "ru.wikipedia")
SUBJECTS = ("culture", "books", "games", "science", "sport")


def _encoded(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate source field: " + key)
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("Nonfinite JSON constant: " + value)


def _display(v: int | float) -> str:
    return f"{v:,.1f}".removesuffix(".0")


def validate_assets(data_bytes: bytes, html_bytes: bytes, observed_bytes: bytes) -> dict:
    """Reconstruct exact values from pinned source data; check visitor-visible HTML."""
    if not (type(data_bytes) is bytes and 0 < len(data_bytes) <= 120_000
            and type(html_bytes) is bytes and 0 < len(html_bytes) <= 400_000):
        raise ValueError("Missing or oversized curated evidence")
    data = json.loads(data_bytes.decode("utf-8"),
                      object_pairs_hook=_unique_pairs, parse_constant=_nonfinite)
    html = html_bytes.decode("utf-8")
    expected_window = {"start": str(START), "end": str(END), "days": 35}
    expected_coverage = {
        "selected": 20, "measured": 20, "daily_observations": 700,
        "subjects": list(SUBJECTS), "editions": list(PROJECTS),
    }
    if not isinstance(data, dict) or any((
        data.get("schema") != SCHEMA,
        data.get("dataset_id") != DATASET,
        data.get("source_candidate_sha256") != CANDIDATE_SHA,
        data.get("source_receipt_sha256") != RECEIPT_SHA,
        data.get("method_version") != "v0-empirical-35d",
        data.get("observed_identity_dataset") != "m1-20261024-enru-curated-20",
        data.get("observation_window_utc") != expected_window,
        data.get("retrieved_at_utc") != "2026-10-26T01:36:18Z",
        data.get("publication_status") != "UNPUBLISHED_SOURCE_BOUND_SNAPSHOT",
        data.get("historical_identity_continuity") != "UNVERIFIED_TITLE_SCOPED",
        data.get("cross_edition_equivalence") != "NOT_ASSUMED",
        data.get("filters") != {"access": "all-access", "agent": "user",
                               "granularity": "daily"},
        data.get("coverage") != expected_coverage,
    )):
        raise ValueError("Changed source, scope, method or provenance")
    series = data.get("series")
    if not isinstance(series, list) or len(series) != 20:
        raise ValueError("Incomplete source selection")
    observed = validate_observed(observed_bytes)
    identities = {(p["project"], p["page_id"]): p for p in observed["pages"]}
    seen, daily, raw_hashes, request_times = set(), [], [], []
    for entry in series:
        if not isinstance(entry, dict):
            raise ValueError("Invalid series")
        project, page_id = entry.get("project"), entry.get("observed_page_id")
        key = (project, page_id)
        if key in seen or key not in identities:
            raise ValueError("Duplicate, missing or unsupported local identity")
        seen.add(key)
        origin = identities[key]
        if (entry.get("title") != origin["title"] or
                entry.get("subject") != origin["subject"]):
            raise ValueError("Changed observed identity context")
        title = entry["title"]
        endpoint = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
                    + project + "/all-access/user/" + quote(title.replace(" ", "_"), safe="")
                    + "/daily/20260919/20261023")
        if entry.get("source_url") != endpoint or type(entry.get("source_status")) is not int or entry["source_status"] != 200:
            raise ValueError("Invalid Wikimedia source endpoint or HTTP status")
        raw_sha, requested = entry.get("raw_response_sha256"), entry.get("requested_at_utc")
        if type(raw_sha) is not str or re.fullmatch(r"[0-9a-f]{64}", raw_sha) is None:
            raise ValueError("Missing source response digest")
        if type(requested) is not str or re.fullmatch(r"2026-10-26T01:3[56]:[0-5][0-9]Z", requested) is None:
            raise ValueError("Invalid source request timestamp")
        raw_hashes.append(raw_sha)
        request_times.append(requested)
        values = entry.get("daily_views")
        if (not isinstance(values, list) or len(values) != 35 or
                any(type(v) is not int or v < 0 or v > 2**31 for v in values)):
            raise ValueError("Missing, invalid or nonfinite daily values")
        daily.append(values)
        weeks = [sum(values[i:i + 7]) for i in range(0, 35, 7)]
        four = sorted(weeks[:4])
        baseline = (four[1] + four[2]) / 2
        latest = weeks[-1]
        delta = latest - baseline
        lift = delta / baseline if baseline else None
        computed = entry.get("computed")
        if (not isinstance(computed, dict) or
                computed.get("weekly_totals") != weeks or
                type(computed.get("latest")) is not int or computed["latest"] != latest or
                type(computed.get("baseline")) not in (int, float) or
                computed["baseline"] != baseline or
                type(computed.get("delta")) not in (int, float) or
                computed["delta"] != delta):
            raise ValueError("Source-derived weekly metrics disagree")
        v = computed.get("relative_lift")
        if (lift is None and v is not None) or (lift is not None and
                (type(v) not in (int, float) or not math.isfinite(v) or abs(v - lift) > 1e-12)):
            raise ValueError("Missing or incorrect relative change")
        key_id = "topic-" + ("en" if project == PROJECTS[0] else "ru") + "-" + str(page_id)
        escaped_id = re.escape(key_id)
        articles = re.findall(r'<article class="topic" id="' + escaped_id + r'"[^>]*>.*?</article>',
                              html, re.DOTALL)
        if len(articles) != 1:
            raise ValueError("Visitor topic missing or duplicated")
        article = articles[0]
        expected_heading = '<h3' + (' lang="ru"' if project == PROJECTS[1] else '') + '>' + escape(title) + '</h3>'
        if (article.count(expected_heading) != 1 or
                article.count('data-project="' + project + '"') != 1 or
                article.count('data-observed-page-id="' + str(page_id) + '"') != 1 or
                article.count('data-latest="' + str(latest) + '"') != 1 or
                article.count('data-baseline="' + format(baseline, "g") + '"') != 1 or
                article.count('data-delta="' + format(delta, "g") + '"') != 1 or
                article.count(raw_sha) != 1 or
                article.count('href="' + endpoint + '"') != 1):
            raise ValueError("Visitor-visible identity, metrics or evidence disagree")
        if article.count('<strong>' + _display(latest) + '</strong>') != 1:
            raise ValueError("Displayed current volume differs from source")
        if article.count('<strong>' + _display(baseline) + '</strong>') != 1:
            raise ValueError("Displayed baseline differs from source")
        actual_change = (("+" if delta >= 0 else "−") + f"{abs(lift) * 100:.1f}%" 
                         if lift is not None else "not computed")
        if article.count(">" + actual_change + "</span>") != 1:
            raise ValueError("Displayed relative change differs from source")
        rendered_weeks = re.findall(r'<span class="weekvalue">([^<]+)</span>', article)
        if rendered_weeks != [_display(v) for v in weeks]:
            raise ValueError("Displayed weekly totals disagree")
        rows = re.findall(r'<tr><th scope="row">(\d{4}-\d{2}-\d{2})</th><td>([\d,]+)</td></tr>', article)
        if rows != [(str(START + timedelta(days=i)), _display(v)) for i, v in enumerate(values)]:
            raise ValueError("Displayed exact daily rows disagree")
    if (len(seen) != 20 or series != sorted(series, key=lambda x: (x["project"], x["observed_page_id"]))):
        raise ValueError("Unexpected source selection or ordering")
    if sha256(_encoded(daily)).hexdigest() != DAILY_SHA:
        raise ValueError("Data differs from independently replayed source artifact")
    if sha256("".join(raw_hashes).encode()).hexdigest() != RAW_SHA_LIST_SHA:
        raise ValueError("Original response hashes changed")
    if sha256("".join(request_times).encode()).hexdigest() != TIMESTAMP_LIST_SHA:
        raise ValueError("Source acquisition times changed")
    counts = Counter((x["project"], x["subject"]) for x in series)
    if counts != Counter({(p, s): 2 for p in PROJECTS for s in SUBJECTS}):
        raise ValueError("Unsupported edition and subject coverage")
    if (html.count('class="topic"') != 20 or html.count('<details') != 20 or
            f'content="{DATASET}"' not in html or
            "not historical page-id continuity" not in html.lower() or
            "not representative" not in html.lower() or
            "26 October 2026" not in html or "2026-10-23" not in html or
            "not yet verified" not in html):
        raise ValueError("Missing complete, dated or honest visitor disclosure")
    return {
        "dataset_id": DATASET, "observation_end_utc": str(END),
        "retrieved_at_utc": data["retrieved_at_utc"],
        "measured_series": 20, "daily_observations": 700,
        "source_candidate_sha256": CANDIDATE_SHA,
        "title_scoped": True, "historical_page_id_continuity": False,
    }
