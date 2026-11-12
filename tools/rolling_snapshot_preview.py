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
from urllib.parse import quote, urlencode


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



def _weekly_bars(weeks: list[int], observation_end: str) -> str:
    """Zero-origin five-week chart with visible UTC dates and exact accessible values."""
    if len(weeks) != 5 or any(type(value) is not int or value < 0 for value in weeks):
        raise ValueError("weekly chart needs five nonnegative integer totals")
    try:
        if type(observation_end) is not str:
            raise ValueError("non-string UTC date")
        end = date.fromisoformat(observation_end)
        if end.isoformat() != observation_end:
            raise ValueError("noncanonical UTC date")
        first = end - timedelta(days=34)
    except (ValueError, OverflowError) as exc:
        raise ValueError("weekly chart needs canonical complete UTC observation end") from exc
    # Fixed English month names avoid locale-dependent published HTML/checksums.
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul",
              "Aug", "Sep", "Oct", "Nov", "Dec")
    peak = max(weeks)
    bars, values = [], []
    for index, count in enumerate(weeks):
        week_start = first + timedelta(days=index * 7)
        week_end = week_start + timedelta(days=6)
        height = 0 if peak == 0 else (count * 100 + peak // 2) // peak
        bars.append(
            '<span class="week-bar"><span class="bar-track"><span class="bar-fill" '
            'style="height:' + str(height) + '%"></span></span><time class="bar-index" datetime="'
            + week_start.isoformat() + '">' + f"{week_start.day:02d} "
            + months[week_start.month - 1] + '</time></span>'
        )
        values.append(f"week {index + 1} {week_start.isoformat()} to "
                      f"{week_end.isoformat()} UTC: {_label(count)} requests")
    return ('<div class="week-bars" role="img" aria-label="'
            + escape("Weekly requests, oldest to newest: " + "; ".join(values), quote=True)
            + '">' + "".join(bars) + '</div>')


def _daily_curve(daily: list[dict]) -> str:
    """Zero-origin, no-JavaScript 35-day history plot; exact values remain tabular."""
    if (len(daily) != 35 or any(type(point) is not dict or
        type(point.get("views")) is not int or point["views"] < 0 or
        type(point.get("date")) is not str for point in daily)):
        raise ValueError("daily chart needs 35 dated nonnegative integer observations")
    # The x coordinates assume adjacent UTC days. Never compress a missing day
    # or plot duplicates/out-of-order observations as an uninterrupted history.
    try:
        first_day = date.fromisoformat(daily[0]["date"])
        for index, point in enumerate(daily):
            observed_day = date.fromisoformat(point["date"])
            if (point["date"] != observed_day.isoformat() or
                    (observed_day - first_day).days != index):
                raise ValueError("nonconsecutive or noncanonical day")
    except ValueError as exc:
        raise ValueError("daily chart needs 35 consecutive canonical UTC dates") from exc
    peak = max(point["views"] for point in daily)
    points = " ".join(
        f'{12 + index * 10},{90 - ((point["views"] * 74 + peak // 2) // peak if peak else 0)}'
        for index, point in enumerate(daily)
    )
    first, last = daily[0]["date"], daily[-1]["date"]
    label = ("Daily requests, " + first + " to " + last + " UTC; peak " +
             f"{peak:,}" + " requests; zero-origin chart. Exact values in the table below.")
    return ('<figure class="daily-curve"><svg viewBox="0 0 364 104" role="img" '
            'aria-label="' + escape(label, quote=True) + '">'
            '<line class="daily-zero" x1="12" y1="90" x2="352" y2="90"/>'
            '<polyline class="daily-line" points="' + points + '"/>'
            '</svg><figcaption>35 daily requests · ' + escape(first) + ' → ' + escape(last) +
            ' UTC · peak ' + f"{peak:,}" +
            '. Zero-origin; exact values below.</figcaption></figure>')


def _uid(row: dict) -> str:
    return "detail-" + row["project"].replace(".", "-") + "-" + str(row["page_id"])


def _article_href(project: str, title: str) -> str:
    """Link an observed title to its edition, without claiming ID continuity."""
    hosts = {"en.wikipedia": "en.wikipedia.org", "ru.wikipedia": "ru.wikipedia.org"}
    try:
        host = hosts[project]
    except KeyError as exc:
        raise ValueError("unsupported Wikipedia edition for title link") from exc
    return "https://" + host + "/wiki/" + quote(title.replace(" ", "_"), safe="")


def _page_id_href(project: str, page_id: int) -> str:
    """Link the selected numeric ID to the CURRENT page, not a 35-day ID history."""
    hosts = {"en.wikipedia": "en.wikipedia.org", "ru.wikipedia": "ru.wikipedia.org"}
    if project not in hosts:
        raise ValueError("unsupported Wikipedia edition for page-ID link")
    if type(page_id) is not int or not 0 < page_id <= 9007199254740991:
        raise ValueError("page ID must be a positive safe integer")
    return "https://" + hosts[project] + "/wiki/Special:Redirect/page/" + str(page_id)


def _spotlights(rows: list[dict], observation_end: str) -> tuple[str, str]:
    """No-JS exact sample highlights: largest signed absolute weekly changes.

    Stable editorial order breaks ties. Never infer a lifecycle label, cause,
    representative rank, page-ID continuity or cross-edition equivalence.
    """
    # The observation end is already validated by the source gate. Keep the
    # labelled week fixed to that source window rather than the viewer clock.
    week_start = (date.fromisoformat(observation_end) - timedelta(days=6)).isoformat()

    def one(positive: bool) -> str:
        evidence = []
        for index, row in enumerate(rows):
            delta = _weekly(row)[2]
            if (delta > 0) if positive else (delta < 0):
                evidence.append((abs(delta), -index, row, delta))
        label = "Largest increase" if positive else "Largest decrease"
        if not evidence:
            return ('<div class="spotlight spotlight-empty"><span class="badge">'
                    + label + '</span><p>No ' + ("positive" if positive else "negative")
                    + ' weekly change among these selected title histories.</p></div>')
        _, _, row, delta = max(evidence, key=lambda entry: (entry[0], entry[1]))
        edition = "EN" if row["project"] == "en.wikipedia" else "RU"
        weeks, baseline, _ = _weekly(row)
        return ('<a class="spotlight" href="#' + _uid(row) + '"><span class="badge">'
                + label + ' · ' + edition + '</span><strong' + (' lang="ru"' if edition == "RU" else '') + '>'
                + escape(row["title"]) + '</strong><span class="spotlight-number">'
                + escape(_signed(delta)) + ' requests vs four-week median</span>'
                + '<span class="spotlight-context">Last complete UTC week '
                + escape(week_start) + '–' + escape(observation_end) + ': '
                + _label(weeks[-1]) + ' requests; preceding four-week median '
                + _label(baseline) + ' requests.</span>'
                + '<span>Inspect 35 exact UTC days ↗</span></a>')
    return one(True), one(False)



def _subject_examples(rows: list[dict], subjects: dict[tuple[str, int], str]) -> str:
    """Source-derived jump links into one measured example per present subject.

    Choose the largest absolute signed seven-day change within the selected
    subject only, breaking ties by original selection order. This is not a
    Wikipedia-wide ranking, a category filter or a lifecycle classifier.
    """
    selected: dict[str, tuple[dict, Fraction]] = {}
    counts: dict[str, int] = {}
    for row in rows:
        subject = subjects[(row["project"], row["page_id"])]
        counts[subject] = counts.get(subject, 0) + 1
        delta = _weekly(row)[2]
        if subject not in selected or abs(delta) > abs(selected[subject][1]):
            selected[subject] = (row, delta)
    links = []
    for subject in sorted(selected):
        row, delta = selected[subject]
        edition = "EN" if row["project"] == "en.wikipedia" else "RU"
        links.append(
            '<a class="subject-example" href="#' + _uid(row) + '">'
            '<span class="badge">' + escape(subject.title()) + ' · '
            + str(counts[subject]) + ' selected</span>'
            '<strong' + (' lang="ru"' if edition == "RU" else '') + '>' + escape(row["title"]) + '</strong>'
            '<span>' + edition + ' · ' + escape(_signed(delta))
            + ' requests vs four-week median</span></a>'
        )
    return "".join(links)


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
    const visibleDailyButton = document.getElementById("compare-daily-csv");
    const visibleDailyStatus = document.getElementById("compare-daily-csv-status");
    const pairForm = document.getElementById("pair-form");
    const pairLeft = document.getElementById("pair-left");
    const pairRight = document.getElementById("pair-right");
    const pairOutput = document.getElementById("pair-output");
    const pairCharts = document.getElementById("pair-daily-charts");
    const pairRows = document.querySelector("#pair-table tbody");
    const pairStatus = document.getElementById("pair-status");
    const pairShare = document.getElementById("pair-share");
    const pairCsvButton = document.getElementById("pair-csv");
    const pairCsvStatus = document.getElementById("pair-csv-status");
    const pairDailyCsvButton = document.getElementById("pair-daily-csv");
    const pairDailyCsvStatus = document.getElementById("pair-daily-csv-status");
    const cardsContainer = document.querySelector(".cards");
    const compareBody = document.querySelector("#compare-table tbody");
    if (!form || !results || !empty || !cards.length || !query || !edition ||
        !subject || !order || !change || !cardsContainer || !compareBody || !link || !warning || !snapshot || !compareResults ||
        !compareEmpty || !csvButton || !csvStatus || !visibleDailyButton || !visibleDailyStatus ||
        !pairForm || !pairLeft || !pairRight ||
        !pairOutput || !pairRows || !pairCharts || !pairStatus || !pairShare || !pairCsvButton || !pairCsvStatus ||
        !pairDailyCsvButton || !pairDailyCsvStatus ||
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
    // Share from the mutable Pages entrypoint points to its already-staged
    // byte-identical immutable archive. Inside archives or offline previews,
    // existing relative query links must remain within their own HTML.
    // An offline downloaded HTML can also be named m1/index.html, without
    // an archives/ sibling. Preserve same-file shares under the file: scheme.
    const mutableM1 = (window.location.protocol === "http:" ||
                       window.location.protocol === "https:") &&
        /\/m1\/(?:index\.html)?$/.test(window.location.pathname);
    const shareBase = mutableM1
        ? new URL("archives/" + snapshot.dataset.dataset + "/index.html", window.location.href)
        : new URL(window.location.href);
    if (mutableM1) {
        for (const anchor of document.querySelectorAll(".share-action a, .detail-share a")) {
            const relative = new URL(anchor.getAttribute("href"), window.location.href);
            relative.pathname = shareBase.pathname;
            anchor.href = relative.toString();
        }
    }
    const keys = ["af_dataset", "af_query", "af_edition", "af_subject"];
    const sortModes = new Set(["editorial", "increase", "decrease",
                               "relative-increase", "relative-decrease"]);
    const changeModes = new Set(["all", "positive", "negative", "unchanged"]);
    const originalPosition = new Map(cards.map((card, index) => [card.dataset.series, index]));
    const rowBySeries = new Map(comparisonRows.map(row => [row.dataset.series, row]));
    // Fold Wikipedia URL underscores and whitespace for search only; never alter source titles or URLs.
    const normalized = value => value.normalize("NFC").toLowerCase()
        .replace(/ё/g, "е").replace(/_/g, " ").replace(/\s+/g, " ").trim();
    const csvSupported = typeof Blob === "function" && typeof URL.createObjectURL === "function";
    const params = new URLSearchParams(window.location.search);
    const requested = Array.from(params.keys()).some(key => key.startsWith("af_"));
    let invalid = false;
    if (requested) {
        const q = params.get("af_query");
        const ed = params.get("af_edition");
        const sub = params.get("af_subject");
        const sort = params.get("af_sort");
        const signed = params.get("af_change");
        const leftId = params.get("af_left");
        const rightId = params.get("af_right");
        const hasPair = leftId !== null || rightId !== null;
        invalid = Array.from(params.keys()).some(key =>
                !keys.includes(key) && !["af_sort", "af_change", "af_left", "af_right"].includes(key)) ||
            keys.some(key => params.getAll(key).length !== 1) ||
            params.getAll("af_sort").length > 1 ||
            params.getAll("af_change").length > 1 ||
            params.getAll("af_left").length > 1 ||
            params.getAll("af_right").length > 1 ||
            (hasPair && (!leftId || !rightId || leftId === rightId ||
                         !bySeries.has(leftId) || !bySeries.has(rightId))) ||
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
            if (hasPair) {
                pairLeft.value = leftId;
                pairRight.value = rightId;
            }
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
        // Explicit current page-ID lookup; never infer ID continuity for title-scoped history.
        const queryIsPageId = text.startsWith("id:");
        const pageIdQuery = queryIsPageId ? text.slice(3) : "";
        const canonicalPageId = /^[1-9][0-9]*$/.test(pageIdQuery);
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
            const found = queryIsPageId ?
                (canonicalPageId && card.dataset.pageId === pageIdQuery) :
                normalized(card.dataset.title || "").includes(text);
            const match = found &&
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
        const url = new URL(shareBase.href);
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
        visibleDailyButton.disabled = shown === 0;
    }
    function drawPairDailyCharts(ids) {
        // Same exact UTC x-axis and shared zero-origin y-axis for both titles.
        // Check all source dates and weekly totals before showing any curve.
        const selected = ids.map(id => {
            const row = rowBySeries.get(id);
            const card = bySeries.get(id);
            const title = row && row.querySelector("th a");
            const weekly = row && Array.from(row.querySelectorAll("td"));
            if (!card || !title || !weekly || weekly.length !== 6)
                throw new Error("incomplete selected pair evidence");
            checkedWeeklyCells(id, weekly, card.dataset.delta2);
            const daily = exactDailyRows(id).map(([day, count]) =>
                ({day, requests: BigInt(count)}));
            return {title: title.textContent, edition: card.dataset.edition, daily};
        });
        const firstDay = selected[0].daily[0].day;
        const lastDay = selected[0].daily[34].day;
        if (selected.some(item => item.daily.length !== 35 ||
            item.daily[0].day !== firstDay || item.daily[34].day !== lastDay))
            throw new Error("incomparable daily windows");
        const maximum = selected.reduce((peak, item) =>
            item.daily.reduce((max, point) =>
                point.requests > max ? point.requests : max, peak), 0n);
        const note = document.createElement("p");
        note.className = "muted";
        note.textContent = "Daily requests, " + firstDay + " to " + lastDay +
            " UTC. Both title plots use the SAME zero-origin scale (0 to " +
            maximum.toString() + " requests). Heights are directly comparable; " +
            "source tables below contain every exact value.";
        const grid = document.createElement("div");
        grid.className = "pair-chart-grid";
        const svgNS = "http://www.w3.org/2000/svg";
        for (const item of selected) {
            const figure = document.createElement("figure");
            figure.className = "pair-daily-chart";
            const caption = document.createElement("figcaption");
            caption.textContent = (item.edition === "ru.wikipedia" ? "RU" : "EN") +
                " · " + item.title;
            if (item.edition === "ru.wikipedia") caption.lang = "ru";
            const svg = document.createElementNS(svgNS, "svg");
            svg.setAttribute("viewBox", "0 0 360 124");
            svg.setAttribute("role", "img");
            svg.setAttribute("aria-label", item.title + ": 35 UTC daily request counts; " +
                "shared zero-to-" + maximum.toString() + " request scale, " +
                firstDay + " to " + lastDay + ". Exact values in the daily table.");
            const zero = document.createElementNS(svgNS, "line");
            for (const [key, value] of Object.entries({
                x1: "12", y1: "108", x2: "348", y2: "108"}))
                zero.setAttribute(key, value);
            zero.setAttribute("class", "pair-zero-axis");
            const line = document.createElementNS(svgNS, "polyline");
            // BigInt ratios avoid truncation/NaN for counts above 2^53;
            // conversion to Number happens only after scaling to 0..96.
            const coordinates = item.daily.map((point, index) => {
                const x = 12 + Math.round(index * 336 / 34);
                const y = 108 - (maximum === 0n ? 0 :
                    Number((point.requests * 96n + maximum / 2n) / maximum));
                return x + "," + y;
            });
            line.setAttribute("points", coordinates.join(" "));
            line.setAttribute("class", "pair-daily-line");
            svg.append(zero, line);
            const legend = document.createElement("p");
            legend.className = "muted";
            legend.textContent = "0–" + maximum.toString() +
                " requests; same scale for both titles. Exact dates and counts below.";
            figure.append(caption, svg, legend);
            grid.appendChild(figure);
        }
        pairCharts.replaceChildren(note, grid);
        pairCharts.hidden = false;
    }

    function renderPair() {
        const leftId = pairLeft.value;
        const rightId = pairRight.value;
        const valid = leftId && rightId && leftId !== rightId &&
            rowBySeries.has(leftId) && rowBySeries.has(rightId);
        pairRows.replaceChildren();
        pairCharts.replaceChildren();
        pairCharts.hidden = true;
        pairOutput.hidden = !valid;
        pairShare.hidden = !valid;
        pairCsvButton.hidden = !valid || !csvSupported;
        pairDailyCsvButton.hidden = !valid || !csvSupported;
        pairCsvStatus.textContent = "";
        pairDailyCsvStatus.textContent = "";
        if (!valid) {
            pairStatus.textContent = (leftId && leftId === rightId) ?
                "Choose two different titles to compare." :
                "Choose two titles to compare five exact, aligned UTC weeks.";
            return;
        }
        // Clone only previously validated, source-derived rows; never calculate
        // a cross-title difference or treat editorial pairs as one entity.
        for (const id of [leftId, rightId]) {
            const row = rowBySeries.get(id).cloneNode(true);
            // The native comparison target must remain unique in the DOM.
            row.removeAttribute("id");
            row.removeAttribute("tabindex");
            row.hidden = false; // Discovery filters must not hide a chosen pair.
            pairRows.appendChild(row);
        }
        const shareUrl = new URL(link.href);
        shareUrl.hash = "pair-compare";
        shareUrl.searchParams.set("af_left", leftId);
        shareUrl.searchParams.set("af_right", rightId);
        pairShare.href = shareUrl.toString();
        try {
            drawPairDailyCharts([leftId, rightId]);
        } catch (error) {
            pairCharts.textContent = "Daily charts unavailable: exact dates or counts did not reconcile. " +
                "Use the full source tables below; no substitute history is shown.";
            pairCharts.hidden = false;
        }
        pairStatus.textContent =
            "Two title-scoped histories for the same five complete UTC weeks. " +
            "This does not establish cross-edition entity equivalence or a cause.";
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
        if (!/^(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)$/.test(raw))
            throw new Error("invalid exact weekly request count");
        return raw.replace(/,/g, "");
    }
    function deltaText(value, expected2) {
        // Fail closed on noncanonical grouping and on changed DOM values.
        // Never export a plausible but wrong delta alongside retained counts.
        const raw = String(value).trim().replace(/^\u2212/, "-");
        if (!/^[+-]?(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)(?:\.5)?$/.test(raw))
            throw new Error("invalid exact baseline delta");
        const canonical = raw.replace(/,/g, "");
        const magnitude = canonical.replace(/^[+-]/, "");
        const doubled = BigInt(magnitude.split(".")[0]) * 2n +
            (magnitude.endsWith(".5") ? 1n : 0n);
        if ((canonical.startsWith("-") ? -doubled : doubled) !== BigInt(expected2))
            throw new Error("mismatched exact baseline delta");
        return canonical;
    }
    function exactDailyRows(id) {
        // The 35 visible exact-source rows are a second, dated observation
        // of the five weekly totals; missing/reordered dates fail closed.
        const article = document.getElementById(id);
        const sourceRows = article && Array.from(article.querySelectorAll(".scroll table tbody tr"));
        if (!sourceRows || sourceRows.length !== 35)
            throw new Error("incomplete exact daily history");
        const end = snapshot.dataset.end;
        if (!/^\d{4}-\d{2}-\d{2}$/.test(end))
            throw new Error("invalid observation end");
        const lastDay = Date.parse(end + "T00:00:00Z");
        if (!Number.isFinite(lastDay) ||
            new Date(lastDay).toISOString().slice(0, 10) !== end)
            throw new Error("invalid UTC end date");
        return sourceRows.map((sourceRow, day) => {
            const cells = sourceRow.children;
            if (cells.length !== 2 || cells[0].tagName !== "TH" ||
                cells[1].tagName !== "TD")
                throw new Error("invalid exact daily row");
            const expectedDay = new Date(lastDay - (34 - day) * 86400000)
                .toISOString().slice(0, 10);
            if (cells[0].textContent.trim() !== expectedDay)
                throw new Error("missing, duplicate or misaligned UTC date");
            return [expectedDay, countText(cells[1].textContent)];
        });
    }
    function checkedWeeklyCells(id, cells, expected2) {
        const daily = exactDailyRows(id);
        const totals = [0n, 0n, 0n, 0n, 0n];
        daily.forEach(([day, count], index) => {
            totals[Math.floor(index / 7)] += BigInt(count);
        });
        const shown = cells.slice(0, 5).map(cell => countText(cell.textContent));
        if (cells.length !== 6 || shown.length !== 5 ||
            shown.some((count, index) => BigInt(count) !== totals[index]))
            throw new Error("weekly/daily evidence mismatch");
        const baseline = totals.slice(0, 4).sort((a, b) => a < b ? -1 : a > b ? 1 : 0);
        if (2n * totals[4] - baseline[1] - baseline[2] !== BigInt(expected2))
            throw new Error("weekly delta does not match daily evidence");
        return [...shown, deltaText(cells[5].textContent, expected2)];
    }
    function downloadCsv(selected, filenamePrefix) {
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
                card.dataset.subject,
                ...checkedWeeklyCells(row.dataset.series, cells, card.dataset.delta2)
            ];
            if (columns.length !== headings.length)
                throw new Error("incompatible comparison schema");
            // Metadata/title are untrusted text; week counts and signed delta
            // were strictly parsed as numeric strings and must stay numeric.
            lines.push(columns.map((value, index) => csvCell(value, index < 7)).join(","));
        }
        saveCsv(lines, filenamePrefix);
        return selected.length;
    }
    function saveCsv(lines, filenamePrefix) {
        const bytes = "\ufeff" + lines.join("\r\n") + "\r\n";
        const blobUrl = URL.createObjectURL(new Blob([bytes], {type: "text/csv;charset=utf-8"}));
        const anchor = document.createElement("a");
        anchor.href = blobUrl;
        anchor.download = filenamePrefix + snapshot.dataset.dataset.slice(0, 12) + ".csv";
        anchor.hidden = true;
        document.body.appendChild(anchor);
        try {
            anchor.click();
        } finally {
            anchor.remove();
            setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
        }
    }
    function downloadDailyCsv(ids, filenamePrefix) {
        // A bounded filtered set of retained exact daily histories;
        // never substitute missing dates with zero or infer equivalence.
        if (ids.length < 1 || ids.length > cards.length ||
            new Set(ids).size !== ids.length ||
            ids.some(id => !rowBySeries.has(id)))
            throw new Error("invalid selected title history");
        const end = snapshot.dataset.end;
        const headers = ["dataset_sha256", "method_version", "observation_end_utc",
                         "snapshot_series_key", "edition", "title", "subject",
                         "utc_date", "daily_requests"];
        const lines = [headers.map(cell => csvCell(cell, false)).join(",")];
        for (const id of ids) {
            const card = bySeries.get(id);
            const row = rowBySeries.get(id);
            const title = row && row.querySelector("th a");
            if (!card || !title)
                throw new Error("incomplete exact daily history");
            for (const [expectedDay, count] of exactDailyRows(id)) {
                const columns = [snapshot.dataset.dataset, snapshot.dataset.method,
                                 end, id, card.dataset.edition, title.textContent,
                                 card.dataset.subject, expectedDay, count];
                lines.push(columns.map((value, index) => csvCell(value, index < 8)).join(","));
            }
        }
        if (lines.length !== 1 + ids.length * 35)
            throw new Error("incomplete daily export");
        saveCsv(lines, filenamePrefix);
    }
    function changed() {
        csvStatus.textContent = "";
        visibleDailyStatus.textContent = "";
        warning.hidden = true;
        update();
        renderPair();
    }
    if (csvSupported) {
        csvButton.hidden = false;
        visibleDailyButton.hidden = false;
        csvButton.addEventListener("click", () => {
            try {
                const selected = Array.from(compareBody.querySelectorAll("tr"))
                    .filter(row => !row.hidden);
                const count = downloadCsv(selected, "dayflare-weekly-");
                if (count)
                    csvStatus.textContent = "CSV prepared for " + count +
                        " selected title histories. Your browser handles saving the file.";
            } catch (error) {
                csvStatus.textContent =
                    "CSV unavailable: an exact comparison value was invalid. Use the table below.";
            }
        });
        visibleDailyButton.addEventListener("click", () => {
            try {
                const visibleCards = Array.from(cardsContainer.querySelectorAll(".card"))
                    .filter(card => !card.hidden);
                const ids = Array.from(compareBody.querySelectorAll("tr"))
                    .filter(row => !row.hidden).map(row => row.dataset.series);
                // The table and cards must represent the same filtered, sorted
                // identities. Matching counts alone would leak the wrong title.
                if (!ids.length || ids.length !== visibleCards.length ||
                    ids.some((id, index) => id !== visibleCards[index].dataset.series))
                    throw new Error("visible series mismatch");
                downloadDailyCsv(ids, "dayflare-visible-daily-");
                visibleDailyStatus.textContent = "Daily CSV prepared for " + ids.length +
                    " visible title histories, each with 35 exact UTC dates. " +
                    "Your browser handles saving the file.";
            } catch (error) {
                visibleDailyStatus.textContent =
                    "Daily CSV unavailable: incomplete, misaligned or invalid exact daily evidence. " +
                    "Use the individual source tables below.";
            }
        });
        pairCsvButton.addEventListener("click", () => {
            if (pairOutput.hidden || pairLeft.value === pairRight.value ||
                !rowBySeries.has(pairLeft.value) || !rowBySeries.has(pairRight.value)) return;
            try {
                // Export only the exact selected pair, independently of discovery filters.
                // Fail closed if the DOM no longer matches the selected series.
                const rows = Array.from(pairRows.querySelectorAll("tr"));
                if (rows.length !== 2 || rows[0].dataset.series !== pairLeft.value ||
                    rows[1].dataset.series !== pairRight.value)
                    throw new Error("pair rows mismatch");
                downloadCsv(rows, "dayflare-pair-");
                pairCsvStatus.textContent = "Pair CSV prepared for the 2 selected " +
                    "title histories. Your browser handles saving the file.";
            } catch (error) {
                pairCsvStatus.textContent =
                    "Pair CSV unavailable: an exact comparison value was invalid. Use the table above.";
            }
        });
        pairDailyCsvButton.addEventListener("click", () => {
            if (pairOutput.hidden) return;
            try {
                downloadDailyCsv([pairLeft.value, pairRight.value], "dayflare-pair-daily-");
                pairDailyCsvStatus.textContent = "Daily CSV prepared: 35 aligned UTC dates " +
                    "for each of the two selected title histories.";
            } catch (error) {
                pairDailyCsvStatus.textContent =
                    "Daily CSV unavailable: incomplete, misaligned or invalid exact daily evidence. " +
                    "Use the source tables below.";
            }
        });
    }
    // Export a single title without requiring an unrelated second title.
    // With JavaScript off the exact daily table remains readable.
    if (csvSupported) {
        for (const button of document.querySelectorAll(".detail-daily-csv")) {
            const article = button.closest("article");
            const status = button.parentElement.querySelector(".detail-daily-csv-status");
            if (!article || !status) continue;
            button.hidden = false;
            button.addEventListener("click", () => {
                try {
                    const id = button.dataset.series;
                    if (!id || article.id !== id || !rowBySeries.has(id))
                        throw new Error("invalid exact title identity");
                    downloadDailyCsv([id], "dayflare-title-daily-");
                    status.textContent = "Daily CSV prepared: 35 exact UTC dates for this title. " +
                        "Your browser handles saving the file.";
                } catch (error) {
                    status.textContent = "Daily CSV unavailable: invalid title, date or exact " +
                        "daily evidence. Use the table below.";
                }
            });
        }
    }
    // A discovery card is an accessible shortcut to the existing exact pair
    // comparator. It never guesses a related page or cross-edition identity.
    for (const action of document.querySelectorAll(".card-pair, .detail-pair")) {
        action.addEventListener("click", event => {
            const card = action.closest(".card");
            const detail = action.closest('article[id^="detail-"]');
            const id = card ? card.dataset.series : (detail && detail.id);
            if (!bySeries.has(id)) return;
            // Both native anchors must target their own exact evidence row.
            if (action.getAttribute("href") !== "#compare-" + id) return;
            // Native fragment navigation happens after click listeners and can
            // steal keyboard focus. Keep the URL/history and focus explicit.
            event.preventDefault();
            pairLeft.value = id;
            if (pairRight.value === id) pairRight.value = "";
            renderPair();
            if (location.hash !== "#pair-compare")
                history.pushState(null, "", "#pair-compare");
            pairRight.focus();
        });
    }
    pairLeft.addEventListener("change", renderPair);
    pairRight.addEventListener("change", renderPair);
    pairForm.addEventListener("reset", () => setTimeout(renderPair, 0));
    pairForm.hidden = false;
    // Reuse the same exact five-week column dates and median-delta heading.
    document.querySelector("#pair-table thead").appendChild(
        document.querySelector("#compare-table thead tr").cloneNode(true));
    form.addEventListener("input", changed);
    form.addEventListener("change", changed);
    form.addEventListener("submit", event => event.preventDefault());
    form.addEventListener("reset", () => setTimeout(changed, 0));
    form.hidden = false;
    link.hidden = false;
    update();
    renderPair();
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
        '.save-snapshot{display:inline-flex;align-items:center;min-height:44px;',
        'padding:.55rem .85rem;border:1px solid #84a8c3;border-radius:.6rem;',
        'color:#e3f4ff;font-weight:750;text-decoration:none;max-width:100%}',
        '.save-snapshot:focus-visible{outline:3px solid #ffca7f;outline-offset:4px}',
        '.save-note{max-width:66ch;color:#cadceb;font-size:.9rem;margin:.2rem 0}',
        '.warning{padding:.8rem 1rem;border:1px solid #ffe6ac;border-left:5px solid #ffbe63;',
        'background:#352b26;color:#fff3dc;border-radius:.45rem;margin:1.5rem 0}',
        '.metadata{display:flex;gap:.8rem 2rem;flex-wrap:wrap;color:#e6edf7;font-size:.95rem}',
        '.archive-age{margin:1.1rem 0 0;padding:.65rem .9rem;background:#152a42;',
        'border:1px solid #58748a;border-left:4px solid #8be6e2;border-radius:.45rem;color:#f4f8fc}',
        'main{padding:2rem 0 5rem}h2{font-size:clamp(1.5rem,3vw,2rem);margin:2.1rem 0 1rem}',
        '.muted{color:#c7d5e4}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));',
        'gap:1rem;margin:1.4rem 0 2rem}.card,article{background:#12253b;border:1px solid #3b5970;',
        'border-radius:1rem;padding:1.2rem}.card h3{font-size:1.2rem;line-height:1.35;margin:.3rem 0}',

        '.spotlights{margin:0 0 2rem}.spotlight-grid{display:grid;',
        'grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));gap:1rem}',
        '.spotlight{display:flex;flex-direction:column;gap:.4rem;padding:1.1rem;',
        'background:#102d40;color:#f6f7fa;border:2px solid #5d879c;border-radius:.85rem;',
        'text-decoration:none;min-height:140px}',
        '.spotlight strong{font-size:1.22rem;overflow-wrap:anywhere}',
        '.spotlight-number{font-variant-numeric:tabular-nums;font-weight:750;color:#f9e1a2}',
        '.spotlight-context{font-size:.92rem;color:#dce9f4;font-variant-numeric:tabular-nums}',
        '.spotlight:focus-visible{outline:3px solid #ffca7f;outline-offset:4px}',
        '.spotlight-empty{background:#202c3b;color:#e6edf7}',
        '.subject-examples{display:flex;gap:.65rem;flex-wrap:wrap;margin:1rem 0 1.5rem}',
        '.subject-example{display:flex;flex:1 1 170px;flex-direction:column;gap:.25rem;',
        'min-width:min(100%,190px);padding:.8rem;border:1px solid #5d879c;',
        'border-radius:.7rem;background:#122a42;color:#f6f7fa;text-decoration:none}',
        '.subject-example strong{overflow-wrap:anywhere}',
        '.subject-example:focus-visible{outline:3px solid #ffca7f;outline-offset:4px}',
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
        '.daily-curve{margin:1rem 0;padding:.7rem 1rem;background:#102c43;',
        'border:1px solid #41637a;border-radius:.7rem}',
        '.daily-curve svg{display:block;width:100%;height:auto;max-height:9rem}',
        '.daily-zero{stroke:#7d9eb3;stroke-width:1.5}',
        '.daily-line{fill:none;stroke:#8be6e2;stroke-width:3;stroke-linejoin:round;stroke-linecap:round}',
        '.daily-curve figcaption{font-size:.9rem;color:#e2edf7;line-height:1.45}',
        '.share-action{margin:.6rem 0 0;font-weight:650}',
        '.current-context a,.page-id-context a{display:inline-block;max-width:100%;min-height:44px;'
        'padding:.55rem .8rem;border:1px solid #7b93ab;border-radius:.5rem;'
        'font-weight:700;text-decoration:none}',
        '.page-id-context{margin:.4rem 0 .9rem}',
        '.detail-share{margin:.75rem 0 1rem}',
        '.detail-share a{display:inline-flex;align-items:center;min-height:44px;padding:.55rem .8rem;',
        'border:1px solid #7b93ab;border-radius:.5rem;font-weight:750;text-decoration:none}',
        '.detail-share a:focus-visible{outline:3px solid #ffca7f;outline-offset:3px}',
        '.card-pair{display:inline-flex;align-items:center;min-height:44px;padding:.55rem .8rem;',
        'max-width:100%;border:1px solid #7b93ab;border-radius:.5rem;font-weight:750;text-decoration:none}',
        '.card-pair:focus-visible{outline:3px solid #ffca7f;outline-offset:3px}',
        '.detail-pair{display:inline-flex;align-items:center;min-height:44px;padding:.55rem .8rem;',
        'max-width:100%;border:1px solid #7b93ab;border-radius:.5rem;font-weight:750;text-decoration:none}',
        '.detail-pair:focus-visible{outline:3px solid #ffca7f;outline-offset:3px}',
        '.share-restore{display:none;padding:1.2rem;margin:1rem 0;border:2px solid #8be6e2;',
        'background:#19354c;border-radius:.75rem}.share-restore:target{display:block}',
        '.scroll{overflow-x:auto;max-width:100%;border:1px solid #3b5970;border-radius:.7rem;',
        'background:#102238;margin:.8rem 0 1.5rem}table{border-collapse:collapse;width:100%;',
        'font-variant-numeric:tabular-nums;font-size:.95rem}th,td{padding:.7rem .8rem;text-align:right;',
        'border-bottom:1px solid #2c455d;white-space:nowrap}th:first-child,td:first-child{text-align:left}',
        'thead{background:#223b53}tbody tr:nth-child(even){background:#1a3047}',
        'tbody tr:hover{background:#25445c}',
        '#compare-table tbody tr:target{outline:3px solid #ffca7f;outline-offset:-3px;',
        'background:#25445c;scroll-margin-top:1rem}',
        'caption{text-align:left;padding:.8rem;white-space:normal;',
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
        '#compare-csv,#compare-daily-csv,#pair-csv,#pair-daily-csv,.detail-daily-csv{font:inherit;font-weight:700;background:#8be6e2;color:#062033;',
        'border:0;border-radius:.55rem;min-height:44px;padding:.6rem 1rem;cursor:pointer}',
        '#compare-csv:focus-visible,#compare-daily-csv:focus-visible,#pair-csv:focus-visible,#pair-daily-csv:focus-visible,.detail-daily-csv:focus-visible{outline:3px solid #ffca7f;outline-offset:3px}',
        '#compare-csv:disabled,#compare-daily-csv:disabled{opacity:.5;cursor:not-allowed}',
        '#compare-csv[hidden],#compare-daily-csv[hidden],#pair-csv[hidden],#pair-daily-csv[hidden],.detail-daily-csv[hidden]{display:none!important}',
        '#pair-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,15rem),1fr));gap:.8rem;margin:1rem 0}',
        '#pair-form[hidden],#pair-output[hidden],#pair-share[hidden]{display:none!important}',
        '#pair-form label{display:grid;gap:.3rem;font-weight:650;min-width:0}',
        '#pair-form select{width:100%;min-width:0;max-width:100%;padding:.75rem;background:#182b44;color:#fff;border:1px solid #7b93ab;border-radius:.5rem}',
        '#pair-form select:focus-visible{outline:3px solid #ffca7f;outline-offset:2px}',
        '#pair-form button{min-height:44px;padding:.65rem 1rem;cursor:pointer;background:#234763;color:#fff;border:1px solid #8aa7c0;border-radius:.5rem;font-weight:650}',
        '#pair-form button:focus-visible{outline:3px solid #ffca7f;outline-offset:2px}',
        '#pair-daily-charts[hidden]{display:none!important}',
        '.pair-chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;margin:1rem 0}',
        '.pair-daily-chart{margin:0;min-width:0;padding:1rem;background:#12253b;border:1px solid #41637a;border-radius:.7rem}',
        '.pair-daily-chart figcaption{font-weight:750;overflow-wrap:anywhere;margin-bottom:.6rem}',
        '.pair-daily-chart svg{display:block;width:100%;height:auto;max-height:10rem}',
        '.pair-zero-axis{stroke:#8eabc0;stroke-width:1.6}',
        '.pair-daily-line{fill:none;stroke:#8be6e2;stroke-width:2.8;stroke-linecap:round;stroke-linejoin:round}',
        '.pair-daily-chart p{font-size:.8rem;margin:.35rem 0 0}',
        '@media(max-width:560px){.pair-chart-grid{grid-template-columns:minmax(0,1fr)}}',
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
        '<p class="save-action"><a class="save-snapshot" href="" download="dayflare-m1-' +
        escape(end, quote=True) + '-' + escape(proof["candidate_sha256"][:12], quote=True) +
        '.html">Save this dated HTML offline ↓</a></p>',
        '<p class="save-note">Keep this self-contained observation even after a hosted refresh. '
        'Works without JavaScript; if your browser does not download it, use Save Page As (HTML only). '
        'An offline copy is not a public immutable Share URL.</p>',
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

        '<section class="spotlights" aria-labelledby="spotlight-heading">',
        '<h2 id="spotlight-heading">Start with a measured change</h2>',
        '<p class="muted">Largest positive and negative absolute weekly changes ',
        'within these selected titles only. The comparison is last complete ',
        'week minus the preceding four-week median; neither a Wikipedia-wide ',
        'ranking nor a validated rising/fading classification.</p>',
        '<div class="spotlight-grid">',
        *_spotlights(rows, end),
        '</div></section>',
        '<section aria-labelledby="subject-examples-heading">',
        '<h2 id="subject-examples-heading">Choose a subject example</h2>',
        '<p class="muted">Each shortcut opens one exact title history from the selected ',
        'subject cohort: the largest absolute weekly change within that subject. ',
        'Ties follow the original selection order. These are examples, not ',
        'subject-wide rankings, filters, or validated trends.</p>',
        '<nav class="subject-examples" aria-label="Measured subject examples">',
        _subject_examples(rows, by_id),
        '</nav></section>',
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
        '<label for="atlas-query">Find a title (е matches ё; _ matches spaces) or current page ID (id:5134)<input id="atlas-query" type="search" ',
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
        entries.append((row, weeks, baseline, delta, subject, edition, ident, share_query))
        base.extend([
            '<div class="card" data-series="' + ident + '" data-title="' + escape(row["title"], quote=True) +
            '" data-page-id="' + str(row["page_id"]) +
            '" data-edition="' + escape(row["project"], quote=True) +
            '" data-subject="' + escape(subject, quote=True) +
            '" data-delta2="' + str((delta * 2).numerator) +
            '" data-baseline2="' + str((baseline * 2).numerator) +
            '"><div class="badge">' + edition + ' · ' + escape(subject) + '</div>',
            '<h3' + (' lang="ru"' if edition == "RU" else '') + '><a href="#' + ident + '">' + title + '</a></h3>',
            '<p class="number">' + _label(weeks[-1]) + ' <small>requests / week</small></p>',
            '<p class="stat">' + escape(_signed(delta)) + ' vs baseline · ' + escape(_lift(delta,baseline)) + '</p>',
            _weekly_bars(weeks, end),
            '<p class="chart-note">Five complete UTC weeks; each label shows the '
            'week start date. Bars start at zero; each title has its own scale. '
            '<a href="#compare">Exact weekly values</a></p>',
            '<p class="muted"><small>Last week is ' + escape((date.fromisoformat(end) - timedelta(days=6)).isoformat()) + ' – ' + escape(end) + ' UTC</small></p>',
            '<p class="card-pair-action"><a href="#compare-' + ident + '" class="card-pair" aria-label="' +
            escape("Compare " + edition + " " + row["title"] + ": exact weekly row or interactive pair", quote=True) +
            '">Compare this title ↗</a></p>',
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
                 '<p><button type="button" id="compare-daily-csv" hidden>Download visible daily CSV</button> ',
                 '<span class="muted">35 exact UTC daily requests per visible title; no guessed zeros.</span></p>',
                 '<p id="compare-daily-csv-status" role="status" aria-live="polite"></p>',
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
    for row, weeks, baseline, delta, subject, edition, ident, share_query in entries:
        base.append('<tr id="compare-'+ident+'" data-series="'+ident+'" tabindex="-1"><th scope="row"><a' + (' lang="ru"' if edition == "RU" else '') + ' href="#'+ ident +'">' + escape(row["title"]) + '</a> ('+edition+')</th>')
        base.extend('<td>'+_label(total)+'</td>' for total in weeks)
        base.append('<td>'+escape(_signed(delta))+'</td></tr>')
    pair_options = ''.join(
        '<option value="' + ident + '"' + (' lang="ru"' if edition == "RU" else '') + '>' + edition + ' · ' + escape(row["title"]) + '</option>'
        for row, weeks, baseline, delta, subject, edition, ident, share_query in entries
    )
    base.extend([
        '</tbody></table></div>',
        '<section id="pair-compare" aria-labelledby="pair-heading">',
        '<h2 id="pair-heading">Compare two selected titles</h2>',
        '<p class="muted">Pick any two editorially selected title histories to see '
        'their exact weekly requests side by side. The source windows and filters '
        'are the same; the titles need not identify equivalent topics. '
        'No cause or lifecycle classification is inferred.</p>',
        '<form id="pair-form" aria-label="Choose two histories to compare" hidden>',
        '<label for="pair-left">First title<select id="pair-left">',
        '<option value="">Choose a title</option>' + pair_options + '</select></label>',
        '<label for="pair-right">Second title<select id="pair-right">',
        '<option value="">Choose a different title</option>' + pair_options + '</select></label>',
        '<button type="reset">Clear pair</button></form>',
        '<p id="pair-status" role="status" aria-live="polite">Without JavaScript, '
        'compare every selected title using the full weekly table above.</p>',
        '<p><a id="pair-share" href="#pair-compare" hidden>Share this exact pair ↗</a></p>',
        '<p><button type="button" id="pair-csv" hidden>Download selected pair CSV</button> ',
        '<span class="muted">Exactly two selected titles; same UTC weeks, not an identity match.</span></p>',
        '<p id="pair-csv-status" role="status" aria-live="polite"></p>',
        '<p><button type="button" id="pair-daily-csv" hidden>Download selected pair daily CSV</button> ',
        '<span class="muted">35 exact UTC days per title; one source-derived count per date.</span></p>',
        '<p id="pair-daily-csv-status" role="status" aria-live="polite"></p>',
        '<p class="muted">Weekly table: scroll sideways or focus it and use arrow keys ',
        'to inspect all five UTC weeks and the exact signed difference.</p>',
        '<div class="scroll" id="pair-output" tabindex="0" hidden '
        'aria-label="Two selected title histories, exact weekly comparison">',
        '<table id="pair-table"><caption>Two title-scoped request histories: '
        'five aligned complete UTC weeks, oldest first; exact counts</caption>',
        '<thead></thead><tbody></tbody></table></div>',
        '<div id="pair-daily-charts" aria-label="Aligned daily request charts" hidden></div></section>',
        '<h2 id="evidence">Inspect exact daily history &amp; evidence</h2>'
    ])
    for row, weeks, baseline, delta, subject, edition, ident, share_query in entries:
        base.extend(['<article id="'+ident+'" aria-labelledby="heading-'+ident+'">',
                     '<div class="badge">'+edition+' · '+escape(subject)+'</div>',
                     '<h3 id="heading-'+ident+'"' + (' lang="ru"' if edition == "RU" else '') + '>'+escape(row["title"])+'</h3>',
                     '<p class="muted">Selected Wikipedia page ID '+str(row["page_id"])+
                     '; title-scoped measurements do not verify historical ID continuity.</p>',
                     '<p class="current-context"><a href="' +
                     escape(_article_href(row["project"], row["title"]), quote=True) +
                     '" rel="noopener noreferrer">Open observed title on Wikipedia ↗</a> ' +
                     '<span class="muted">(the address may redirect or no longer exist; ' +
                     'this is not a verified historical page-ID link)</span></p>',
                     '<p class="page-id-context"><a href="' +
                     escape(_page_id_href(row["project"], row["page_id"]), quote=True) +
                     '" rel="noopener noreferrer">Open current page by selected ID ↗</a> ' +
                     '<span class="muted">This ID-based URL follows the present page if available; ' +
                     'it cannot verify the identity behind 35 days of title-scoped requests.</span></p>',
                     '<p class="detail-share"><a href="?' + escape(share_query, quote=True) +
                     '#share-restore">Share this exact history ↗</a> ' +
                     '<span class="muted">Same dataset, method and observation end; ' +
                     'the link will not substitute another title history.</span></p>',
                     '<p class="detail-pair-action"><a href="#compare-'+ident+'" class="detail-pair">Compare this title ↗</a> ' +
                     '<span class="muted">With JavaScript, choose a second selected history; ' +
                     'without it, inspect this exact row in the five-week table.</span></p>',
                     '<div class="metrics"><p><strong>Last week</strong><br>'+_label(weeks[-1])+'</p>',
                     '<p><strong>Four-week median</strong><br>'+_label(baseline)+'</p>',
                     '<p><strong>Absolute Δ</strong><br>'+escape(_signed(delta))+'</p>',
                     '<p><strong>Relative Δ</strong><br>'+escape(_lift(delta,baseline))+'</p></div>',
                     _daily_curve(row["daily"]),
                     '<p class="detail-download"><button type="button" class="detail-daily-csv" data-series="' + ident +
                     '" hidden>Download this title’s 35-day CSV</button> ' +
                     '<span class="detail-daily-csv-status" role="status" aria-live="polite"></span></p>',
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
