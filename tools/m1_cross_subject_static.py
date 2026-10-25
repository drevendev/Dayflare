"""Fail-closed verification of the four adopted, historic title-scoped series."""
from __future__ import annotations

from datetime import date, timedelta
import json
import re
from urllib.parse import quote

SCHEMA = 'dayflare.m1-cross-subject-static.v1'
DATASET = 'm1-cross-subject-title-20261025'
SAMPLE_SHA = 'f159d102eca3e0406a785abde487754ac6cf35e1852cfc5de4235774c25168ba'
SOURCES = {
    'cinema-en': ('culture', 'en.wikipedia.org', 'Cinema', 'ab81b8372fb51260d1c1a58a4d16d1b96568108afc411e17e626799d72d068ba'),
    'cinema-ru': ('culture', 'ru.wikipedia.org', 'Кинематограф', '47ebee145e6fb06aff70c56864dbbd13f3400a7925ef28f5ab8830cf28d889f3'),
    'games-en': ('games', 'en.wikipedia.org', 'Video_game', 'b34b64afb6a66921f81812a658dac5dee87605e291ba89b2c12748b93683d680'),
    'games-ru': ('games', 'ru.wikipedia.org', 'Компьютерная_игра', '15d90e5154d50c2e0f2949b0547c67d99c70dc17e5670f03cb26a11d814c0908'),
}
WINDOW = {'start':'2026-08-11','end':'2026-09-14','expected_days':35}


def _visible_number(value: int | float) -> str:
    """Render the one-decimal precision used by the archived static companion."""
    return f'{value:,.1f}'.removesuffix('.0')


