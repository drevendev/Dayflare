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


def _uid(row: dict) -> str:
    return "detail-" + row["project"].replace(".", "-") + "-" + str(row["page_id"])


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
        '.warning{padding:.8rem 1rem;border:1px solid #ffe6ac;border-left:5px solid #ffbe63;',
        'background:#352b26;color:#fff3dc;border-radius:.45rem;margin:1.5rem 0}',
        '.metadata{display:flex;gap:.8rem 2rem;flex-wrap:wrap;color:#e6edf7;font-size:.95rem}',
        'main{padding:2rem 0 5rem}h2{font-size:clamp(1.5rem,3vw,2rem);margin:2.1rem 0 1rem}',
        '.muted{color:#c7d5e4}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));',
        'gap:1rem;margin:1.4rem 0 2rem}.card,article{background:#12253b;border:1px solid #3b5970;',
        'border-radius:1rem;padding:1.2rem}.card h3{font-size:1.2rem;line-height:1.35;margin:.3rem 0}',
        '.badge{font-size:.8rem;letter-spacing:.05em;text-transform:uppercase;color:#aee7d7}',
        '.number{font-variant-numeric:tabular-nums;font-size:1.65rem;font-weight:800;margin:.3rem 0}',
        '.stat{font-variant-numeric:tabular-nums;color:#f1e5b7}',
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
        '</style></head><body>',
        '<a class="skip" href="#main">Skip to atlas</a>',
        '<header><div class="wrap"><div class="eyebrow">Dayflare / EN + RU Wikipedia</div>',
        '<h1>Where did attention change?</h1>',
        '<p class="lead">Explore selected title histories as measured daily request counts. ',
        'Inspect five full weeks, exact values and original source endpoints—without opaque scores.</p>',
        '<div class="warning" role="note"><strong>' + escape(status) + '</strong>. ',
        'This is an offline preview, <strong>not</strong> a public release, live feed, ',
        'stable historical page-ID series or representative ranking.</div>',
        '<div class="metadata"><span><strong>Observed:</strong> ' + escape(observed) + ' UTC</span>',
        '<span><strong>Retrieved:</strong> ' + escape(candidate["retrieved_at"]) + '</span>',
        '<span><strong>Series:</strong> ' + str(len(rows)) + ' selected titles</span></div></div></header>',
        '<main id="main" class="wrap"><h2 id="overview">Discover a measured change</h2>',
        '<p class="muted">Cards compare the last complete seven days with the median of the ',
        'four preceding complete seven-day totals. A larger share is not proof of a cause. ',
        'Choose a title to inspect its 35 exact daily observations and evidence.</p>',
        '<div class="cards">'
    ]
    entries = []
    for row in rows:
        weeks, baseline, delta = _weekly(row)
        subject = by_id[(row["project"], row["page_id"])]
        title = escape(row["title"])
        edition = "EN" if row["project"] == "en.wikipedia" else "RU"
        ident = _uid(row)
        entries.append((row, weeks, baseline, delta, subject, edition, ident))
        base.extend([
            '<div class="card"><div class="badge">' + edition + ' · ' + escape(subject) + '</div>',
            '<h3><a href="#' + ident + '">' + title + '</a></h3>',
            '<p class="number">' + _label(weeks[-1]) + ' <small>requests / week</small></p>',
            '<p class="stat">' + escape(_signed(delta)) + ' vs baseline · ' + escape(_lift(delta,baseline)) + '</p>',
            '<p class="muted"><small>Last week is ' + escape((date.fromisoformat(end) - timedelta(days=6)).isoformat()) + ' – ' + escape(end) + ' UTC</small></p>',
            '</div>'
        ])
    base.extend(['</div><h2 id="compare">Compare exact weekly counts</h2>',
                 '<p class="muted">All rows use equivalent all-access/user request filters ',
                 'and the same complete UTC dates. These are selected title queries—not ',
                 'matched subjects across editions or population measurements.</p>',
                 '<div class="scroll" tabindex="0" aria-label="Scrollable weekly comparison table">',
                 '<table><caption>Five complete seven-day weeks (oldest first); exact request totals</caption><thead><tr>',
                 '<th scope="col">Title / edition</th>'])
    for n in range(5):
        week_start = first + timedelta(days=7*n)
        week_end = week_start + timedelta(days=6)
        base.append('<th scope="col">' + week_start.strftime('%b %d') + '–' + week_end.strftime('%b %d') + '</th>')
    base.extend(['<th scope="col">Δ vs median</th></tr></thead><tbody>'])
    for row, weeks, baseline, delta, subject, edition, ident in entries:
        base.append('<tr><th scope="row"><a href="#'+ ident +'">' + escape(row["title"]) + '</a> ('+edition+')</th>')
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
                 '</div></footer></body></html>\n'])
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_bundle", type=Path)
    parser.add_argument("local_preview_directory", type=Path)
    args = parser.parse_args(argv)
    try:
        result = export_verified_preview(args.source_bundle, args.local_preview_directory)
    except (OSError, ValueError) as exc:
        print(f"PREVIEW_REJECTED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
