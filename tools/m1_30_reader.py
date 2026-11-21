"""Build a standalone *unpublished* EN/RU reader from the retained 30-title JSON.

Runs offline, has no dependencies or external assets, and never overwrites outputs.
Validation is delegated to the independently pinned candidate decoder on CLI.
This is a normalized-data presentation, not a substitute for raw source evidence.
"""
from __future__ import annotations

import argparse
import csv
from io import StringIO
import re
from urllib.parse import quote
from datetime import date, timedelta
from html import escape
import json
from pathlib import Path
from statistics import median


def e(value: object) -> str:
    return escape(str(value), quote=True)


def metrics(row: dict) -> tuple[int, float, float]:
    values = [point['views'] for point in row['daily']]
    reference = median(sum(values[i:i + 7]) for i in (0, 7, 14, 21))
    latest = sum(values[28:35])
    return latest, latest - reference, reference


def largest_daily_rise(daily: list[dict]) -> tuple[int, int | None]:
    """Largest positive request step across 34 consecutive UTC days.

    The first date has no preceding observation; ties prefer the earliest later
    date. A zero result means no observed *positive* step, not missing data.
    """
    if type(daily) is not list or len(daily) != 35 or any(
        type(point) is not dict or type(point.get('views')) is not int
        or not 0 <= point['views'] < 2**53 or type(point.get('date')) is not str
        for point in daily
    ):
        raise ValueError('daily rise needs 35 exact nonnegative dated requests')
    try:
        first = date.fromisoformat(daily[0]['date'])
        for i, point in enumerate(daily):
            observed = date.fromisoformat(point['date'])
            if observed.isoformat() != point['date'] or (observed - first).days != i:
                raise ValueError('missing, repeated or noncanonical UTC day')
    except (ValueError, OverflowError) as exc:
        raise ValueError('daily rise needs 35 consecutive canonical UTC days') from exc
    best, best_index = 0, None
    for i in range(1, 35):
        step = daily[i]['views'] - daily[i - 1]['views']
        if step > best:
            best, best_index = step, i
    return best, best_index


def largest_daily_fall(daily: list[dict]) -> tuple[int, int | None]:
    """Largest strictly positive day-to-day decrease across 34 UTC transitions.

    A missing fall returns (0, None); equal falls choose the earliest later day.
    Reuse the strict 35-day exact-integer/date checks of the rise calculation.
    """
    largest_daily_rise(daily)
    best, best_index = 0, None
    for i in range(1, 35):
        drop = daily[i - 1]['views'] - daily[i]['views']
        if drop > best:
            best, best_index = drop, i
    return best, best_index



def weekly_spotlights(rows: list[dict]) -> str:
    """Select actual largest signed weekly deviations in the curated cohort.

    Zero is neither a positive nor negative deviation; ties prefer lower stable
    (project, page_id). The result is not a Wikipedia-wide popularity ranking.
    """
    output = []
    for direction, label, positive in (
        ('positive', 'Largest positive weekly difference', True),
        ('negative', 'Largest negative weekly difference', False),
    ):
        matching = [row for row in rows
                    if (metrics(row)[1] > 0 if positive else metrics(row)[1] < 0)]
        matching.sort(key=lambda row: (
            -metrics(row)[1] if positive else metrics(row)[1],
            row['project'], row['page_id']))
        if not matching:
            output.append(
                f'<p class="spotlight spotlight--empty" data-direction="{direction}">'
                f'{label}: none measured among these 30 selected histories.</p>')
            continue
        row = matching[0]
        latest, delta, baseline = metrics(row)
        edition = row['project'].split('.')[0].upper()
        anchor = f"page-{edition.lower()}-{row['page_id']}"
        change = f'{delta:+,.1f}' if delta % 1 else f'{delta:+,.0f}'
        reference = f'{baseline:,.1f}' if baseline % 1 else f'{baseline:,.0f}'
        first, last = row['daily'][28]['date'], row['daily'][34]['date']
        output.append(
            f'<a class="spotlight" data-direction="{direction}" href="#{anchor}">'
            f'<span class="spotlight-kicker">{label} · selected 30 only</span>'
            f'<span class="spotlight-title">{e(row["title"])} · {edition}</span>'
            f'<strong class="spotlight-value">{e(change)} requests</strong>'
            f'<span class="spotlight-evidence">{latest:,} requests during {e(first)}–{e(last)} UTC; '
            f'prior four-week median {reference}. Inspect history and source ↓</span></a>')
    return ''.join(output)

def sparkline(row: dict) -> str:
    values = [point['views'] for point in row['daily']]
    maximum = max(values) or 1
    xy = ' '.join(f'{8 + i * 6},{51 - round(value * 43 / maximum)}'
                  for i, value in enumerate(values))
    return (f'<svg viewBox="0 0 221 60" aria-hidden="true" focusable="false" '
            f'preserveAspectRatio="none"><polyline points="{xy}" fill="none" '
            f'stroke="currentColor" stroke-width="2.6" vector-effect="non-scaling-stroke"/>'
            f'</svg>')


def single_history_csv(row: dict, dataset: str, method: str) -> str:
    """Static download, even with JS disabled; identical columns to visible CSV."""
    project, page_id = row['project'], row['page_id']
    if project not in ('en.wikipedia', 'ru.wikipedia') or type(page_id) is not int or page_id <= 0:
        raise ValueError('invalid per-article CSV identity')
    if not all(isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_.-]+', value)
               for value in (dataset, method)):
        raise ValueError('unsafe per-article CSV version')
    key = f'{project}:{page_id}'
    buffer = StringIO(newline='')
    writer = csv.writer(buffer, lineterminator=chr(13) + chr(10))
    writer.writerow(('utc_date', 'project_page_id', 'requests', 'dataset_id', 'method_version'))
    for point in row['daily']:
        value = point['views']
        if type(value) is not int or value < 0 or value > 2**53 - 1:
            raise ValueError('invalid exact per-article CSV request count')
        writer.writerow((point['date'], key, value, dataset, method))
    return 'data:text/csv;charset=utf-8,' + quote(buffer.getvalue(), safe='')