def validate_assets(data_bytes: bytes, html_bytes: bytes) -> dict:
    """Check raw-source receipts, finite measurements, exact no-JS rows and version."""
    if len(data_bytes)>96*1024 or len(html_bytes)>256*1024:
        raise ValueError('Oversized cross-subject asset')
    data=json.loads(data_bytes)
    html=html_bytes.decode('utf-8')
    if (data.get('schema')!=SCHEMA or data.get('dataset_id')!=DATASET or
            data.get('source_sample_sha256')!=SAMPLE_SHA or
            data.get('method_version')!='v0-empirical-35d' or
            data.get('source_collection_schema')!='dayflare.m1-cross-subject-title-views.v1' or
            data.get('observation_window_utc')!=WINDOW or
            data.get('filters')!={'access':'all-access','agent':'user','granularity':'daily'} or
            data.get('acquired_at_utc')!='2026-10-25T14:34:13Z' or
            data.get('source_raw_retained_in_repository') is not False or
            len(data.get('series',[]))!=4 or
            data.get('coverage')!={'selected_titles':4,'measured_series':4,'daily_observations':140,'subjects':['culture','games'],'editions':['en.wikipedia.org','ru.wikipedia.org']}):
        raise ValueError('Unexpected cross-subject provenance, method or coverage')
    if (f'content="{DATASET}"' not in html or 'Historical titles, not stable page IDs.' not in html
            or 'retrieved 25 october 2026' not in html.lower()):
        raise ValueError('Missing historical identity or provenance notice')
    seen=set()
    for series in data['series']:
        key=series.get('id')
        if key not in SOURCES or key in seen:
            raise ValueError('Unexpected or duplicate title series')
        seen.add(key)
        subject,project,article,source_sha=SOURCES[key]
        endpoint=('https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/'
                  +project+'/all-access/user/'+quote(article,safe='')+'/daily/20260811/20260914')
        if (series.get('subject'),series.get('project'),series.get('article'),series.get('source_sha256')) != (subject,project,article,source_sha):
            raise ValueError('Unexpected title identity or raw-body checksum')
        if series.get('source_url')!=endpoint or not series.get('retrieved_at_utc','').startswith('2026-10-25T14:34:'):
            raise ValueError('Unexpected source URL or retrieval time')
        days=series.get('daily_views')
        if not isinstance(days,list) or len(days)!=35 or any(type(v) is not int or v<0 for v in days):
            raise ValueError('Unavailable or invalid daily observations')
        weeks=[sum(days[i:i+7]) for i in range(0,35,7)]
        middle=sorted(weeks[:4]); baseline=(middle[1]+middle[2])/2
        latest=weeks[-1]; delta=latest-baseline
        derived=series.get('computed',{})
        if (derived.get('weekly_totals_oldest_to_current')!=weeks or
                derived.get('latest')!=latest or derived.get('baseline')!=baseline or
                derived.get('delta')!=delta or
                (derived.get('relative_lift') is not None and
                 abs(derived['relative_lift']-(delta/baseline if baseline else 0))>1e-12) or
                (baseline==0 and derived.get('relative_lift') is not None)):
            raise ValueError('Weekly metrics do not match 35 exact days')
        if (html.count('id="'+key+'"')!=1 or
                html.count('data-latest="'+str(latest)+'" data-baseline="'+format(baseline,'g')+
                           '" data-delta="'+format(delta,'g')+'"')!=1 or
                html.count(source_sha)!=1):
            raise ValueError('HTML metrics, identity or evidence checksum disagree')
        # Every displayed value is a source-bound assertion, not just metadata
        # in data-* attributes. A valid release hash cannot prove semantic accuracy.
        escaped=re.escape(key)
        articles=re.findall(r'<article class="series" id="'+escaped+r'"[^>]*>.*?</article>',
                            html, flags=re.DOTALL)
        if len(articles)!=1:
            raise ValueError('Missing or duplicated HTML series article')
        article=articles[0]
        if baseline<=0:
            raise ValueError('Cannot display a relative percentage without a positive baseline')
        sign='+' if delta>=0 else '−'
        summary=re.findall(
            r'<div class="metricrow"><strong class="metric">([^<]+)</strong>'
            r'<div><strong class="(up|down)">([^<]+)</strong>'
            r'<span>vs four-week median ([^<]+)</span></div></div>'
            r'<div class="change">([^<]+)</div>', article)
        expected_summary=(
            f'{latest:,}', 'up' if delta>=0 else 'down',
            sign+f'{abs(delta/baseline)*100:.2f}%',
            _visible_number(baseline),
            sign+_visible_number(abs(delta))+
            ' requests vs baseline · not a lifecycle classification',
        )
        if summary!=[expected_summary]:
            raise ValueError('Visitor-visible HTML summary or percentage disagrees with source')

        week_labels=('11–17 Aug','18–24 Aug','25–31 Aug','1–7 Sep','8–14 Sep')
        tallest=max(weeks)
        expected_bars=''.join(
            '<li><span>'+label+'</span><span class="track"><span style="width:"+
            f'{week*100/tallest:.1f}%'+
            '"></span></span><strong>'+f'{week:,}'+'</strong></li>'
            for label,week in zip(week_labels,weeks)
        )
        bars=re.findall(
            r'<ol class="bars" aria-label="Five complete weekly request totals">(.*?)</ol>',
            article, flags=re.DOTALL)
        if bars!=[expected_bars]:
            raise ValueError('Visitor-visible HTML weekly bar totals, dates or widths disagree')

        rows=re.findall(
            r'<tr data-series="'+escaped+
            r'" data-day="([^"]+)"><th scope="row">([^<]+)</th><td>([0-9,]+)</td></tr>',
            article)
        expected=[((date(2026,8,11)+timedelta(days=i)).isoformat(),int(v))
                  for i,v in enumerate(days)]
        actual=[(day,visible_day,int(v.replace(',','')))
                for day,visible_day,v in rows]
        if (len(rows)!=article.count('<tr data-series="'+key+'"') or
                actual!=[(day,day,value) for day,value in expected]):
            raise ValueError('Visitor-visible HTML daily dates or values disagree')
    if seen!=set(SOURCES):
        raise ValueError('Missing cross-subject title series')
    return {'dataset_id':DATASET,'title_series':4,'daily_observations':140,
            'observation_window_utc':[WINDOW['start'],WINDOW['end']],
            'retrieved_utc':'2026-10-25','source_sample_sha256':SAMPLE_SHA,
            'historical_page_id_continuity':'not_verified',
            'raw_http_bodies_in_release':False}
