"""Build a standalone *unpublished* EN/RU reader from the retained 30-title JSON.

Runs offline, has no dependencies or external assets, and never overwrites outputs.
Validation is delegated to the independently pinned candidate decoder on CLI.
This is a normalized-data presentation, not a substitute for raw source evidence.
"""
from __future__ import annotations

import argparse
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


def sparkline(row: dict) -> str:
    values = [point['views'] for point in row['daily']]
    maximum = max(values) or 1
    xy = ' '.join(f'{8 + i * 6},{51 - round(value * 43 / maximum)}'
                  for i, value in enumerate(values))
    return (f'<svg viewBox="0 0 221 60" aria-hidden="true" focusable="false" '
            f'preserveAspectRatio="none"><polyline points="{xy}" fill="none" '
            f'stroke="currentColor" stroke-width="2.6" vector-effect="non-scaling-stroke"/>'
            f'</svg>')


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
        daily_rows = ''.join(f'<tr><th scope="row">{e(p["date"])}</th><td>{p["views"]:,}</td></tr>'
                             for p in r['daily'])
        comparison_weeks = [sum(r['daily'][i + j]['views'] for j in range(7))
                            for i in (0, 7, 14, 21, 28)]
        week_rows = ''.join(
            f'<tr><th scope="row">W{i + 1}<span class="week-date">'
            f'{expected_dates[7 * i]}–{expected_dates[7 * i + 6]} UTC'
            f'</span></th><td>{v:,}</td></tr>'
                            for i, v in enumerate(comparison_weeks))
        articles.append(f'''<article id="{anchor}" class="tile" data-delta="{delta}" data-text="{e(edition + ' ' + title)}" data-edition="{edition}">
          <div class="topline"><span class="edition">{edition}</span><span class="code">page #{r['page_id']}</span></div>
          <h3>{e(title)}</h3><div class="metrics"><div><span>Last 7 days</span><strong>{weekly:,}</strong></div>
          <div><span>vs prior 4-week median</span><strong class="{'rise' if delta >= 0 else 'fall'}">{e(difference)}</strong></div></div>
          <div class="curve">{sparkline(r)}</div><p class="minor">Relative change: {e(ratio)} · 35 observed days</p>
           <p class="card-actions"><a class="compare-jump" href="#compare" data-compare-id="{e(ident)}" aria-label="Compare {e(title)} ({edition}) with another selected article">Compare this article</a></p>
          <details><summary>History, values &amp; evidence</summary>
          <div class="detail"><p>The baseline is the median of four non-overlapping seven-day totals immediately before the last seven days. It is not a lifecycle classification.</p>
          <div class="tables"><table><caption>Five seven-day totals</caption><thead><tr><th scope="col">Period</th><th scope="col">Requests</th></tr></thead><tbody>{week_rows}</tbody></table>
          <table><caption>Daily requests, {e(start)}–{e(end)}</caption><thead><tr><th scope="col">UTC date</th><th scope="col">Requests</th></tr></thead><tbody>{daily_rows}</tbody></table></div>
          <p class="minor">Raw response SHA-256 (reported): <code>{e(r['source']['body_sha256'])}</code></p>
          <p class="links"><a href="{e(wiki)}" target="_blank" rel="noopener noreferrer">Wikipedia page</a><a href="{e(endpoint)}" target="_blank" rel="noopener noreferrer">Wikimedia API request</a><a href="#{anchor}">Link to this article</a></p>
          </div></details></article>''')
        options.append(f'<option value="{e(ident)}">{e(edition + " · " + title)}</option>')
        compare_data[ident] = {'title': title, 'edition': edition,
                               'values': [p['views'] for p in r['daily']]}
    payload = json.dumps({'dataset': dataset, 'method': method, 'start': start, 'end': str(end),
                          'dates': expected_dates, 'rows': compare_data}, ensure_ascii=False, separators=(',', ':'))
    payload = payload.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    css = '''
:root{color-scheme:dark;--bg:#09151d;--panel:#142735;--ink:#f1f6f8;--muted:#b5c8d0;--line:#3c5c6b;--accent:#e8d78b;--good:#9fe2ca;--bad:#ffb5ab;font-family:system-ui,-apple-system,Segoe UI,sans-serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);line-height:1.5}a{color:var(--accent)}a:hover{text-decoration-thickness:2px}:focus-visible{outline:3px solid var(--accent);outline-offset:4px}button,input,select{font:inherit}button,select,input{min-height:44px;border:1px solid var(--line);border-radius:8px;background:#1a3140;color:var(--ink);padding:8px 12px}button{cursor:pointer}button:hover{background:#275065}.wrap{width:min(1160px,calc(100% - 36px));margin:auto}.skip{position:absolute;top:-100px;left:16px;z-index:3}.skip:focus{top:12px;background:var(--bg)}header{padding:45px 0 38px;border-bottom:1px solid var(--line);background:radial-gradient(ellipse at 75% 0%,#274657 0%,transparent 63%)}.eyebrow,.edition{color:var(--accent);font-size:.76rem;letter-spacing:.12em;font-weight:750;text-transform:uppercase}h1{font-size:clamp(2.1rem,5.5vw,4.25rem);line-height:1.05;letter-spacing:-.04em;margin:12px 0 15px;max-width:900px}h2{font-size:clamp(1.35rem,3vw,2rem);line-height:1.16}h3{font-size:1.27rem;margin:10px 0 15px;overflow-wrap:anywhere}.lead{color:#d7e5ec;max-width:760px;font-size:1.09rem}.status{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}.status span{padding:6px 11px;border-radius:99px;background:#234253;color:#e9f3f6;border:1px solid var(--line);font-size:.86rem}.warning{background:#352d23;border-left:4px solid var(--accent);padding:14px 18px;margin:24px 0;color:#ffeac7}.controls{display:flex;flex-wrap:wrap;gap:14px;align-items:end;margin:25px 0}.controls label,.form label{display:grid;gap:6px;color:var(--muted);font-size:.91rem}.controls input{width:min(340px,78vw)}.controls select{width:170px}.count{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:17px;margin:24px 0 54px}.tile{min-width:0;scroll-margin-top:18px;background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:20px;box-shadow:0 6px 24px #0002}.tile:target{border-color:var(--accent);outline:2px solid var(--accent)}.topline{display:flex;justify-content:space-between;align-items:center;gap:10px}.code,.minor{color:var(--muted);font-size:.82rem}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:10px}.metrics span{display:block;color:var(--muted);font-size:.77rem}.metrics strong{display:block;font-size:1.45rem;letter-spacing:-.04em}.rise{color:var(--good)}.fall{color:var(--bad)}.curve{color:var(--accent);height:75px;margin-top:10px}.curve svg{width:100%;height:100%}details{margin-top:14px}summary{cursor:pointer;color:var(--accent);font-weight:600;padding:9px 0}summary:focus-visible{outline-offset:3px}.detail{border-top:1px solid var(--line);font-size:.87rem}.tables{display:flex;gap:16px;align-items:start;flex-wrap:wrap}table{border-collapse:collapse;min-width:0;width:100%;font-variant-numeric:tabular-nums}caption{text-align:left;font-weight:bold;padding:12px 0 6px}th,td{text-align:left;padding:5px 7px;border-bottom:1px solid var(--line)}td{text-align:right}.tables table{flex:1 1 180px;max-width:100%}.links{display:flex;gap:13px;flex-wrap:wrap}.detail code{overflow-wrap:anywhere}section#compare{background:#102330;border-block:1px solid var(--line);padding:28px 0}.form{display:flex;flex-wrap:wrap;gap:12px;align-items:end}.form label{min-width:0;flex:1 1 190px}.form select{width:100%;max-width:100%}#comparison{max-width:100%;overflow-x:auto}#comparison table{margin-top:15px;max-width:740px}#comparison th:first-child{width:34%}#download-csv{display:inline-flex;align-items:center;min-height:44px;border:1px solid var(--line);border-radius:8px;padding:8px 12px}#share-field{width:min(100%,640px)}#invalid-link,#no-results{padding:13px 16px;border:1px solid var(--accent);border-radius:8px;margin:12px 0;color:var(--accent)}.compare-jump{display:inline-flex;align-items:center;justify-content:center;min-height:44px;border:1px solid var(--line);border-radius:8px;padding:8px 12px;color:var(--accent);text-decoration:none;font-weight:650}.compare-jump:hover{background:#275065}[hidden]{display:none!important}footer{color:var(--muted);padding:28px 0 50px;font-size:.9rem}
.week-date{display:block;color:var(--muted);font-size:.75rem;line-height:1.35;overflow-wrap:anywhere}.pair-chart{max-width:740px;margin:18px 0 12px}.pair-chart figcaption{font-size:.88rem;color:var(--muted);font-weight:600}.pair-legend{font-size:.83rem;color:var(--ink);overflow-wrap:anywhere}.pair-weeks{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;border-bottom:1px solid var(--line)}.pair-week{min-width:0}.pair-bars{height:118px;display:flex;justify-content:center;align-items:end;gap:4px}.pair-bar{display:block;width:min(38%,26px);background:#6bc4db;border-radius:4px 4px 0 0}.pair-bar--b{background:var(--accent)}.pair-week-label{display:block;text-align:center;font-size:.78rem;color:var(--muted);padding:4px 0 6px}
@media(min-width:760px){.detail .tables{display:block}.detail table{margin-top:12px}.detail{max-height:580px;overflow:auto}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}'''
    js = '''(()=>{'use strict';const data=JSON.parse(document.getElementById('dataset').textContent),params=new URLSearchParams(location.search),rows=data.rows;
const $=id=>document.getElementById(id),search=$('search'),edition=$('edition'),sort=$('sort'),tiles=Array.from(document.querySelectorAll('.tile')),status=$('result-count');
const cleaned=s=>Array.from(s).map(c=>c.charCodeAt(0)<32||c.charCodeAt(0)===127?' ':c).join('').trim().split(' ').filter(Boolean).join(' ').slice(0,80);
function filter(){let term=cleaned(search.value).toLocaleLowerCase(),ed=edition.value,n=0;for(let tile of tiles){let show=(!term||tile.dataset.text.toLocaleLowerCase().includes(term))&&(!ed||ed===tile.dataset.edition);tile.hidden=!show;if(show)n++;}status.textContent=n+' of '+tiles.length+' histories';$('no-results').hidden=n!==0;}
function sortTiles(){const mode=sort.value,ordered=tiles.slice().sort((a,b)=>{const av=Number(a.dataset.delta),bv=Number(b.dataset.delta);const diff=mode==='increase'?bv-av:mode==='decrease'?av-bv:Math.abs(bv)-Math.abs(av);return diff||tiles.indexOf(a)-tiles.indexOf(b);});$('cards').replaceChildren(...ordered);}
 search.addEventListener('input',()=>{filter();syncShare();});edition.addEventListener('change',()=>{filter();syncShare();});sort.addEventListener('change',()=>{sortTiles();syncShare();});sortTiles();filter();
const left=$('left'),right=$('right'),message=$('compare-message'),out=$('comparison'),share=$('share-field'),csvLink=$('download-csv');
const hasHistory=id=>Object.prototype.hasOwnProperty.call(rows,id);
function shareLink(){const p=new URLSearchParams({dataset:data.dataset,method:data.method,left:left.value,right:right.value,q:cleaned(search.value),ed:edition.value,order:sort.value});return location.href.split('?')[0].split('#')[0]+'?'+p.toString()+'#compare';}
function syncShare(){if(share.value)share.value=shareLink();}
function renderCompare(){const a=rows[left.value],b=rows[right.value];out.replaceChildren();share.value='';csvLink.hidden=true;csvLink.href='';if(!a||!b){message.textContent='Choose two articles to compare.';return;}if(left.value===right.value){message.textContent='Select two distinct article histories.';return;}
$('invalid-link').hidden=true;
let totals=(v)=>[0,7,14,21,28].map(n=>v.slice(n,n+7).reduce((sum,x)=>sum+x,0));const ta=totals(a.values),tb=totals(b.values);
const peak=Math.max(1,...ta,...tb);if(!Number.isFinite(peak)||ta.some(v=>!Number.isFinite(v)||v<0)||tb.some(v=>!Number.isFinite(v)||v<0)){message.textContent='Comparison unavailable: invalid weekly totals.';return;}
const t=document.createElement('table');let cap=document.createElement('caption');cap.textContent='Exact seven-day request totals · same dates and filter';t.append(cap);let h=document.createElement('thead'),tr=document.createElement('tr');['UTC week',a.edition+' · '+a.title,b.edition+' · '+b.title].forEach(s=>{let th=document.createElement('th');th.scope='col';th.textContent=s;tr.append(th)});h.append(tr);t.append(h);let body=document.createElement('tbody');
for(let i=0;i<5;i++){let row=document.createElement('tr');const period=document.createElement('th');period.scope='row';period.textContent='W'+(i+1);const dates=document.createElement('span');dates.className='week-date';dates.textContent=data.dates[i*7]+'–'+data.dates[i*7+6]+' UTC';period.append(dates);row.append(period);for(const v of [ta[i],tb[i]]){const cell=document.createElement('td');cell.textContent=v.toLocaleString();row.append(cell);}body.append(row)}t.append(body);const chart=document.createElement('figure');chart.className='pair-chart';
const caption=document.createElement('figcaption');caption.textContent='One shared zero-based scale · 0 to '+peak.toLocaleString()+' weekly requests. W1–W5 map to inclusive UTC date ranges in the exact table below.';chart.append(caption);
const legend=document.createElement('p');legend.className='pair-legend';legend.textContent='A (cyan): '+a.edition+' · '+a.title+'  |  B (gold): '+b.edition+' · '+b.title;chart.append(legend);
const weekGrid=document.createElement('div');weekGrid.className='pair-weeks';weekGrid.setAttribute('aria-hidden','true');
for(let i=0;i<5;i++){const week=document.createElement('div');week.className='pair-week';const bars=document.createElement('div');bars.className='pair-bars';for(const [side,total] of [['a',ta[i]],['b',tb[i]]]){const bar=document.createElement('span');bar.className='pair-bar pair-bar--'+side;bar.style.height=(112*total/peak)+'px';bars.append(bar);}const label=document.createElement('span');label.className='pair-week-label';label.textContent='W'+(i+1);week.append(bars,label);weekGrid.append(week);}
chart.append(weekGrid);out.append(chart,t);message.textContent='Comparison of editions, not populations or equivalent topics.';
share.value=shareLink();
const lines=['utc_date,left_page_id,left_requests,right_page_id,right_requests,dataset_id,method_version'];
for(let i=0;i<data.dates.length;i++){lines.push([data.dates[i],left.value,a.values[i],right.value,b.values[i],data.dataset,data.method].join(','));}
const crlf=String.fromCharCode(13,10);
csvLink.href='data:text/csv;charset=utf-8,'+encodeURIComponent(lines.join(crlf)+crlf);
csvLink.hidden=false;}
for(const link of document.querySelectorAll('.compare-jump')){link.addEventListener('click',event=>{const id=link.dataset.compareId;if(!hasHistory(id))return;event.preventDefault();left.value=id;if(right.value===id)right.value='';$('invalid-link').hidden=true;renderCompare();if(!right.value)message.textContent='Choose a second article to compare with '+rows[id].edition+' · '+rows[id].title+'.';if(location.hash!=='#compare')history.pushState(null,'','#compare');$('compare').scrollIntoView({block:'start',behavior:'auto'});right.focus({preventScroll:true});});}
left.addEventListener('change',renderCompare);right.addEventListener('change',renderCompare);
if(params.size){let valid=(params.size===4||params.size===7)&&['dataset','method','left','right'].every(k=>params.has(k))&&params.get('dataset')===data.dataset&&params.get('method')===data.method&&hasHistory(params.get('left'))&&hasHistory(params.get('right'))&&params.get('left')!==params.get('right')&&(params.size===4||(params.has('q')&&params.has('ed')&&params.has('order')&&params.get('q').length<=80&&params.get('q')===cleaned(params.get('q'))&&['','EN','RU'].includes(params.get('ed'))&&['magnitude','increase','decrease'].includes(params.get('order'))));if(valid){if(params.size===7){search.value=params.get('q');edition.value=params.get('ed');sort.value=params.get('order');sortTiles();filter();}left.value=params.get('left');right.value=params.get('right');renderCompare();}else{$('invalid-link').hidden=false;message.textContent='Incompatible comparison or discovery link; choose two current entries.';}}else renderCompare();
$('copy-link').addEventListener('click',async()=>{if(!share.value){message.textContent='Choose two articles first.';return;}try{await navigator.clipboard.writeText(share.value);message.textContent='Local-file link copied; share the HTML file too.';}catch(_){share.focus();share.select();message.textContent='Copy the selected local-file link manually; recipients also need this HTML file.';}});
})();'''
    opts = ''.join(options)
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>Dayflare · 30 observed EN/RU histories · offline</title><style>{css}</style><noscript><style>.controls,#compare,.card-actions{{display:none!important}}</style></noscript></head>
<body><a class="skip" href="#discover">Skip to discovery</a><header><div class="wrap"><p class="eyebrow">Dayflare / measured attention</p>
<h1>See what changed in Wikipedia reading.</h1><p class="lead">Explore <strong>30 selected articles</strong> in English and Russian Wikipedia. Inspect real daily request counts, find larger changes and compare two histories without an account or network connection.</p>
<div class="status"><span>35 UTC days · {e(start)} to {e(end)}</span><span>15 EN · 15 RU</span><span>Retrieved {e(candidate['retrieved_at'])}</span><span>OFFLINE · UNPUBLISHED</span></div></div></header>
<main><div class="wrap"><aside class="warning" role="note"><strong>Dated, selected sample — not live.</strong> These are page requests, not unique readers or evidence of interest, approval or causes. A higher or lower week is not a validated “rising” or “fading” classification. Topic titles and observed page IDs do not establish historical identity across page moves. Original raw HTTP response bodies are <strong>not included</strong> in the retained normalized dataset. This offline view is not a published or verified Pages release.</aside>
<noscript><p class="warning" role="note"><strong>JavaScript is disabled.</strong> Search, filters and comparison require JavaScript. All 30 selected articles and their exact 35-day histories remain readable below; open “History, values &amp; evidence” in any card.</p></noscript>
<section id="discover" aria-labelledby="discover-heading"><h2 id="discover-heading">Discover a measured change</h2><p class="count">Ordered by magnitude of the difference between the final seven days and the median of four preceding weeks; not a ranking of all Wikipedia articles.</p><div class="controls">
<label for="search">Search selected articles<input id="search" type="search" placeholder="Article title or edition" autocomplete="off"></label>
<label for="edition">Wikipedia edition<select id="edition"><option value="">EN + RU</option><option value="EN">English</option><option value="RU">Russian</option></select></label>
<label for="sort">Order by measured change<select id="sort"><option value="magnitude">Largest absolute weekly difference</option><option value="increase">Largest signed increase first</option><option value="decrease">Largest signed decrease first</option></select></label>
<span id="result-count" class="count" role="status" aria-live="polite">30 histories</span></div><p id="no-results" hidden role="status">No selected articles match. Clear the search or edition filter.</p>
<div id="cards" class="grid">{''.join(articles)}</div></section></div><section id="compare" aria-labelledby="compare-heading"><div class="wrap"><h2 id="compare-heading">Compare two observed histories</h2><p>Equivalent UTC days, request filters and method. Edition differences are not population differences or evidence that two titles are the same concept.</p><div class="form"><label for="left">First article<select id="left">{opts}</select></label><label for="right">Second article<select id="right">{opts}</select></label></div>
<p id="invalid-link" role="alert" hidden>Link dataset, method or article IDs are incompatible with this archived copy. Select a new comparison.</p><p id="compare-message" role="status" aria-live="polite">Choose two articles to compare.</p><div id="comparison"></div>
<div class="form"><label for="share-field">Local URL for this comparison and discovery filters<input id="share-field" readonly aria-describedby="share-note"></label><button id="copy-link" type="button">Copy comparison link</button><a id="download-csv" download="dayflare-30-pair.csv" hidden>Download exact 35-day CSV</a></div><p id="share-note" class="minor">The URL preserves this comparison, discovery search, edition and ordering. It only works if the recipient also has this exact HTML file at the same path; it is not a public hosted link.</p></div></section></main>
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
