"""Build a deterministic, accessible LOCAL HTML atlas from one retained source bundle.

No source authentication, page-ID history, release promotion, Pages deployment or
live refresh is implied. The export cannot overwrite an earlier local preview.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import tempfile
import sys
from urllib.parse import urlencode


def _label(value: int | Fraction) -> str:
    value = Fraction(value)
    sign = "−" if value < 0 else ""
    n = abs(value.numerator)
    if value.denominator == 1:
        return sign + f"{n:,}"
    if value.denominator == 2:
        return sign + f"{n // 2:,}.5"
    raise ValueError("unexpected fractional pageview total")


def _signed(value: Fraction) -> str:
    return ("+" if value > 0 else "") + _label(value)


def _lift(delta: Fraction, baseline: Fraction) -> str:
    if baseline == 0:
        return "Unavailable (zero baseline)"
    with localcontext() as ctx:
        ctx.prec = 32
        result = (Decimal(delta.numerator) * Decimal(baseline.denominator) * 100 /
                  (Decimal(delta.denominator) * Decimal(baseline.numerator)))
    return "≈" + ("+" if result > 0 else "") + f"{result:.1f}%"


def _weekly(row: dict):
    daily = row["daily"]
    totals = [sum(point["views"] for point in daily[i:i + 7]) for i in range(0, 35, 7)]
    ordered = sorted(totals[:4])
    baseline = Fraction(ordered[1] + ordered[2], 2)
    return totals, baseline, Fraction(totals[-1]) - baseline



def _weekly_bars(weeks: list[int]) -> str:
    """Zero-origin, no-JavaScript five-week mini chart with exact accessible values."""
    if len(weeks) != 5 or any(type(value) is not int or value < 0 for value in weeks):
        raise ValueError("weekly chart needs five nonnegative integer totals")
    peak = max(weeks)
    bars = []
    for index, count in enumerate(weeks, 1):
        height = 0 if peak == 0 else (count * 100 + peak // 2) // peak
        bars.append(
            '<span class="week-bar"><span class="bar-track"><span class="bar-fill" '
            'style="height:' + str(height) + '%"></span></span><span class="bar-index">'
            + str(index) + '</span></span>'
        )
    values = "; ".join(f"week {index} {_label(count)}"
                       for index, count in enumerate(weeks, 1))
    return ('<div class="week-bars" role="img" aria-label="'
            + escape("Weekly requests, oldest to newest: " + values, quote=True)
            + '">' + "".join(bars) + '</div>')


def _uid(row: dict) -> str:
    return "detail-" + row["project"].replace(".", "-") + "-" + str(row["page_id"])


_FILTER_SCRIPT = r"""(function () {
    "use strict";
    const form = document.getElementById("atlas-filters");
    const results = document.getElementById("atlas-results");
    const empty = document.getElementById("atlas-empty");
    const cards = Array.from(document.querySelectorAll(".cards > .card"));
    const comparisonRows = Array.from(document.querySelectorAll("#compare-table tbody tr"));
    const compareResults = document.getElementById("compare-results");
    const compareEmpty = document.getElementById("compare-empty");
    const query = document.getElementById("atlas-query");
    const edition = document.getElementById("atlas-edition");
    const subject = document.getElementById("atlas-subject");
    const order = document.getElementById("atlas-order");
    const change = document.getElementById("atlas-change");
    const link = document.getElementById("atlas-filter-link");
    const warning = document.getElementById("atlas-filter-warning");
    const snapshot = document.getElementById("share-restore");
    const csvButton = document.getElementById("compare-csv");
    const csvStatus = document.getElementById("compare-csv-status");
    const cardsContainer = document.querySelector(".cards");
    const compareBody = document.querySelector("#compare-table tbody");
    if (!form || !results || !empty || !cards.length || !query || !edition ||
        !subject || !order || !change || !cardsContainer || !compareBody || !link || !warning || !snapshot || !compareResults ||
        !compareEmpty || !csvButton || !csvStatus ||
        comparisonRows.length !== cards.length ||
        !/^[0-9a-f]{64}$/.test(snapshot.dataset.dataset || "")) return;
    const bySeries = new Map(cards.map(card => [card.dataset.series, card]));
    const weekHeaders = Array.from(document.querySelectorAll(
        "#compare-table thead th[data-week-start]"));
    if (bySeries.size !== cards.length ||
        new Set(comparisonRows.map(row => row.dataset.series)).size !== cards.length ||
        comparisonRows.some(row => !bySeries.has(row.dataset.series)) ||
        typeof BigInt !== "function" ||
        cards.some(card => !/^-?\d+$/.test(card.dataset.delta2 || "") ||
            !/^\d+$/.test(card.dataset.baseline2 || "")) ||
        weekHeaders.length !== 5 || weekHeaders.some(th =>
            !/^\d{4}-\d{2}-\d{2}$/.test(th.dataset.weekStart || "") ||
            !/^\d{4}-\d{2}-\d{2}$/.test(th.dataset.weekEnd || ""))) return;
    const keys = ["af_dataset", "af_query", "af_edition", "af_subject"];
    const sortModes = new Set(["editorial", "increase", "decrease",
                               "relative-increase", "relative-decrease"]);
    const changeModes = new Set(["all", "positive", "negative", "unchanged"]);
    const originalPosition = new Map(cards.map((card, index) => [card.dataset.series, index]));
    const rowBySeries = new Map(comparisonRows.map(row => [row.dataset.series, row]));
    const normalized = value => value.normalize("NFC").toLocaleLowerCase();
    const params = new URLSearchParams(window.location.search);
    const requested = Array.from(params.keys()).some(key => key.startsWith("af_"));
    let invalid = false;
    if (requested) {
        const q = params.get("af_query");
        const ed = params.get("af_edition");
        const sub = params.get("af_subject");
        const sort = params.get("af_sort");
        const signed = params.get("af_change");
        invalid = Array.from(params.keys()).some(key =>
                !keys.includes(key) && key !== "af_sort" && key !== "af_change") ||
            keys.some(key => params.getAll(key).length !== 1) ||
            params.getAll("af_sort").length > 1 ||
            params.getAll("af_change").length > 1 ||
            (sort !== null && !sortModes.has(sort)) ||
            (signed !== null && !changeModes.has(signed)) ||
            params.get("af_dataset") !== snapshot.dataset.dataset ||
            q === null || q.length > 120 || q !== q.trim() ||
            q !== q.normalize("NFC") || /[\u0000-\u001f\u007f]/.test(q) ||
            !Array.from(edition.options).some(option => option.value === ed) ||
            !Array.from(subject.options).some(option => option.value === sub);
        if (!invalid) {
            query.value = q;
            edition.value = ed;
            subject.value = sub;
            order.value = sort === null ? "editorial" : sort;
            change.value = signed === null ? "all" : signed;
        }
    }
    function measuredOrder(a, b) {
        const fallback = originalPosition.get(a.dataset.series) -
            originalPosition.get(b.dataset.series);
        if (order.value === "editorial") return fallback;
        // The median of four integer weeks is integral or half-integral.
        // Compare doubled exact deltas without lossy Number conversion.
        const left = BigInt(a.dataset.delta2);
        const right = BigInt(b.dataset.delta2);
        if (order.value.startsWith("relative-")) {
            // Compare signed delta / median as exact rationals; tiny medians
            // are allowed but disclosed, while zero is never a percentage.
            const leftBase = BigInt(a.dataset.baseline2);
            const rightBase = BigInt(b.dataset.baseline2);
            if (leftBase === 0n || rightBase === 0n) {
                if (leftBase === rightBase) return fallback;
                return leftBase === 0n ? 1 : -1;
            }
            const difference = left * rightBase - right * leftBase;
            if (difference === 0n) return fallback;
            return ((difference > 0n) ===
                (order.value === "relative-increase")) ? -1 : 1;
        }
        if (left === right) return fallback;
        return ((left > right) === (order.value === "increase")) ? -1 : 1;
    }
    function update() {
        const text = normalized(query.value.trim());
        let shown = 0;
        const visible = new Set();
        for (const card of cards) {
            // Exact, integer doubled-delta sign; neither floating-point rounding
            // nor a lifecycle/causal label is involved in this filter.
            const signedDelta = BigInt(card.dataset.delta2);
            const signMatches = change.value === "all" ||
                (change.value === "positive" && signedDelta > 0n) ||
                (change.value === "negative" && signedDelta < 0n) ||
                (change.value === "unchanged" && signedDelta === 0n);
            const match = normalized(card.dataset.title || "").includes(text) &&
                (edition.value === "all" || edition.value === card.dataset.edition) &&
                (subject.value === "all" || subject.value === card.dataset.subject) &&
                signMatches;
            card.hidden = !match;
            if (match) {
                shown++;
                visible.add(card.dataset.series);
            }
        }
        for (const row of comparisonRows) row.hidden = !visible.has(row.dataset.series);
        // Keep the cards, exact-value comparison and exported CSV in the same order.
        for (const card of cards.slice().sort(measuredOrder)) {
            cardsContainer.appendChild(card);
            compareBody.appendChild(rowBySeries.get(card.dataset.series));
        }
        compareResults.textContent = "Showing " + shown + " of " + comparisonRows.length +
            " selected title histories in this comparison.";
        compareEmpty.hidden = shown !== 0;
        results.textContent = "Showing " + shown + " of " + cards.length +
            " selected title histories (not all Wikipedia pages).";
        empty.hidden = shown !== 0;
        const url = new URL(window.location.href);
        url.search = "";
        url.hash = "overview";
        url.searchParams.set("af_dataset", snapshot.dataset.dataset);
        url.searchParams.set("af_query", query.value.trim().normalize("NFC").slice(0, 120));
        url.searchParams.set("af_edition", edition.value);
        url.searchParams.set("af_subject", subject.value);
        url.searchParams.set("af_sort", order.value);
        url.searchParams.set("af_change", change.value);
        link.href = url.toString();
        csvButton.disabled = shown === 0;
    }
    function csvCell(value, protectFormula) {
        // Guard formula-leading titles, including whitespace prefixes. Keep exact
        // request-count strings as text; never round through JavaScript Number.
        let raw = String(value).replace(/[\r\n\t]/g, " ");
        if (protectFormula && /^[\s\u200b-\u200d\u2060\ufeff]*[=+\-@\u2212]/u.test(raw)) raw = "'" + raw;
        return '"' + raw.replace(/"/g, '""') + '"';
    }
    function countText(value) {
        const raw = String(value).trim();
        if (!/^(?:\d+|\d{1,3}(?:,\d{3})+)$/.test(raw))
            throw new Error("invalid exact weekly request count");
        return raw.replace(/,/g, "");
    }
    function deltaText(value) {
        const raw = String(value).trim().replace(/^\u2212/, "-").replace(/,/g, "");
        if (!/^[+-]?\d+(?:\.5)?$/.test(raw))
            throw new Error("invalid exact baseline delta");
        return raw;
    }
    function downloadCsv() {
        const selected = Array.from(compareBody.querySelectorAll("tr")).filter(row => !row.hidden);
        if (!selected.length) return;
        const headings = [
            "dataset_sha256", "method_version", "observation_end_utc",
            "snapshot_series_key", "edition", "title", "subject",
            ...weekHeaders.map(th => th.dataset.weekStart + "_to_" +
                               th.dataset.weekEnd + "_requests"),
            "last_week_minus_four_week_median_requests"
        ];
        const lines = [headings.map(value => csvCell(value, false)).join(",")];
        for (const row of selected) {
            const card = bySeries.get(row.dataset.series);
            const cells = Array.from(row.querySelectorAll("td"));
            const title = row.querySelector("th a");
            if (!card || !title || cells.length !== 6)
                throw new Error("incomplete comparison row");
            const columns = [
                snapshot.dataset.dataset, snapshot.dataset.method, snapshot.dataset.end,
                row.dataset.series, card.dataset.edition, title.textContent,
                card.dataset.subject, ...cells.slice(0, 5).map(cell =>
                    countText(cell.textContent)), deltaText(cells[5].textContent)
            ];
            if (columns.length !== headings.length)
                throw new Error("incompatible comparison schema");
            // Metadata/title are untrusted text; week counts and signed delta
            // were strictly parsed as numeric strings and must stay numeric.
            lines.push(columns.map((value, index) => csvCell(value, index < 7)).join(","));
        }
        const bytes = "\ufeff" + lines.join("\r\n") + "\r\n";
        const blobUrl = URL.createObjectURL(new Blob([bytes], {type: "text/csv;charset=utf-8"}));
        const anchor = document.createElement("a");
        anchor.href = blobUrl;
        anchor.download = "dayflare-weekly-" + snapshot.dataset.dataset.slice(0, 12) + ".csv";
        anchor.hidden = true;
        document.body.appendChild(anchor);
        try {
            anchor.click();
        } finally {
            anchor.remove();
            setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
        }
        csvStatus.textContent = "CSV prepared for " + selected.length +
            " selected title histories. Your browser handles saving the file.";
    }
    function changed() {
        csvStatus.textContent = "";
        warning.hidden = true;
        update();
    }
    if (typeof Blob === "function" && typeof URL.createObjectURL === "function") {
        csvButton.hidden = false;
        csvButton.addEventListener("click", () => {
            try {
                downloadCsv();
            } catch (error) {
                csvStatus.textContent =
                    "CSV unavailable: an exact comparison value was invalid. Use the table below.";
            }
        });
    }
    form.addEventListener("input", changed);
    form.addEventListener("change", changed);
    form.addEventListener("submit", event => event.preventDefault());
    form.addEventListener("reset", () => setTimeout(changed, 0));
    form.hidden = false;
    link.hidden = false;
    update();
    if (invalid) {
        warning.hidden = false;
        warning.textContent = "This filtered link is invalid or belongs to a different dataset. Showing all selected histories; no substitute was loaded.";
    }
})();"""


_AGE_SCRIPT = r"""(function () {
    "use strict";
    const age = document.getElementById("atlas-observation-age");
    if (!age) return;
    const observedEnd = age.dataset.observedEnd || "";
    function unavailable() {
        age.textContent = "Age unavailable (device clock or observation date mismatch). Archived, not live.";
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(observedEnd)) { unavailable(); return; }
    const observedMs = Date.parse(observedEnd + "T00:00:00Z");
    if (!Number.isFinite(observedMs) ||
        new Date(observedMs).toISOString().slice(0, 10) !== observedEnd) {
        unavailable();
        return;
    }
    const now = new Date();
    const todayMs = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    const days = (todayMs - observedMs) / 86400000;
    if (!Number.isSafeInteger(days) || days < 0) { unavailable(); return; }
    age.textContent = "That was " + days + " complete UTC calendar day" +
        (days === 1 ? "" : "s") + " ago (according to your device clock). Archived, not live.";
})();"""

def render_html(candidate: dict, seed: dict, proof: dict) -> bytes:
    """Render *already-verified* source inputs; caller enforces byte-bound proof."""
    by_id = {(x["project"], x["page_id"]): x["subject"] for x in seed["pages"]}
    rows = candidate["series"]
    first = date.fromisoformat(candidate["observation_end"]) - timedelta(days=34)
    end = candidate["observation_end"]
    observed = first.isoformat() + " – " + end
    synthetic = proof["provenance_status"] == "synthetic_injected_not_upstream_evidence"
    status = ("SYNTHETIC TEST DATA — NOT WIKIPEDIA EVIDENCE" if synthetic else
              "LOCAL EVIDENCE — UPSTREAM ORIGIN NOT INDEPENDENTLY VERIFIED")
    base = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta name="color-scheme" content="dark">',
        '<title>Dayflare · dated attention atlas (local preview)</title>',
        '<style>',
        ':root{color-scheme:dark;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;',
        'background:#091527;color:#f6f7fa;line-height:1.55}*{box-sizing:border-box}',
        'body{margin:0}a{color:#8be6e2;text-underline-offset:.18em}',
        'a:focus-visible,summary:focus-visible{outline:3px solid #ffca7f;outline-offset:4px}',
        '.skip{position:absolute;top:-5rem;left:1rem;background:#f5f5f1;color:#071627;padding:.7rem}',
        '.skip:focus{top:1rem;z-index:5}.wrap{width:min(1160px,calc(100% - 2rem));margin:auto}',
        'header{padding:3.2rem 0 2.4rem;background:linear-gradient(130deg,#143957,#0a1c32 75%);',
        'border-bottom:1px solid #3c566c}.eyebrow{font-size:.82rem;text-transform:uppercase;',
        'letter-spacing:.13em;color:#8be6e2;font-weight:750}',
        'h1{font-size:clamp(2.2rem,6vw,4rem);line-height:1.12;margin:.5rem 0}',
        '.lead{font-size:clamp(1.05rem,2.4vw,1.3rem);max-width:65ch;color:#e1e8f0}',
        '.hero-action{display:inline-flex;align-items:center;justify-content:center;min-height:44px;',
        'padding:.7rem 1rem;border-radius:.65rem;background:#8be6e2;color:#062033;',
        'font-weight:800;text-decoration:none;margin:.25rem 0 0;max-width:100%;text-align:center}',
        '.hero-action:focus-visible{outline:3px solid #ffca7f;outline-offset:4px}',
        '.warning{padding:.8rem 1rem;border:1px solid #ffe6ac;border-left:5px solid #ffbe63;',
        'background:#352b26;color:#fff3dc;border-radius:.45rem;margin:1.5rem 0}',
        '.metadata{display:flex;gap:.8rem 2rem;flex-wrap:wrap;color:#e6edf7;font-size:.95rem}',
        '.archive-age{margin:1.1rem 0 0;padding:.65rem .9rem;background:#152a42;',
        'border:1px solid #58748a;border-left:4px solid #8be6e2;border-radius:.45rem;color:#f4f8fc}',
        'main{padding:2rem 0 5rem}h2{font-size:clamp(1.5rem,3vw,2rem);margin:2.1rem 0 1rem}',
        '.muted{color:#c7d5e4}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));',
        'gap:1rem;margin:1.4rem 0 2rem}.card,article{background:#12253b;border:1px solid #3b5970;',
        'border-radius:1rem;padding:1.2rem}.card h3{font-size:1.2rem;line-height:1.35;margin:.3rem 0}',
        '.badge{font-size:.8rem;letter-spacing:.05em;text-transform:uppercase;color:#aee7d7}',
        '.number{font-variant-numeric:tabular-nums;font-size:1.65rem;font-weight:800;margin:.3rem 0}',
        '.stat{font-variant-numeric:tabular-nums;color:#f1e5b7}',
        '.week-bars{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));',
        'gap:.4rem;margin:.9rem 0 .2rem}',
        '.week-bar{display:flex;flex-direction:column;gap:.2rem;min-width:0}',
        '.bar-track{display:flex;align-items:flex-end;height:3.4rem;background:#203d54;',
        'border:1px solid #425f78;border-radius:.25rem;overflow:hidden}',
        '.bar-fill{display:block;width:100%;background:#8be6e2}',
        '.bar-index{text-align:center;font-size:.76rem;color:#d3e2ee}',
        '.chart-note{font-size:.84rem;margin:.15rem 0 .8rem;color:#d3e2ee}',
        '.share-action{margin:.6rem 0 0;font-weight:650}',
        '.share-restore{display:none;padding:1.2rem;margin:1rem 0;border:2px solid #8be6e2;',
        'background:#19354c;border-radius:.75rem}.share-restore:target{display:block}',
        '.scroll{overflow-x:auto;max-width:100%;border:1px solid #3b5970;border-radius:.7rem;',
        'background:#102238;margin:.8rem 0 1.5rem}table{border-collapse:collapse;width:100%;',
        'font-variant-numeric:tabular-nums;font-size:.95rem}th,td{padding:.7rem .8rem;text-align:right;',
        'border-bottom:1px solid #2c455d;white-space:nowrap}th:first-child,td:first-child{text-align:left}',
        'thead{background:#223b53}tbody tr:nth-child(even){background:#1a3047}',
        'tbody tr:hover{background:#25445c}caption{text-align:left;padding:.8rem;white-space:normal;',
        'color:#e2edf7}article{margin:1.5rem 0}article h3{font-size:1.5rem;margin:.2rem 0}',
        'article .metrics{display:flex;gap:1.5rem;flex-wrap:wrap;margin:1rem 0}',
        '.metrics p{margin:.2rem 0}details{border:1px solid #41637a;border-radius:.55rem;',
        'padding:.6rem .8rem;margin:1rem 0;overflow-wrap:anywhere}',
        'summary{cursor:pointer;font-weight:700;min-height:2rem}',
        '.source{overflow-wrap:anywhere}footer{overflow-wrap:anywhere;border-top:1px solid #3b5970;',
        'padding:2rem 0;color:#c7d5e4}small{font-size:.85rem}',
        '@media(max-width:560px){header{padding:2rem 0}article,.card{padding:1rem}',
        'th,td{padding:.55rem .65rem}.metadata{display:block}.metadata span{display:block;margin:.3rem 0}}',
        '@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important}}',
        '#atlas-filters[hidden],#atlas-empty[hidden],#compare-empty[hidden],',
        '.cards>.card[hidden],#compare-table tbody tr[hidden]{display:none!important}',
        '#atlas-filters{display:flex;flex-wrap:wrap;align-items:end;gap:.8rem;',
        'padding:1rem;border:1px solid #41637a;background:#102238;',
        'border-radius:.75rem;margin:1rem 0}',
        '#atlas-filters label{display:grid;gap:.25rem;font-weight:650;min-width:0}',
        '#atlas-filters input,#atlas-filters select{font:inherit;background:#071827;',
        'color:#fff;border:1px solid #60809a;border-radius:.45rem;',
        'min-height:2.7rem;padding:.55rem;max-width:100%}',
        '#atlas-filters input{width:min(100%,18rem)}',
        '#atlas-filters select{width:100%;min-width:0}',
        '#atlas-filters button{font:inherit;background:#8be6e2;color:#062033;',
        'border:0;border-radius:.45rem;min-height:2.7rem;padding:.55rem .9rem;',
        'cursor:pointer;font-weight:700}',
        '#atlas-filters :is(input,select,button):focus-visible{outline:3px solid #ffca7f;outline-offset:2px}',
        '.filter-link{display:inline-block;margin:.1rem 0 .9rem;font-weight:700}',
        '#atlas-filter-link[hidden]{display:none}',
        '#compare-csv{font:inherit;font-weight:700;background:#8be6e2;color:#062033;',
        'border:0;border-radius:.55rem;min-height:44px;padding:.6rem 1rem;cursor:pointer}',
        '#compare-csv:focus-visible{outline:3px solid #ffca7f;outline-offset:3px}',
        '#compare-csv:disabled{opacity:.5;cursor:not-allowed}',
        '#compare-csv[hidden]{display:none!important}',
        '.filter-warning{padding:.8rem 1rem;border:2px solid #ffca7f;background:#352b26;color:#fff3dc}',
        '@media(max-width:560px){#atlas-filters{display:grid}#atlas-filters input{width:100%}}',
        '</style></head><body>',
        '<a class="skip" href="#main">Skip to atlas</a>',
        '<header><div class="wrap"><div class="eyebrow">Dayflare / EN + RU Wikipedia</div>',
        '<h1>Where did attention change?</h1>',
        '<p class="lead">Explore selected title histories as measured daily request counts. ',
        'Inspect five full weeks, exact values and original source endpoints—without opaque scores.</p>',
        '<a class="hero-action" href="#overview">Explore ' + str(len(rows)) +
        ' measured histories ↓</a>',
        '<div class="warning" role="note"><strong>' + escape(status) + '</strong>. ',
        'This is an offline preview, <strong>not</strong> a public release, live feed, ',
        'stable historical page-ID series or representative ranking.</div>',
        '<div class="metadata"><span><strong>Observed:</strong> ' + escape(observed) + ' UTC</span>',
        '<span><strong>Retrieved:</strong> ' + escape(candidate["retrieved_at"]) + '</span>',
        '<span><strong>Series:</strong> ' + str(len(rows)) + ' selected titles</span></div>',
        '<p class="archive-age"><strong>Archive age:</strong> Last observed <time datetime="' +
        escape(end, quote=True) + '">' + escape(end) + ' UTC</time>. ',
        '<span id="atlas-observation-age" data-observed-end="' + escape(end, quote=True) +
        '">Historical archive; age cannot be calculated without JavaScript. Not live.</span></p></div></header>',
        '<main id="main" class="wrap">',
        '<section class="share-restore" id="share-restore" tabindex="-1" role="status" aria-live="polite"',
        ' data-dataset="' + escape(proof["candidate_sha256"], quote=True) +
        '" data-method="' + escape(candidate["method_version"], quote=True) +
        '" data-end="' + escape(end, quote=True) + '">',
        '<p id="share-message">This dataset-bound share requires JavaScript to restore the exact history. ',
        'You can still browse all available dated evidence below.</p>',
        '<p><a href="#overview">Browse current snapshot</a></p></section>',
        '<h2 id="overview">Discover a measured change</h2>',
        '<p class="muted">Browse selected English and Russian titles, or filter by ',
        'edition, subject and exact weekly change.</p>',
        '<details id="atlas-method" class="method-explainer">',
        '<summary>How the weekly change is measured</summary>',
        '<p>Cards compare the last complete seven days with the median of the ',
        'four preceding complete seven-day totals. A larger share is not proof of a cause. ',
        'Choose a title to inspect its 35 exact daily observations and evidence.</p>',
        '<p>Order by exact last-week change in requests (last week minus the ',
        'four-week median), not by importance or Wikipedia-wide popularity. ',
        'Relative ordering divides that exact signed difference by the ',
        'four-week median, without rounding. Zero baselines are unavailable ',
        'and sort last in both directions; tiny baselines can magnify ',
        'percentages. No thresholds or lifecycle classes are inferred. ',
        'The original editorial selection is preserved without JavaScript.</p>',
        '<p>Filter by the exact signed difference: positive, negative or ',
        'zero. This is a measured comparison, <strong>not</strong> a validated ',
        'rising, returning or fading classification.</p>',
        '</details>',
        '<form id="atlas-filters" aria-label="Filter selected titles" hidden>',
        '<label for="atlas-query">Find a title<input id="atlas-query" type="search" ',
        'autocomplete="off" maxlength="120" placeholder="Search English or Russian titles"></label>',
        '<label for="atlas-edition">Edition<select id="atlas-edition">',
        '<option value="all">Both editions</option>',
        '<option value="en.wikipedia">English</option>',
        '<option value="ru.wikipedia">Russian</option></select></label>',
        '<label for="atlas-subject">Subject<select id="atlas-subject">',
        '<option value="all">All subjects</option>',
        "".join('<option value="' + escape(subject, quote=True) + '">' +
                escape(subject.replace("/", " / ").title()) + '</option>'
                for subject in sorted(set(by_id.values()))),
        '</select></label>',
        '<label for="atlas-order">Sort by weekly change<select id="atlas-order">',
        '<option value="editorial">Original</option>',
        '<option value="increase">Increase</option>',
        '<option value="decrease">Decrease</option>',
        '<option value="relative-increase">Relative rise (%)</option>',
        '<option value="relative-decrease">Relative fall (%)</option>',
        '</select></label>',
        '<label for="atlas-change">Exact weekly change<select id="atlas-change">',
        '<option value="all">All changes</option>',
        '<option value="positive">Increase</option>',
        '<option value="negative">Decrease</option>',
        '<option value="unchanged">No change</option>',
        '</select></label><button type="reset">Show all</button></form>',
        '<p id="atlas-filter-warning" class="filter-warning" role="alert" hidden></p>',
        '<a id="atlas-filter-link" class="filter-link" href="#overview" hidden>Open a link to these filters ↗</a>',
        '<p id="atlas-results" role="status" aria-live="polite">All ' +
        str(len(rows)) + ' selected titles shown.</p>',
        '<p id="atlas-empty" hidden>No matching titles in this selected archive. ',
        'Use Show all to restore every history.</p>',
        '<div class="cards">'
    ]
    entries = []
    for row in rows:
        weeks, baseline, delta = _weekly(row)
        subject = by_id[(row["project"], row["page_id"])]
        title = escape(row["title"])
        edition = "EN" if row["project"] == "en.wikipedia" else "RU"
        ident = _uid(row)
        share_query = urlencode({
            "df_dataset": proof["candidate_sha256"],
            "df_method": candidate["method_version"],
            "df_end": end,
            "df_edition": row["project"],
            "df_page": str(row["page_id"]),
        })
        entries.append((row, weeks, baseline, delta, subject, edition, ident))
        base.extend([
            '<div class="card" data-series="' + ident + '" data-title="' + escape(row["title"], quote=True) +
            '" data-edition="' + escape(row["project"], quote=True) +
            '" data-subject="' + escape(subject, quote=True) +
            '" data-delta2="' + str((delta * 2).numerator) +
            '" data-baseline2="' + str((baseline * 2).numerator) +
            '"><div class="badge">' + edition + ' · ' + escape(subject) + '</div>',
            '<h3><a href="#' + ident + '">' + title + '</a></h3>',
            '<p class="number">' + _label(weeks[-1]) + ' <small>requests / week</small></p>',
            '<p class="stat">' + escape(_signed(delta)) + ' vs baseline · ' + escape(_lift(delta,baseline)) + '</p>',
            _weekly_bars(weeks),
            '<p class="chart-note">Five complete weeks (1–5), bars start at zero; '
            'each title has its own scale. <a href="#compare">Exact weekly values</a></p>',
            '<p class="muted"><small>Last week is ' + escape((date.fromisoformat(end) - timedelta(days=6)).isoformat()) + ' – ' + escape(end) + ' UTC</small></p>',
            '<p class="share-action"><a href="?' + escape(share_query, quote=True) +
            '#share-restore">Share this exact history</a></p>',
            '</div>'
        ])
    base.extend(['</div><h2 id="compare">Compare exact weekly counts</h2>',
                 '<p class="muted">All rows use equivalent all-access/user request filters ',
                 'and the same complete UTC dates. These are selected title queries—not ',
                 'matched subjects across editions or population measurements. ',
                 'With JavaScript this table follows discovery filters; exact daily ',
                 'evidence remains available below.</p>',
                 '<p id="compare-results">All '+
                 str(len(rows))+' selected title histories compared.</p>',
                 '<p><button type="button" id="compare-csv" hidden>Download visible weekly CSV</button> '
                 '<span class="muted">Dataset-bound CSV; counts are requests, not people.</span></p>',
                 '<p id="compare-csv-status" role="status" aria-live="polite"></p>',
                 '<p id="compare-empty" hidden>No matching histories in this weekly ',
                 'comparison. Use Show all above.</p>',
                 '<div class="scroll" tabindex="0" aria-label="Scrollable weekly comparison table">',
                 '<table id="compare-table"><caption>Five complete seven-day weeks (oldest first); exact request totals</caption><thead><tr>',
                 '<th scope="col">Title / edition</th>'])
    for n in range(5):
        week_start = first + timedelta(days=7*n)
        week_end = week_start + timedelta(days=6)
        base.append('<th scope="col" data-week-start="' + week_start.isoformat() +
                    '" data-week-end="' + week_end.isoformat() + '">' +
                    week_start.strftime('%b %d') + '–' + week_end.strftime('%b %d') + '</th>')
    base.extend(['<th scope="col">Δ vs median</th></tr></thead><tbody>'])
    for row, weeks, baseline, delta, subject, edition, ident in entries:
        base.append('<tr data-series="'+ident+'"><th scope="row"><a href="#'+ ident +'">' + escape(row["title"]) + '</a> ('+edition+')</th>')
        base.extend('<td>'+_label(total)+'</td>' for total in weeks)
        base.append('<td>'+escape(_signed(delta))+'</td></tr>')
    base.extend(['</tbody></table></div><h2 id="evidence">Inspect exact daily history &amp; evidence</h2>'])
    for row, weeks, baseline, delta, subject, edition, ident in entries:
        base.extend(['<article id="'+ident+'" aria-labelledby="heading-'+ident+'">',
                     '<div class="badge">'+edition+' · '+escape(subject)+'</div>',
                     '<h3 id="heading-'+ident+'">'+escape(row["title"])+'</h3>',
                     '<p class="muted">Provided current page ID '+str(row["page_id"])+
                     '; title-scoped measurements do not verify historical ID continuity.</p>',
                     '<div class="metrics"><p><strong>Last week</strong><br>'+_label(weeks[-1])+'</p>',
                     '<p><strong>Four-week median</strong><br>'+_label(baseline)+'</p>',
                     '<p><strong>Absolute Δ</strong><br>'+escape(_signed(delta))+'</p>',
                     '<p><strong>Relative Δ</strong><br>'+escape(_lift(delta,baseline))+'</p></div>',
                     '<div class="scroll" tabindex="0" aria-label="Scrollable exact daily history for '+escape(row["title"],quote=True)+'">',
                     '<table><caption>Daily all-access/user requests · '+escape(observed)+' UTC</caption>',
                     '<thead><tr><th scope="col">UTC date</th><th scope="col">Requests</th></tr></thead><tbody>'])
        for point in row["daily"]:
            base.append('<tr><th scope="row">'+escape(point["date"])+'</th><td>'+_label(point["views"] )+'</td></tr>')
        source=row["source"]
        base.extend(['</tbody></table></div><details><summary>View source endpoint and retained-body SHA-256</summary>',
                     '<p><strong>Source:</strong> <a class="source" href="'+escape(source["endpoint"],quote=True)+'" rel="noopener noreferrer">'+escape(source["endpoint"])+'</a></p>',
                     '<p><strong>Requested:</strong> '+escape(source["requested_at"])+
                     ' · HTTP '+str(source["http_status"])+'</p>',
                     '<p><strong>Decoded response SHA-256:</strong><br><code class="source">'+escape(source["body_sha256"])+'</code></p>',
                     '<p class="muted">Receipt agreement is not independent verification of Wikimedia origin, source licensing or page moves.</p>',
                     '</details><p><a href="#overview">↑ Back to discovery</a> · <a href="#compare">Weekly comparison</a></p></article>'])
    base.extend(['</main><footer><div class="wrap"><strong>What these counts mean:</strong> ',
                 'Requests are not unique people, approval, importance or causation. ',
                 'A selected title absent from another source is not zero interest. ',
                 'A provider-reported zero appears only as an observed response value; ',
                 'missing days reject the entire candidate. English and Russian are ',
                 'Wikipedia editions, not countries. A rolling preview is not a live publication.',
                 '<p><small>Dataset '+escape(candidate["dataset_id"])+
                 ' · method '+escape(candidate["method_version"])+
                 ' · canonical candidate SHA-256 '+escape(proof["candidate_sha256"])+'</small></p>',
                 '</div></footer><script>',
                 _FILTER_SCRIPT,
                 '</script><script>',
                 Path(__file__).with_name("m1_dataset_share.js").read_text(encoding="utf-8"),
                 '</script><script>',
                  _AGE_SCRIPT,
                  '</script></body></html>\n'])
    return "".join(base).encode("utf-8")


def export_verified_preview(bundle: Path, destination: Path, *, now=None) -> dict:
    """Never overwrite output or export unverified/tampered candidate bytes."""
    from .rolling_pageview_source import (SourceError, _atomic_new_dir, _bytes, sha,
                                          strict_json, verify_bundle, MAX_BYTES, MAX_SEED_BYTES)
    bundle, destination = Path(bundle), Path(destination)
    proof = verify_bundle(bundle, now=now)
    candidate_raw = _bytes(bundle / "candidate.json", MAX_BYTES)
    seed_raw = _bytes(bundle / "seeds.json", MAX_SEED_BYTES)
    if sha(candidate_raw) != proof["candidate_sha256"] or sha(seed_raw) != proof["seed_sha256"]:
        raise SourceError("source input changed after verification; no preview")
    doc = strict_json(candidate_raw, "candidate", max_bytes=MAX_BYTES)
    seed = strict_json(seed_raw, "seed", max_bytes=MAX_SEED_BYTES)
    html = render_html(doc, seed, proof)
    if destination.exists() or destination.is_symlink():
        raise SourceError("preview destination already exists; cannot replace previous evidence")
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise SourceError("preview parent must be existing real directory")
    # Invariant rechecked before publish; this still does not authenticate origin.
    repeated = verify_bundle(bundle, now=now)
    if repeated != proof:
        raise SourceError("source verification changed during preview build")
    manifest = {
        "schema_version": "dayflare.local-rolling-preview.v1",
        "candidate_sha256": proof["candidate_sha256"],
        "source_seed_sha256": proof["seed_sha256"],
        "html_sha256": sha256(html).hexdigest(),
        "dataset_id": doc["dataset_id"],
        "observation_end": doc["observation_end"],
        "retrieved_at": doc["retrieved_at"],
        "series": len(doc["series"]),
        "provenance_status": proof["provenance_status"],
        "publication_status": "LOCAL_PREVIEW_NOT_PUBLISHED",
    }
    from .rolling_window_gate import canonical
    with tempfile.TemporaryDirectory(prefix=".dayflare-preview-", dir=destination.parent) as name:
        tmp = Path(name)
        (tmp / "index.html").write_bytes(html)
        (tmp / "preview-manifest.json").write_bytes(canonical(manifest))
        if sha256((tmp / "index.html").read_bytes()).hexdigest() != manifest["html_sha256"]:
            raise SourceError("preview HTML readback mismatch")
        _atomic_new_dir(tmp, destination)
    return manifest



def export_staged_current_preview(stage_root: Path, destination: Path) -> dict:
    """Export the accepted LOCAL v2 source version, never an unchecked candidate.

    Hold the same advisory lock as stage() across verification and the atomic
    no-replace preview export. Another cooperative refresh cannot advance the
    current pointer between selection and publication of this local HTML.
    """
    from .rolling_window_gate import stamp
    from .stage_rolling_version import (
        StageError, SOURCE_SCHEMA, _check_directory, _current, _exclusive,
        _version_files,
    )

    stage_root = Path(stage_root)
    _check_directory(stage_root)
    _check_directory(stage_root / "versions")  # Reject an intermediate symlink.
    with _exclusive(stage_root):
        pointer = _current(stage_root)
        if pointer is None:
            raise StageError("no current staged version to preview")
        digest = pointer["version_sha256"]
        version = _version_files(stage_root, digest)
        if version["schema_version"] != SOURCE_SCHEMA:
            raise StageError("current version is candidate-only v1; retained source required")
        # The historical retrieval instant, not today's date, defines the
        # completeness gate for byte-for-byte archived source replay.
        return export_verified_preview(
            stage_root / "versions" / digest / "source",
            destination,
            now=stamp(pointer["retrieved_at"]),
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-stage", action="store_true",
                        help="export the verified current immutable v2 stage, not a source bundle")
    parser.add_argument("source_bundle", type=Path,
                        help="retained source bundle, or stage root with --from-stage")
    parser.add_argument("local_preview_directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.from_stage:
            result = export_staged_current_preview(args.source_bundle, args.local_preview_directory)
        else:
            result = export_verified_preview(args.source_bundle, args.local_preview_directory)
    except (OSError, ValueError) as exc:
        print(f"PREVIEW_REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