def cohort_weekly_csv(rows: list[dict], dataset: str, method: str) -> str:
    """Download all selected articles' exact W1–W5 request totals without JS.

    Order matches the initial cards. Median/difference are computed in integer
    half-units: values ending in .5 are exact, never rounded through floats.
    A source title that could execute as a spreadsheet formula gets an
    apostrophe prefix in this export only; page identity remains unchanged.
    """
    if type(rows) is not list or len(rows) != 30:
        raise ValueError('weekly cohort needs exactly 30 histories')
    if not all(type(v) is str and re.fullmatch(r'[a-zA-Z0-9_.-]+', v)
               for v in (dataset, method)):
        raise ValueError('unsafe weekly cohort version')

    def half_text(twice: int) -> str:
        magnitude = abs(twice)
        return ('-' if twice < 0 else '') + str(magnitude // 2) + ('.5' if magnitude % 2 else '')

    expected_dates = None
    seen = set()
    prepared = []
    for row in rows:
        if (type(row) is not dict or row.get('project') not in ('en.wikipedia', 'ru.wikipedia')
                or type(row.get('page_id')) is not int or row['page_id'] <= 0
                or type(row.get('title')) is not str or not row['title']
                or type(row.get('source')) is not dict):
            raise ValueError('invalid weekly cohort identity')
        key = f"{row['project']}:{row['page_id']}"
        if key in seen:
            raise ValueError('duplicate weekly cohort identity')
        seen.add(key)
        source = row['source']
        if (type(source.get('endpoint')) is not str
                or not source['endpoint'].startswith('https://wikimedia.org/')
                or type(source.get('body_sha256')) is not str
                or re.fullmatch(r'[0-9a-f]{64}', source['body_sha256']) is None):
            raise ValueError('invalid weekly cohort source reference')
        daily = row.get('daily')
        largest_daily_rise(daily)  # 35 canonical consecutive UTC days; exact safe integers.
        dates = tuple(point['date'] for point in daily)
        if expected_dates is None:
            expected_dates = dates
        elif dates != expected_dates:
            raise ValueError('incomparable weekly cohort observation windows')
        weeks = [sum(daily[i + offset]['views'] for offset in range(7))
                 for i in (0, 7, 14, 21, 28)]
        if any(total > 2**53 - 1 for total in weeks):
            raise ValueError('inexact weekly cohort total')
        middle = sorted(weeks[:4])
        baseline_twice = middle[1] + middle[2]
        change_twice = weeks[4] * 2 - baseline_twice
        title = row['title']
        if re.match(r'^[\x00-\x20\ufeff]*[=+\-@]', title) or title[0] in '\t\r\n':
            title = "'" + title
        prepared.append((
            (-abs(change_twice), row['project'], row['page_id']),
            (key, title, dates[0], dates[-1], *weeks,
             half_text(baseline_twice), half_text(change_twice),
             dataset, method, source['endpoint'], source['body_sha256']),
        ))

    output = StringIO(newline='')
    writer = csv.writer(output, lineterminator=chr(13) + chr(10))
    writer.writerow((
        'project_page_id', 'article_title', 'observed_start_utc', 'observed_end_utc',
        'week_1_requests', 'week_2_requests', 'week_3_requests',
        'week_4_requests', 'week_5_requests', 'prior_four_week_median_requests',
        'final_week_minus_median_requests', 'dataset_id', 'method_version',
        'recorded_api_endpoint', 'reported_response_sha256',
    ))
    for _, values in sorted(prepared, key=lambda item: item[0]):
        writer.writerow(values)
    return 'data:text/csv;charset=utf-8,' + quote(output.getvalue(), safe='')


def cohort_daily_csv(rows: list[dict], dataset: str, method: str) -> str:
    """One self-contained, no-JS download of all exact selected UTC observations.

    Reuse the cohort's stricter identity, complete-window, provenance and
    safe-integer gate; do not silently turn invalid/missing days into zeros.
    Order follows the initial visible cards, not an all-Wikipedia ranking.
    """
    cohort_weekly_csv(rows, dataset, method)
    ranked = sorted(rows, key=lambda row: (
        -abs(metrics(row)[1]), row['project'], row['page_id']))
    output = StringIO(newline='')
    writer = csv.writer(output, lineterminator=chr(13) + chr(10))
    writer.writerow((
        'utc_date', 'project_page_id', 'requests', 'dataset_id',
        'method_version', 'recorded_api_endpoint', 'reported_response_sha256',
    ))
    for row in ranked:
        identity = f"{row['project']}:{row['page_id']}"
        source = row['source']
        for point in row['daily']:
            writer.writerow((
                point['date'], identity, point['views'], dataset, method,
                source['endpoint'], source['body_sha256'],
            ))
    return 'data:text/csv;charset=utf-8,' + quote(output.getvalue(), safe='')


def render(candidate: dict) -> bytes:
    """Render already-validated candidate; all 35 values remain visible without JS."""
    rows = candidate['series']
    if len(rows) != 30 or any(len(r['daily']) != 35 for r in rows):
        raise ValueError('expected exactly 30 complete histories')
    ids = [f"{r['project']}:{r['page_id']}" for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate identity')
    end = date.fromisoformat(candidate['observation_end'])
    start = rows[0]['daily'][0]['date']
    expected_dates = [(date.fromisoformat(start) + timedelta(days=i)).isoformat()
                      for i in range(35)]
    if expected_dates[-1] != str(end):
        raise ValueError('incomparable observation window')
    for r in rows:
        if [point['date'] for point in r['daily']] != expected_dates:
            raise ValueError('incomparable observation window')
    dataset = candidate['dataset_id']
    method = candidate['method_version']
    spotlight_markup = weekly_spotlights(rows)
    cohort_csv = cohort_weekly_csv(rows, dataset, method)
    daily_cohort_csv = cohort_daily_csv(rows, dataset, method)
    sorted_rows = sorted(rows, key=lambda r: (-abs(metrics(r)[1]), r['project'], r['page_id']))
    articles = []
    options = ['<option value="">Choose an article</option>']
    compare_data = {}
    for r in sorted_rows:
        ident = f"{r['project']}:{r['page_id']}"
        edition = r['project'].split('.')[0].upper()
        title = r['title']
        weekly, delta, baseline = metrics(r)
        difference = ('+' if delta > 0 else '') + f'{delta:,.{1 if delta % 1 else 0}f}'
        ratio = f'{delta / baseline * 100:+.1f}%' if baseline > 0 else 'unavailable (zero baseline)'
        anchor = f"page-{edition.lower()}-{r['page_id']}"
        wiki = f"https://{r['project']}.org/?curid={r['page_id']}"
        endpoint = r['source']['endpoint']
        if not endpoint.startswith('https://wikimedia.org/'):
            raise ValueError('unexpected provider URL')
        rise, rise_index = largest_daily_rise(r['daily'])
        if rise_index is None:
            rise_text = ('No positive one-day rise across 34 consecutive UTC-day comparisons; '
                         'the first date has no predecessor.')
        else:
            prior, current = r['daily'][rise_index - 1], r['daily'][rise_index]
            rise_text = (f'Largest one-day rise: +{rise:,} requests on '
                         f'<time datetime="{e(current["date"])}">{e(current["date"])}</time> UTC '
                         f'({prior["views"]:,} → {current["views"]:,} from the preceding day). '
                         f'<a class="rise-jump" href="#day-{anchor}-{e(current["date"])}">'
                         'Inspect exact day ↓</a>')
        fall, fall_index = largest_daily_fall(r['daily'])
        if fall_index is None:
            fall_text = ('No one-day request fall across 34 consecutive UTC-day comparisons; '
                         'the first date has no predecessor.')
        else:
            prior, current = r['daily'][fall_index - 1], r['daily'][fall_index]
            fall_text = (f'Largest one-day fall: −{fall:,} requests on '
                         f'<time datetime="{e(current["date"])}">{e(current["date"])}</time> UTC '
                         f'({prior["views"]:,} → {current["views"]:,} from the preceding day). '
                         f'<a class="fall-jump" href="#day-{anchor}-{e(current["date"])}">'
                         'Inspect exact falling day ↓</a>')
        daily_rows = ''.join(
            f'<tr id="day-{anchor}-{e(p["date"])}"><th scope="row">{e(p["date"])}</th>'
            f'<td>{p["views"]:,}</td></tr>'
            for p in r['daily'])
        comparison_weeks = [sum(r['daily'][i + j]['views'] for j in range(7))
                            for i in (0, 7, 14, 21, 28)]
        article_csv = single_history_csv(r, dataset, method)
        week_rows = ''.join(
            f'<tr><th scope="row">W{i + 1}<span class="week-date">'
            f'{expected_dates[7 * i]}–{expected_dates[7 * i + 6]} UTC'
            f'</span></th><td>{v:,}</td></tr>'
                            for i, v in enumerate(comparison_weeks))
        articles.append(f'''<article id="{anchor}" class="tile" data-delta="{delta}" data-volume="{weekly}" data-daily-rise="{rise}" data-daily-fall="{fall}" data-page-id="{e(ident)}" data-text="{e(edition + ' ' + title)}" data-edition="{edition}">
          <div class="topline"><span class="edition">{edition}</span><span class="code">page #{r['page_id']}</span></div>
          <h3>{e(title)}</h3><div class="metrics"><div><span>Last 7 days</span><strong>{weekly:,}</strong></div>
          <div><span>vs prior 4-week median</span><strong class="{'rise' if delta >= 0 else 'fall'}">{e(difference)}</strong></div></div>
          <div class="curve">{sparkline(r)}</div><p class="minor">Relative change: {e(ratio)} · 35 observed days</p>
          <p class="daily-rise">{rise_text}</p><p class="daily-fall">{fall_text}</p>
           <p class="card-actions"><a class="compare-jump" href="#compare" data-compare-id="{e(ident)}" aria-label="Compare {e(title)} ({edition}) with another selected article">Compare this article</a></p>
          <details><summary>History, values &amp; evidence</summary>
          <div class="detail"><p>The baseline is the median of four non-overlapping seven-day totals immediately before the last seven days. It is not a lifecycle classification.</p>
          <div class="tables"><table><caption>Five seven-day totals</caption><thead><tr><th scope="col">Period</th><th scope="col">Requests</th></tr></thead><tbody>{week_rows}</tbody></table>
          <table><caption>Daily requests, {e(start)}–{e(end)}</caption><thead><tr><th scope="col">UTC date</th><th scope="col">Requests</th></tr></thead><tbody>{daily_rows}</tbody></table></div>
          <p class="minor">Raw response SHA-256 (reported): <code>{e(r['source']['body_sha256'])}</code></p>
          <p class="links"><a href="{e(wiki)}" target="_blank" rel="noopener noreferrer">Wikipedia page</a><a href="{e(endpoint)}" target="_blank" rel="noopener noreferrer">Wikimedia API request</a><a href="#{anchor}">Link to this article</a></p>
          <p class="card-export"><a class="article-csv" download="dayflare-{edition.lower()}-{r['page_id']}-35day.csv" href="{e(article_csv)}">Download this article's exact 35-day CSV</a></p>
          </div></details></article>''')
        options.append(f'<option value="{e(ident)}">{e(edition + " · " + title)}</option>')
        compare_data[ident] = {'title': title, 'edition': edition,
                               'values': [p['views'] for p in r['daily']],
                               'source_url': endpoint,
                               'body_sha256': r['source']['body_sha256']}
    payload = json.dumps({'dataset': dataset, 'method': method, 'start': start, 'end': str(end),
                          'retrieved': candidate['retrieved_at'],
                          'dates': expected_dates, 'rows': compare_data}, ensure_ascii=False, separators=(',', ':'))
    payload = payload.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    css = '''
:root{color-scheme:dark;--bg:#09151d;--panel:#142735;--ink:#f1f6f8;--muted:#b5c8d0;--line:#3c5c6b;--accent:#e8d78b;--good:#9fe2ca;--bad:#ffb5ab;font-family:system-ui,-apple-system,Segoe UI,sans-serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);line-height:1.5}a{color:var(--accent)}a:hover{text-decoration-thickness:2px}:focus-visible{outline:3px solid var(--accent);outline-offset:4px}button,input,select,textarea{font:inherit}button,select,input{min-height:44px;border:1px solid var(--line);border-radius:8px;background:#1a3140;color:var(--ink);padding:8px 12px}button{cursor:pointer}button:hover{background:#275065}.wrap{width:min(1160px,calc(100% - 36px));margin:auto}.skip{position:absolute;top:-100px;left:16px;z-index:3}.skip:focus{top:12px;background:var(--bg)}header{padding:45px 0 38px;border-bottom:1px solid var(--line);background:radial-gradient(ellipse at 75% 0%,#274657 0%,transparent 63%)}.eyebrow,.edition{color:var(--accent);font-size:.76rem;letter-spacing:.12em;font-weight:750;text-transform:uppercase}h1{font-size:clamp(2.1rem,5.5vw,4.25rem);line-height:1.05;letter-spacing:-.04em;margin:12px 0 15px;max-width:900px}h2{font-size:clamp(1.35rem,3vw,2rem);line-height:1.16}h3{font-size:1.27rem;margin:10px 0 15px;overflow-wrap:anywhere}.lead{color:#d7e5ec;max-width:760px;font-size:1.09rem}.spotlights{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:23px 0 4px;max-width:900px}.spotlight{min-width:0;display:flex;flex-direction:column;gap:5px;background:#183445;border:1px solid #577787;border-radius:12px;padding:15px 18px;color:var(--ink);text-decoration:none;overflow-wrap:anywhere}.spotlight:hover{border-color:var(--accent);background:#214459}.spotlight-kicker{color:var(--accent);font-size:.8rem;font-weight:700}.spotlight-title{font-weight:700;font-size:1.06rem}.spotlight-value{font-size:1.45rem;line-height:1.2;font-variant-numeric:tabular-nums}.spotlight-evidence{color:#d2e1e9;font-size:.79rem;line-height:1.5}.spotlight--empty{margin:0}.spotlight[data-direction=positive] .spotlight-value{color:var(--good)}.spotlight[data-direction=negative] .spotlight-value{color:var(--bad)}@media(max-width:620px){.spotlights{grid-template-columns:1fr}}.status{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}.status span{padding:6px 11px;border-radius:99px;background:#234253;color:#e9f3f6;border:1px solid var(--line);font-size:.86rem}.warning{background:#352d23;border-left:4px solid var(--accent);padding:14px 18px;margin:24px 0;color:#ffeac7}.controls{display:flex;flex-wrap:wrap;gap:14px;align-items:end;margin:25px 0}.controls label,.form label{display:grid;gap:6px;color:var(--muted);font-size:.91rem}.controls input{width:min(340px,78vw)}.controls select{width:170px}.count{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:17px;margin:24px 0 54px}.tile{min-width:0;scroll-margin-top:18px;background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:20px;box-shadow:0 6px 24px #0002}.tile:target{border-color:var(--accent);outline:2px solid var(--accent)}.topline{display:flex;justify-content:space-between;align-items:center;gap:10px}.code,.minor{color:var(--muted);font-size:.82rem}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:10px}.metrics span{display:block;color:var(--muted);font-size:.77rem}.metrics strong{display:block;font-size:1.45rem;letter-spacing:-.04em}.rise{color:var(--good)}.fall{color:var(--bad)}.curve{color:var(--accent);height:75px;margin-top:10px}.curve svg{width:100%;height:100%}details{margin-top:14px}summary{cursor:pointer;color:var(--accent);font-weight:600;padding:9px 0}summary:focus-visible{outline-offset:3px}.detail{border-top:1px solid var(--line);font-size:.87rem}.tables{display:flex;gap:16px;align-items:start;flex-wrap:wrap}table{border-collapse:collapse;min-width:0;width:100%;font-variant-numeric:tabular-nums}caption{text-align:left;font-weight:bold;padding:12px 0 6px}th,td{text-align:left;padding:5px 7px;border-bottom:1px solid var(--line)}td{text-align:right}.tables table{flex:1 1 180px;max-width:100%}.links{display:flex;gap:13px;flex-wrap:wrap}.detail code{overflow-wrap:anywhere}section#compare{background:#102330;border-block:1px solid var(--line);padding:28px 0}.form{display:flex;flex-wrap:wrap;gap:12px;align-items:end}.form label{min-width:0;flex:1 1 190px}.form select{width:100%;max-width:100%}#comparison{max-width:100%;overflow-x:auto}#comparison table{margin-top:15px;max-width:740px}#comparison th:first-child{width:34%}#comparison .pair-daily{border-top:1px solid var(--line);margin-top:18px;max-width:740px}#comparison .pair-daily th:first-child{width:34%}#comparison .pair-daily table{font-size:.87rem}#comparison .pair-daily th,#comparison .pair-daily td{padding:6px 4px}#download-csv{display:inline-flex;align-items:center;min-height:44px;border:1px solid var(--line);border-radius:8px;padding:8px 12px}#share-field{width:min(100%,640px)}#share-summary{display:block;width:100%;max-width:740px;min-height:190px;margin:10px 0;border:1px solid var(--line);border-radius:8px;background:#1a3140;color:var(--ink);padding:12px;resize:vertical;font:inherit;font-size:.85rem;line-height:1.5}#invalid-link,#no-results{padding:13px 16px;border:1px solid var(--accent);border-radius:8px;margin:12px 0;color:var(--accent)}.compare-jump{display:inline-flex;align-items:center;justify-content:center;min-height:44px;border:1px solid var(--line);border-radius:8px;padding:8px 12px;color:var(--accent);text-decoration:none;font-weight:650}.compare-jump:hover{background:#275065}.article-csv{display:inline-flex;align-items:center;min-height:44px;border:1px solid var(--line);border-radius:8px;padding:8px 12px;text-decoration:none;font-weight:650}.article-csv:hover{background:#275065}.cohort-export{max-width:900px;color:var(--muted);font-size:.84rem;margin:18px 0 0}.cohort-csv{display:inline-flex;align-items:center;min-height:44px;border:1px solid var(--line);border-radius:8px;padding:8px 12px;color:var(--accent);background:#142f40;text-decoration:none;font-weight:700}.cohort-csv:hover{background:#275065}.cohort-daily{display:inline-flex;align-items:center;min-height:44px;border:1px solid var(--line);border-radius:8px;padding:8px 12px;color:var(--accent);background:#142f40;text-decoration:none;font-weight:700;margin-top:8px}.cohort-daily:hover{background:#275065}.daily-rise,.daily-fall{font-size:.88rem;line-height:1.55;color:#dce9f4;overflow-wrap:anywhere}.rise-jump,.fall-jump{display:inline-flex;align-items:center;min-height:44px;font-weight:650}tr:target{background:#315064;outline:2px solid var(--accent);outline-offset:-2px}#download-visible{display:inline-flex;align-items:center;min-height:44px;border:1px solid var(--line);border-radius:8px;padding:8px 12px;text-decoration:none;font-weight:650}[hidden]{display:none!important}footer{color:var(--muted);padding:28px 0 50px;font-size:.9rem}
.week-date{display:block;color:var(--muted);font-size:.75rem;line-height:1.35;overflow-wrap:anywhere}.pair-chart{max-width:740px;margin:18px 0 12px}.pair-chart figcaption{font-size:.88rem;color:var(--muted);font-weight:600}.pair-legend{font-size:.83rem;color:var(--ink);overflow-wrap:anywhere}.pair-weeks{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;border-bottom:1px solid var(--line)}.pair-week{min-width:0}.pair-bars{height:118px;display:flex;justify-content:center;align-items:end;gap:4px}.pair-bar{display:block;width:min(38%,26px);background:#6bc4db;border-radius:4px 4px 0 0}.pair-bar--b{background:var(--accent)}.pair-week-label{display:block;text-align:center;font-size:.78rem;color:var(--muted);padding:4px 0 6px}
@media(min-width:760px){.detail .tables{display:block}.detail table{margin-top:12px}.detail{max-height:580px;overflow:auto}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}'''
    js = '''(()=>{'use strict';const data=JSON.parse(document.getElementById('dataset').textContent),params=new URLSearchParams(location.search),rows=data.rows;
const $=id=>document.getElementById(id),search=$('search'),edition=$('edition'),sort=$('sort'),tiles=Array.from(document.querySelectorAll('.tile')),status=$('result-count'),visibleCsv=$('download-visible');
const cleaned=s=>Array.from(s).map(c=>c.charCodeAt(0)<32||c.charCodeAt(0)===127?' ':c).join('').trim().split(' ').filter(Boolean).join(' ').slice(0,80);
const matchKey=s=>s.normalize('NFC').toLocaleLowerCase().replace(/ё/g,'е');
function updateVisibleCsv(){visibleCsv.hidden=true;visibleCsv.href='';
const chosen=Array.from($('cards').children).filter(tile=>!tile.hidden);
if(!chosen.length)return;
const lines=['utc_date,project_page_id,requests,dataset_id,method_version'];
for(const tile of chosen){const id=tile.dataset.pageId;
if(!Object.prototype.hasOwnProperty.call(rows,id))return;
const values=rows[id].values;if(!Array.isArray(values)||values.length!==data.dates.length)return;
for(let i=0;i<data.dates.length;i++){const value=values[i];if(!Number.isSafeInteger(value)||value<0)return;
lines.push([data.dates[i],id,value,data.dataset,data.method].join(','));}}
const crlf=String.fromCharCode(13,10);
visibleCsv.href='data:text/csv;charset=utf-8,'+encodeURIComponent(lines.join(crlf)+crlf);
visibleCsv.hidden=false;}
function filter(){let term=matchKey(cleaned(search.value)),ed=edition.value,n=0;for(let tile of tiles){let show=(!term||matchKey(tile.dataset.text).includes(term))&&(!ed||ed===tile.dataset.edition);tile.hidden=!show;if(show)n++;}status.textContent=n+' of '+tiles.length+' histories';$('no-results').hidden=n!==0;updateVisibleCsv();}
function sortTiles(){const mode=sort.value,ordered=tiles.slice().sort((a,b)=>{const av=Number(a.dataset.delta),bv=Number(b.dataset.delta);const diff=mode==='daily-rise'?Number(b.dataset.dailyRise)-Number(a.dataset.dailyRise):mode==='daily-fall'?Number(b.dataset.dailyFall)-Number(a.dataset.dailyFall):mode==='volume'?Number(b.dataset.volume)-Number(a.dataset.volume):mode==='increase'?bv-av:mode==='decrease'?av-bv:Math.abs(bv)-Math.abs(av);return diff||tiles.indexOf(a)-tiles.indexOf(b);});$('cards').replaceChildren(...ordered);}
 search.addEventListener('input',()=>{filter();syncShare();});edition.addEventListener('change',()=>{filter();syncShare();});sort.addEventListener('change',()=>{sortTiles();updateVisibleCsv();syncShare();});sortTiles();filter();
const left=$('left'),right=$('right'),message=$('compare-message'),out=$('comparison'),share=$('share-field'),csvLink=$('download-csv'),summary=$('share-summary'),copySummary=$('copy-summary');
const hasHistory=id=>Object.prototype.hasOwnProperty.call(rows,id);
function shareLink(){const p=new URLSearchParams({dataset:data.dataset,method:data.method,left:left.value,right:right.value,q:cleaned(search.value),ed:edition.value,order:sort.value});return location.href.split('?')[0].split('#')[0]+'?'+p.toString()+'#compare';}
function syncShare(){if(share.value)share.value=shareLink();}
function renderCompare(){const a=rows[left.value],b=rows[right.value];out.replaceChildren();share.value='';csvLink.hidden=true;csvLink.href='';summary.hidden=true;summary.value='';copySummary.hidden=true;if(!a||!b){message.textContent='Choose two articles to compare.';return;}if(left.value===right.value){message.textContent='Select two distinct article histories.';return;}
$('invalid-link').hidden=true;
let totals=(v)=>[0,7,14,21,28].map(n=>v.slice(n,n+7).reduce((sum,x)=>sum+x,0));const ta=totals(a.values),tb=totals(b.values);
const peak=Math.max(1,...ta,...tb);if(!Number.isFinite(peak)||ta.some(v=>!Number.isFinite(v)||v<0)||tb.some(v=>!Number.isFinite(v)||v<0)){message.textContent='Comparison unavailable: invalid weekly totals.';return;}
const validCounts=[...a.values,...b.values,...ta,...tb].every(v=>Number.isSafeInteger(v)&&v>=0);
if(!validCounts){message.textContent='Comparison unavailable: invalid exact request counts.';return;}
const evidence=(label,id,entry,totals)=>{const first=totals.slice(0,4).sort((x,y)=>x-y),baseline=first[1]/2+first[2]/2,delta=totals[4]-baseline;
const lines=[label+': '+entry.edition+' Wikipedia · '+entry.title+' ('+id+')'];
for(let i=0;i<5;i++)lines.push('W'+(i+1)+' '+data.dates[7*i]+'–'+data.dates[7*i+6]+' UTC: '+totals[i].toLocaleString('en-US')+' requests');
lines.push('Median W1–W4: '+baseline.toLocaleString('en-US')+'; W5 minus median: '+(delta>0?'+':'')+delta.toLocaleString('en-US')+' requests');
lines.push('Recorded Wikimedia API URL: '+entry.source_url);
lines.push('Recorded raw response SHA-256: '+entry.body_sha256);
return lines.join(String.fromCharCode(10));};
summary.value=['DAYFLARE · UNPUBLISHED HISTORICAL COMPARISON','35 observed UTC days: '+data.start+'–'+data.end,'Retrieved: '+data.retrieved,'Dataset: '+data.dataset+' | method: '+data.method,evidence('A',left.value,a,ta),evidence('B',right.value,b,tb),'Selected, title-scoped EN/RU page requests (all-access, agent=user); not unique people, all Wikipedia, importance, causation, population comparisons or a verified live update. Recorded source hashes are not provider-origin proof.'].join(String.fromCharCode(10,10));
summary.hidden=false;copySummary.hidden=false;
const t=document.createElement('table');let cap=document.createElement('caption');cap.textContent='Exact seven-day request totals · same dates and filter';t.append(cap);let h=document.createElement('thead'),tr=document.createElement('tr');['UTC week',a.edition+' · '+a.title,b.edition+' · '+b.title].forEach(s=>{let th=document.createElement('th');th.scope='col';th.textContent=s;tr.append(th)});h.append(tr);t.append(h);let body=document.createElement('tbody');
for(let i=0;i<5;i++){let row=document.createElement('tr');const period=document.createElement('th');period.scope='row';period.textContent='W'+(i+1);const dates=document.createElement('span');dates.className='week-date';dates.textContent=data.dates[i*7]+'–'+data.dates[i*7+6]+' UTC';period.append(dates);row.append(period);for(const v of [ta[i],tb[i]]){const cell=document.createElement('td');cell.textContent=v.toLocaleString();row.append(cell);}body.append(row)}t.append(body);const chart=document.createElement('figure');chart.className='pair-chart';
const caption=document.createElement('figcaption');caption.textContent='One shared zero-based scale · 0 to '+peak.toLocaleString()+' weekly requests. W1–W5 map to inclusive UTC date ranges in the exact table below.';chart.append(caption);
const legend=document.createElement('p');legend.className='pair-legend';legend.textContent='A (cyan): '+a.edition+' · '+a.title+'  |  B (gold): '+b.edition+' · '+b.title;chart.append(legend);
const weekGrid=document.createElement('div');weekGrid.className='pair-weeks';weekGrid.setAttribute('aria-hidden','true');
for(let i=0;i<5;i++){const week=document.createElement('div');week.className='pair-week';const bars=document.createElement('div');bars.className='pair-bars';for(const [side,total] of [['a',ta[i]],['b',tb[i]]]){const bar=document.createElement('span');bar.className='pair-bar pair-bar--'+side;bar.style.height=(112*total/peak)+'px';bars.append(bar);}const label=document.createElement('span');label.className='pair-week-label';label.textContent='W'+(i+1);week.append(bars,label);weekGrid.append(week);}
chart.append(weekGrid);
const daily=document.createElement('details');daily.className='pair-daily';const dailySummary=document.createElement('summary');dailySummary.textContent='Inspect all 35 exact UTC days (A and B)';daily.append(dailySummary);
const dailyTable=document.createElement('table'),dailyCaption=document.createElement('caption');dailyCaption.textContent='Exact daily requests for the same 35-day window';dailyTable.append(dailyCaption);
const dailyHead=document.createElement('thead'),dailyHeadRow=document.createElement('tr');['UTC date','A · '+a.edition,'B · '+b.edition].forEach(label=>{const th=document.createElement('th');th.scope='col';th.textContent=label;dailyHeadRow.append(th);});dailyHead.append(dailyHeadRow);dailyTable.append(dailyHead);
const dailyBody=document.createElement('tbody');for(let i=0;i<data.dates.length;i++){const row=document.createElement('tr'),day=document.createElement('th');day.scope='row';day.textContent=data.dates[i];row.append(day);for(const value of [a.values[i],b.values[i]]){const cell=document.createElement('td');cell.textContent=value.toLocaleString();row.append(cell);}dailyBody.append(row);}dailyTable.append(dailyBody);daily.append(dailyTable);chart.append(daily);
out.append(chart,t);message.textContent='Comparison of editions, not populations or equivalent topics.';
share.value=shareLink();
const lines=['utc_date,left_page_id,left_requests,right_page_id,right_requests,dataset_id,method_version'];
for(let i=0;i<data.dates.length;i++){lines.push([data.dates[i],left.value,a.values[i],right.value,b.values[i],data.dataset,data.method].join(','));}
const crlf=String.fromCharCode(13,10);
csvLink.href='data:text/csv;charset=utf-8,'+encodeURIComponent(lines.join(crlf)+crlf);
csvLink.hidden=false;}
for(const link of document.querySelectorAll('.rise-jump,.fall-jump')){link.addEventListener('click',()=>{const detail=link.closest('.tile').querySelector('details');if(detail)detail.open=true;});}
 for(const link of document.querySelectorAll('.compare-jump')){link.addEventListener('click',event=>{const id=link.dataset.compareId;if(!hasHistory(id))return;event.preventDefault();left.value=id;if(right.value===id)right.value='';$('invalid-link').hidden=true;renderCompare();if(!right.value)message.textContent='Choose a second article to compare with '+rows[id].edition+' · '+rows[id].title+'.';if(location.hash!=='#compare')history.pushState(null,'','#compare');$('compare').scrollIntoView({block:'start',behavior:'auto'});right.focus({preventScroll:true});});}
left.addEventListener('change',renderCompare);right.addEventListener('change',renderCompare);
if(params.size){let valid=(params.size===4||params.size===7)&&['dataset','method','left','right'].every(k=>params.has(k))&&params.get('dataset')===data.dataset&&params.get('method')===data.method&&hasHistory(params.get('left'))&&hasHistory(params.get('right'))&&params.get('left')!==params.get('right')&&(params.size===4||(params.has('q')&&params.has('ed')&&params.has('order')&&params.get('q').length<=80&&params.get('q')===cleaned(params.get('q'))&&['','EN','RU'].includes(params.get('ed'))&&['magnitude','volume','daily-rise','daily-fall','increase','decrease'].includes(params.get('order'))));if(valid){if(params.size===7){search.value=params.get('q');edition.value=params.get('ed');sort.value=params.get('order');sortTiles();filter();}left.value=params.get('left');right.value=params.get('right');renderCompare();}else{$('invalid-link').hidden=false;message.textContent='Incompatible comparison or discovery link; choose two current entries.';}}else renderCompare();
$('copy-summary').addEventListener('click',async()=>{if(summary.hidden||!summary.value){message.textContent='Choose two distinct histories first.';return;}
try{await navigator.clipboard.writeText(summary.value);message.textContent='Evidence summary copied as plain text.';}
catch(_){summary.focus();summary.select();message.textContent='Copy the selected evidence summary manually.';}});
$('copy-link').addEventListener('click',async()=>{if(!share.value){message.textContent='Choose two articles first.';return;}try{await navigator.clipboard.writeText(share.value);message.textContent='Local-file link copied; share the HTML file too.';}catch(_){share.focus();share.select();message.textContent='Copy the selected local-file link manually; recipients also need this HTML file.';}});
})();'''
    opts = ''.join(options)
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>Dayflare · 30 observed EN/RU histories · offline</title><style>{css}</style><noscript><style>.controls,#compare,.card-actions{{display:none!important}}</style></noscript></head>
<body><a class="skip" href="#discover">Skip to discovery</a><header><div class="wrap"><p class="eyebrow">Dayflare / measured attention</p>
<h1>See what changed in Wikipedia reading.</h1><p class="lead">Explore <strong>30 selected articles</strong> in English and Russian Wikipedia. Inspect real daily request counts, find larger changes and compare two histories without an account or network connection.</p>
<div class="status"><span>35 UTC days · {e(start)} to {e(end)}</span><span>15 EN · 15 RU</span><span>Retrieved {e(candidate['retrieved_at'])}</span><span>OFFLINE · UNPUBLISHED</span></div>
<nav id="spotlights" class="spotlights" aria-label="Exact measured highlights among 30 selected histories">{spotlight_markup}</nav><p class="cohort-export"><a class="cohort-csv" download="dayflare-30-weekly-summary.csv" href="{e(cohort_csv)}">Download all 30 exact weekly comparisons (CSV)</a> · Five complete UTC weeks, stable page IDs, source receipts and exact half-unit medians. Works without JavaScript; not a live ranking.</p><p class="cohort-export"><a class="cohort-daily" download="dayflare-30-all-daily.csv" href="{e(daily_cohort_csv)}">Download all 1,050 exact daily requests (CSV)</a> · 30 selected page IDs × 35 UTC days, with recorded source URL and checksum on every row. Works without JavaScript; not a live feed.</p></div></header>
<main><div class="wrap"><aside class="warning" role="note"><strong>Dated, selected sample — not live.</strong> These are page requests, not unique readers or evidence of interest, approval or causes. A higher or lower week is not a validated “rising” or “fading” classification. Topic titles and observed page IDs do not establish historical identity across page moves. Original raw HTTP response bodies are <strong>not included</strong> in the retained normalized dataset. This offline view is not a published or verified Pages release.</aside>
<noscript><p class="warning" role="note"><strong>JavaScript is disabled.</strong> Search, filters and comparison require JavaScript. All 30 selected articles and their exact 35-day histories remain readable or individually downloadable as CSV below; open “History, values &amp; evidence” in any card.</p></noscript>
<section id="discover" aria-labelledby="discover-heading"><h2 id="discover-heading">Discover a measured change</h2><p class="count">Initial order: absolute difference between final week and the preceding four-week median. Daily-rise and daily-fall orders separately use the largest positive increase and largest positive decrease across 34 adjacent UTC-day pairs (first day excluded; ties prefer the earliest day; zero means no matching positive step). These are selected observations, not a Wikipedia-wide ranking or a lifecycle classification.</p><div class="controls">
<label for="search">Search selected articles<input id="search" type="search" placeholder="Article title or edition" autocomplete="off" aria-label="Search selected articles" aria-describedby="search-hint"><small id="search-hint" class="minor">Russian е and ё spellings match for search; original article titles stay unchanged.</small></label>
<label for="edition">Wikipedia edition<select id="edition"><option value="">EN + RU</option><option value="EN">English</option><option value="RU">Russian</option></select></label>
<label for="sort">Order by requests or measured change<select id="sort"><option value="magnitude">Largest absolute weekly difference</option><option value="volume">Most requests in last complete UTC week</option><option value="daily-rise">Largest one-day request rise</option><option value="daily-fall">Largest one-day request fall</option><option value="increase">Largest signed increase first</option><option value="decrease">Largest signed decrease first</option></select></label>
<span id="result-count" class="count" role="status" aria-live="polite">30 histories</span><a id="download-visible" download="dayflare-30-visible.csv" hidden>Download visible 35-day CSV</a></div><p id="no-results" hidden role="status">No selected articles match. Clear the search or edition filter.</p>
<div id="cards" class="grid">{''.join(articles)}</div></section></div><section id="compare" aria-labelledby="compare-heading"><div class="wrap"><h2 id="compare-heading">Compare two observed histories</h2><p>Equivalent UTC days, request filters and method. Edition differences are not population differences or evidence that two titles are the same concept.</p><div class="form"><label for="left">First article<select id="left">{opts}</select></label><label for="right">Second article<select id="right">{opts}</select></label></div>
<p id="invalid-link" role="alert" hidden>Link dataset, method or article IDs are incompatible with this archived copy. Select a new comparison.</p><p id="compare-message" role="status" aria-live="polite">Choose two articles to compare.</p><div id="comparison"></div>
<div class="form"><label for="share-field">Local URL for this comparison and discovery filters<input id="share-field" readonly aria-describedby="share-note"></label><button id="copy-link" type="button">Copy comparison link</button><a id="download-csv" download="dayflare-30-pair.csv" hidden>Download exact 35-day CSV</a></div><div class="evidence-share"><label for="share-summary"><strong>Share the evidence as text (works without sharing the HTML file)</strong></label><textarea id="share-summary" rows="11" readonly hidden aria-describedby="summary-help"></textarea><button id="copy-summary" type="button" hidden>Copy evidence summary</button><p class="minor" id="summary-help">Includes exact five UTC-week totals, signed median differences, source links and dataset identity. Not live and not a verified explanation of the change.</p></div><p id="share-note" class="minor">The URL preserves this comparison, discovery search, edition and ordering. It only works if the recipient also has this exact HTML file at the same path; it is not a public hosted link.</p></div></section></main>
<footer><div class="wrap"><p>Source: Wikimedia per-article pageview observations; all-access / user agent filter (not verified human visitors). Dataset <code>{e(dataset)}</code>, schema <code>{e(candidate['schema_version'])}</code>, method <code>{e(method)}</code>. Each article links to its recorded API request and Wikipedia page. Export generated from repository-retained normalized candidate, without network or publishing.</p></div></footer>
<script type="application/json" id="dataset">{payload}</script><script>{js}</script></body></html>'''
    return document.encode('utf-8')


def main() -> None:
    from tools.m1_30_retained_candidate import read_candidate
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='new HTML file (never overwritten)')
    args = parser.parse_args()
    _, data = read_candidate()
    output = args.output
    if not output.parent.is_dir() or output.parent.is_symlink() or output.exists() or output.is_symlink():
        parser.error('destination must be new in an existing real directory')
    html = render(data)
    with output.open('xb') as target:
        target.write(html)
    print(json.dumps({'status': 'UNPUBLISHED_OFFLINE_READER', 'dataset': data['dataset_id'],
                      'html_bytes': len(html), 'output': str(output)}, sort_keys=True))


if __name__ == '__main__':
    main()
