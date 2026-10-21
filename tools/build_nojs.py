"""Deterministic, read-only-source, accessible no-JavaScript evidence tables.

Run `python -m tools.build_nojs --check` before publishing. The generated HTML is
only a projection of the retained D02 evidence ZIP, never a second data authority.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "evidence/d02-20261018/source.zip"
PAGE = ROOT / "site/index.html"
ARCHIVE_SHA = "3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631"
MEMBER_SHAS = {
    "sample.json": "98880f706c0d8b5433f0fbb46bcad0cb9a2d515ea894752dcd971326e5805a8e",
    "receipt.json": "298c6ade24ec911502f4e2bee23e4c3ac012eecc8192b56071210d3cf94adb21",
}
START_MARKER = "<!-- DAYFLARE_NOJS_START -->"
END_MARKER = "<!-- DAYFLARE_NOJS_END -->"
WINDOW_START = date(2026, 8, 11)


def verified_series(archive: Path = ARCHIVE) -> list[dict]:
    raw = archive.read_bytes()
    if sha256(raw).hexdigest() != ARCHIVE_SHA:
        raise ValueError("retained source archive checksum mismatch")
    with ZipFile(archive) as zip_file:
        if set(zip_file.namelist()) != set(MEMBER_SHAS):
            raise ValueError("unexpected source archive members")
        files = {}
        for name, digest in MEMBER_SHAS.items():
            info = zip_file.getinfo(name)
            if info.file_size > 128 * 1024:
                raise ValueError("oversized evidence member")
            member = zip_file.read(name)
            if sha256(member).hexdigest() != digest:
                raise ValueError(f"evidence member hash mismatch: {name}")
            files[name] = json.loads(member)
    sample, receipt = files["sample.json"], files["receipt.json"]
    if not (isinstance(sample, list) and len(sample) == 6 and receipt.get("success") is True
            and receipt.get("method_version") == "v0-empirical-35d"
            and receipt.get("observation_window") == {"start": "20260811", "end": "20260914", "expected_days": 35}
            and len(receipt.get("series_metrics", [])) == 6):
        raise ValueError("incompatible historical evidence schema/window")
    output = []
    for sample_row, metric_row in zip(sample, receipt["series_metrics"]):
        spec, metrics = metric_row["request"], metric_row["metrics"]
        rows = sample_row.get("items", [])
        edition, title = spec["project"], spec["article"]
        if (edition not in {"en.wikipedia.org", "ru.wikipedia.org"}
                or not isinstance(title, str) or not title or len(rows) != 35):
            raise ValueError("incompatible historical series")
        for index, row in enumerate(rows):
            if (row.get("date") != (WINDOW_START + timedelta(days=index)).isoformat()
                    or not isinstance(row.get("views"), int) or isinstance(row["views"], bool)
                    or not 0 <= row["views"] <= (1 << 53) - 1
                    or row.get("project") != edition.removesuffix(".org")
                    or row.get("article") != title or row.get("value_state") != "observed"
                    or row.get("agent") != "user" or row.get("access") != "all-access"
                    or row.get("granularity") != "daily"):
                raise ValueError(f"incomplete or incompatible daily value: {edition} {title} {index}")
        totals = [sum(r["views"] for r in rows[i:i+7]) for i in (0, 7, 14, 21, 28)]
        middle = sorted(totals[:4])[1:3]
        baseline = sum(middle) / 2
        delta = totals[-1] - baseline
        relative = None if baseline == 0 else delta / baseline
        if (totals != metrics["weekly_totals_oldest_to_current"] or totals[-1] != metrics["V"]
                or baseline != metrics["B"] or delta != metrics["delta"]
                or (relative is None) != (metrics["relative_lift"] is None)
                or relative is not None and abs(relative - metrics["relative_lift"]) > 1e-12):
            raise ValueError("reported metrics do not match retained observations")
        output.append({"title": title, "edition": edition, "rows": rows,
                       "latest": totals[-1], "baseline": baseline,
                       "delta": delta, "relative": relative})
    return output


def number(value: int | float) -> str:
    return f"{value:,.1f}" if value % 1 else f"{int(value):,}"


def change(value: float | None) -> str:
    if value is None:
        return "unavailable (zero baseline)"
    size = abs(value * 100)
    decimals = 3 if 0 < size < 0.05 else 1
    return ("−" if value < 0 else "+") + f"{size:.{decimals}f}%"


def render(series: list[dict]) -> str:
    out = ['<noscript>', '<section class="nojs-atlas" aria-labelledby="nojs-title">',
           '<h3 id="nojs-title">Measured histories · available without JavaScript</h3>',
           '<p>Six <strong>preselected</strong> EN/RU Wikipedia pageview series, 11 August–14 September 2026. '
           'Retrieved 18 October 2026; <strong>not live or representative</strong>. '
           '“User” traffic is not verified people. Select a topic to read all 35 exact daily values.</p>',
           '<p class="fine">Comparison: last complete seven-day total (8–14 September) against the '
           'median of the preceding four complete weekly totals. This is not a validated trend label. '
           'Each table displays page requests, not unique readers or causal explanations.</p>']
    for series_item in series:
        title = series_item["title"].replace("_", " ")
        edition = "English" if series_item["edition"].startswith("en") else "Russian"
        url = "https://" + series_item["edition"] + "/wiki/" + quote(series_item["title"], safe="")
        delta = series_item["delta"]
        out.extend([
            '<details class="nojs-topic">',
            f'<summary><strong>{escape(title)} · {edition}</strong> '
            f'<span>8–14 Sep: {number(series_item["latest"])} views; '
            f'baseline: {number(series_item["baseline"])}; '
            f'change: {"−" if delta < 0 else "+"}{number(abs(delta))} '
            f'({change(series_item["relative"])})</span></summary>',
            '<div class="tablewrap"><table>',
            f'<caption>{escape(title)} · {edition}: 35 exact UTC daily pageviews</caption>',
            '<thead><tr><th scope="col">Date (UTC)</th><th scope="col">Pageviews</th></tr></thead>',
            '<tbody>',
        ])
        for row in series_item["rows"]:
            out.append(f'<tr><th scope="row">{row["date"]}</th><td>{number(row["views"])}</td></tr>')
        out.extend(['</tbody></table></div>',
                    f'<a class="source-link" href="{escape(url, quote=True)}" rel="noopener noreferrer" '
                    'target="_blank">View Wikipedia article ↗</a>',
                    '</details>'])
    out.extend(['<p class="fine">Evidence: Wikimedia Analytics API (CC0 data), '
                '<a href="../evidence/d02-20261018/provenance.json">source provenance</a>. '
                'This fallback is generated from the same retained snapshot used by the interactive atlas.</p>',
                '</section>', '</noscript>'])
    return "\n".join(out)


def updated_page(text: str, body: str) -> str:
    if text.count(START_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise ValueError("expected exactly one source-derived region")
    head, tail = text.split(START_MARKER, 1)
    _, after = tail.split(END_MARKER, 1)
    return head + START_MARKER + "\n" + body + "\n" + END_MARKER + after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if committed no-JS tables are stale")
    args = parser.parse_args()
    current = PAGE.read_text(encoding="utf-8")
    proposed = updated_page(current, render(verified_series()))
    if args.check:
        if current != proposed:
            parser.exit(1, "Stale generated tables: run python -m tools.build_nojs\n")
        print("PASS: no-JS tables match the 210 retained daily observations")
    else:
        PAGE.write_text(proposed, encoding="utf-8")
        print("Generated exact HTML tables from retained historical evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
