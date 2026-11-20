"""Regression tests for the pinned 30-title offline reader."""
import json
import shutil
import subprocess
from html.parser import HTMLParser
import unittest

from tools.m1_30_reader import render, metrics
from tools.m1_30_retained_candidate import read_candidate


class TagReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.articles = 0
        self.rows = 0
        self.deltas = []
        self.volumes = []
        self.compare_links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'article':
            self.articles += 1
            self.deltas.append(float(dict(attrs)['data-delta']))
            self.volumes.append(int(dict(attrs)['data-volume']))
        if tag == 'tr':
            self.rows += 1
        if tag == 'a' and dict(attrs).get('class') == 'compare-jump':
            self.compare_links.append(dict(attrs))


class ReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = read_candidate()[1]

    def test_static_counts_provenance_and_determinism(self):
        raw = render(self.candidate)
        self.assertEqual(raw, render(self.candidate))
        text = raw.decode('utf-8')
        parsed = TagReader()
        parsed.feed(text)
        self.assertEqual(parsed.articles, 30)
        self.assertEqual(parsed.rows, 30 * (35 + 5 + 2))
        expected = sorted(self.candidate['series'],
                          key=lambda row: (-abs(metrics(row)[1]), row['project'], row['page_id']))
        self.assertEqual(parsed.deltas, [metrics(row)[1] for row in expected])
        self.assertEqual(parsed.volumes, [metrics(row)[0] for row in expected])
        self.assertTrue(any(delta > 0 for delta in parsed.deltas))
        self.assertTrue(any(delta < 0 for delta in parsed.deltas))
        self.assertIn('<label for="sort">Order by requests or measured change', text)
        self.assertIn('value="volume">Most requests in last complete UTC week', text)
        self.assertIn('Largest signed increase first', text)
        self.assertIn('Largest signed decrease first', text)
        self.assertIn('Retrieved 2026-11-17T08:30:55Z', text)
        self.assertIn('OFFLINE · UNPUBLISHED', text)
        self.assertIn('Original raw HTTP response bodies', text)
        self.assertIn(self.candidate['dataset_id'], text)
        self.assertIn('History, values &amp; evidence', text)
        self.assertIn('dataset:data.dataset,method:data.method', text)

    def test_each_card_links_to_existing_stable_identity_comparison(self):
        text = render(self.candidate).decode('utf-8')
        parsed = TagReader()
        parsed.feed(text)
        expected_ids = {f"{row['project']}:{row['page_id']}" for row in self.candidate['series']}
        self.assertEqual(len(parsed.compare_links), 30)
        self.assertEqual({item['data-compare-id'] for item in parsed.compare_links}, expected_ids)
        self.assertTrue(all(item['href'] == '#compare' and
                            item['aria-label'].startswith('Compare ') for item in parsed.compare_links))
        self.assertIn('.controls,#compare,.card-actions{display:none!important}', text)
        self.assertIn("right.focus({preventScroll:true})", text)
        self.assertIn("if(right.value===id)right.value=''", text)

    def test_final_week_volume_sort_runs_generated_javascript(self):
        """Volume sorting must differ from signed change and preserve ties/inputs."""
        if not shutil.which('node'):
            self.skipTest('Node is unavailable for generated sorting JavaScript')
        html = render(self.candidate).decode('utf-8')
        script = html.rsplit('<script>', 1)[1].split('</script>', 1)[0]
        sort_fn = ('function sortTiles()' + script.split('function sortTiles()', 1)[1]
                   .split(chr(10) + ' search.addEventListener', 1)[0])
        setup = r"""
const tiles=[
  {dataset:{delta:'100',volume:'4'}},
  {dataset:{delta:'-20',volume:'25'}},
  {dataset:{delta:'0',volume:'25'}},
  {dataset:{delta:'5',volume:'10'}}
];
const original=JSON.stringify(tiles.map(t=>t.dataset));
const sort={value:'magnitude'};
const parent={children:[],replaceChildren(...items){this.children=items;}};
const $=id=>{if(id!=='cards')throw Error('Unexpected selector');return parent;};
function check(mode,expected){
  sort.value=mode;sortTiles();
  const actual=parent.children.map(t=>tiles.indexOf(t));
  if(JSON.stringify(actual)!==JSON.stringify(expected))
    throw Error('Incorrect '+mode+' order: '+actual);
  if(JSON.stringify(tiles.map(t=>t.dataset))!==original)
    throw Error('Sorting mutated source observations');
}
check('magnitude',[0,1,3,2]);
check('increase',[0,3,2,1]);
check('decrease',[1,2,3,0]);
check('volume',[1,2,3,0]); // equal-volume ties retain original card order
"""
        result = subprocess.run(
            ['node', '-'], input=sort_fn + chr(10) + setup,
            text=True, capture_output=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_numeric_change_exactly_median_of_four_weeks(self):
        row = self.candidate['series'][0]
        values = [item['views'] for item in row['daily']]
        latest, delta, baseline = metrics(row)
        self.assertEqual(latest, sum(values[-7:]))
        self.assertEqual(delta, latest - baseline)
        self.assertGreaterEqual(baseline, 0)

    def test_half_integer_median_is_exact_in_rendered_cards(self):
        clone = json.loads(json.dumps(self.candidate))
        row = clone['series'][0]
        for week, total in enumerate((100, 100, 101, 101, 200)):
            for day in range(7):
                row['daily'][week * 7 + day]['views'] = total if day == 0 else 0
        marker = f'id="page-{row["project"].split(".")[0]}-{row["page_id"]}"'

        def card():
            return render(clone).decode('utf-8').split(marker, 1)[1].split('</article>', 1)[0]

        self.assertEqual(metrics(row)[1], 99.5)
        self.assertIn('>+99.5</strong>', card())
        row['daily'][28]['views'] = 100
        self.assertEqual(metrics(row)[1], -0.5)
        self.assertIn('>-0.5</strong>', card())
        row['daily'][28]['views'] = 101
        self.assertEqual(metrics(row)[1], 0.5)
        self.assertIn('>+0.5</strong>', card())

    def test_share_link_id_validation_rejects_inherited_properties(self):
        html = render(self.candidate).decode('utf-8')
        script = html.rsplit('<script>', 1)[1].split('</script>', 1)[0]
        own_key = script.split('const hasHistory=', 1)[1].split(';', 1)[0]
        predicate = script.split('let valid=', 1)[1].split(';if(valid)', 1)[0]
        cleaner = script.split('const cleaned=', 1)[1].split(';', 1)[0]
        self.assertIn('Object.prototype.hasOwnProperty.call(rows,id)', own_key)
        self.assertIn("hasHistory(params.get('left'))", predicate)
        self.assertIn("hasHistory(params.get('right'))", predicate)
        if not shutil.which('node'):
            self.skipTest('Node is unavailable for JavaScript URL validation')
        js = ("const rows={'en.wikipedia:1':{},'ru.wikipedia:2':{}};"
              "const data={dataset:'d',method:'m'};"
              "const hasHistory=" + own_key + ";"
              "const cleaned=" + cleaner + ";"
              "function check(s){const params=new URLSearchParams(s);"
              "let valid=" + predicate + ";return !!valid;}"
              "const url=(left,right,dataset='d')=>new URLSearchParams({"
              "dataset,method:'m',left,right}).toString();"
              "if(!check(url('en.wikipedia:1','ru.wikipedia:2')))process.exit(10);"
              "for(const id of ['toString','constructor','__proto__','unknown'])"
              "if(check(url(id,'ru.wikipedia:2')))process.exit(11);"
              "if(check(url('en.wikipedia:1','ru.wikipedia:2','old')))process.exit(12);"
              "if(check(url('en.wikipedia:1','en.wikipedia:1')))process.exit(13);"
              "const rich=(q='',ed='',order='magnitude')=>new URLSearchParams({"
              "dataset:'d',method:'m',left:'en.wikipedia:1',right:'ru.wikipedia:2',q,ed,order}).toString();"
              "if(!check(rich('Chess','RU','decrease')))process.exit(14);"
              "if(!check(rich('Chess','RU','volume')))process.exit(21);"
              "for(const q of ['a\\nb','a\\u007fb','x'.repeat(81)])"
              "if(check(rich(q)))process.exit(15);"
              "if(check(rich('','BAD')))process.exit(16);"
              "if(check(rich('','RU','bad')))process.exit(17);"
              "if(check(rich()+'&unexpected=1'))process.exit(18);"
              "if(check(url('en.wikipedia:1','ru.wikipedia:2')+'&q=x'))process.exit(19);"
              "if(check('other=1'))process.exit(20);")
        result = subprocess.run(['node', '-'], input=js, text=True,
                                capture_output=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_russian_yo_search_matches_without_rewriting_titles_or_queries(self):
        """Use the actual generated filter JS, not a separate invented matcher."""
        html = render(self.candidate).decode('utf-8')
        self.assertIn('aria-describedby="search-hint"', html)
        self.assertIn('Russian е and ё spellings match for search', html)
        self.assertIn('s.normalize(\'NFC\')', html)
        if not shutil.which('node'):
            self.skipTest('Node is unavailable for generated discovery JavaScript')
        script = html.rsplit('<script>', 1)[1].split('</script>', 1)[0]
        cleaned = 'const cleaned=' + script.split('const cleaned=', 1)[1].split(';', 1)[0] + ';'
        matcher = 'const matchKey=' + script.split('const matchKey=', 1)[1].split(';', 1)[0] + ';'
        filter_fn = ('function filter()' + script.split('function filter()', 1)[1]
                     .split('\nfunction sortTiles()', 1)[0])
        setup = r"""
const search={value:''},edition={value:''},status={textContent:''};
const noResults={hidden:true};
const $=id=>id==='no-results'?noResults:null;
const tiles=[
  {dataset:{text:'RU Чёрная дыра',edition:'RU'},hidden:false},
  {dataset:{text:'EN Black hole',edition:'EN'},hidden:false}
];
const original=tiles[0].dataset.text;
function check(input,ed,expected) {
  search.value=input;edition.value=ed;filter();
  const count=tiles.filter(t=>!t.hidden).length;
  if(count!==expected || status.textContent!==expected+' of 2 histories' ||
     noResults.hidden!==(expected!==0) || search.value!==input ||
     tiles[0].dataset.text!==original)
    throw Error('Incorrect search/identity behavior for '+JSON.stringify([input,ed]));
}
check('черная дыра','RU',1);
check('ЧЁРНАЯ ДЫРА','',1);
check('че\u0308рная дыра','RU',1);
check('чёрная дыра','RU',1);
check('черная дыра','EN',0);
check('черная дырка','RU',0);
check('Black hole','EN',1);
"""
        result = subprocess.run(
            ['node', '-'], input=cleaned + '\n' + matcher + '\n' +
            filter_fn + '\n' + setup, text=True, capture_output=True,
            timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pair_csv_export_requires_complete_equivalent_utc_dates(self):
        html = render(self.candidate).decode('utf-8')
        self.assertIn('id="download-csv" download="dayflare-30-pair.csv" hidden', html)
        self.assertIn('utc_date,left_page_id,left_requests,right_page_id,right_requests,dataset_id,method_version', html)
        self.assertIn('data:text/csv;charset=utf-8,', html)
        self.assertIn("const peak=Math.max(1,...ta,...tb)", html)
        self.assertIn('One shared zero-based scale', html)
        self.assertIn('className=\'pair-chart\'', html)
        self.assertIn('className=\'pair-daily\'', html)
        self.assertIn('Inspect all 35 exact UTC days (A and B)', html)
        self.assertIn('Exact daily requests for the same 35-day window', html)
        self.assertIn("csvLink.hidden=true;csvLink.href=''", html)
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][1]['daily'][18]['date'] = '2026-10-11'
        with self.assertRaisesRegex(ValueError, 'incomparable observation window'):
            render(clone)

    def test_week_date_ranges_are_inclusive_and_observed(self):
        html = render(self.candidate).decode('utf-8')
        dates = [point['date'] for point in self.candidate['series'][0]['daily']]
        self.assertEqual(len(dates), 35)
        self.assertEqual(html.count('class="week-date"'), 150)
        for week in range(5):
            exact = dates[week * 7] + '–' + dates[week * 7 + 6] + ' UTC'
            self.assertEqual(html.count(exact), 30)
        self.assertIn("dates.textContent=data.dates[i*7]+'–'+data.dates[i*7+6]+' UTC'", html)
        self.assertIn('W1–W5 map to inclusive UTC date ranges', html)

    def test_no_js_fallback_hides_inoperative_actions(self):
        """Static histories remain usable without inert interactive controls."""
        html = render(self.candidate).decode('utf-8')
        self.assertIn('<noscript><style>.controls,#compare,.card-actions{display:none!important}</style>', html)
        head, body = html.split('</head>', 1)
        self.assertIn('<noscript><style>.controls,#compare,.card-actions{display:none!important}</style>', head)
        self.assertIn('<noscript><p class="warning" role="note">', body)
        self.assertIn('JavaScript is disabled.', html)
        self.assertIn('Search, filters and comparison require JavaScript.', html)
        self.assertIn('All 30 selected articles and their exact 35-day histories', html)
        self.assertEqual(html.count('<article '), 30)
        self.assertEqual(html.count('<table><caption>Daily requests'), 30)

    def test_reject_incomplete_window_and_unsafe_source_link(self):
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][1]['daily'].pop()
        with self.assertRaises(ValueError):
            render(clone)
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][0]['source']['endpoint'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError):
            render(clone)

    def test_reject_duplicate_page_identity_and_inconsistent_dates(self):
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][1]['project'] = clone['series'][0]['project']
        clone['series'][1]['page_id'] = clone['series'][0]['page_id']
        with self.assertRaises(ValueError):
            render(clone)
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][1]['daily'][0]['date'] = '1900-01-01'
        with self.assertRaises(ValueError):
            render(clone)


    def test_incompatible_share_link_warning_clears_after_repair(self):
        """Exercise the generated inline JS: invalid link -> valid comparison."""
        if not shutil.which('node'):
            self.skipTest('Node is unavailable for comparison interaction test')
        html = render(self.candidate).decode('utf-8')
        script = html.rsplit('<script>', 1)[1].split('</script>', 1)[0]
        setup = r"""
class Element {
  constructor(id='') {
    this.id=id; this.hidden=true; this.value=''; this.textContent='';
    this.dataset={}; this.children=[]; this.handlers={};this.style={};this.attributes={};
  }
  addEventListener(type,fn){this.handlers[type]=fn;}
  setAttribute(name,value){this.attributes[name]=String(value);}
  replaceChildren(...children){this.children=children;}
  append(...children){this.children.push(...children);}
  select(){} focus(){}
}
const elements=Object.create(null);
const el=id=>elements[id]||(elements[id]=new Element(id));
const rows=Object.create(null);
rows['en.wikipedia:1']={title:'A',edition:'EN',values:Array(35).fill(2)};
rows['ru.wikipedia:2']={title:'B',edition:'RU',values:Array(35).fill(3)};
el('dataset').textContent=JSON.stringify({
  dataset:'current',method:'v0',rows,
  dates:Array.from({length:35},(_,i)=>new Date(Date.UTC(2026,9,11+i)).toISOString().slice(0,10)),
  start:'2026-10-11',end:'2026-11-14'
});
const document={
  getElementById:el,querySelectorAll:()=>[],
  createElement:tag=>new Element(tag),
  createElementNS:(ns,tag)=>new Element(tag)
};
const location={
  search:'?dataset=outdated&method=v0&left=en.wikipedia%3A1&right=ru.wikipedia%3A2',
  href:'file:///local/dayflare.html?dataset=outdated#compare'
};
const navigator={clipboard:{writeText:async()=>{}}};
"""
        check = r"""
if(el('invalid-link').hidden!==false) throw Error('Old link warning missing');
if(!el('compare-message').textContent.includes('Incompatible')) {
  throw Error('Old link error missing');
}
el('left').value='en.wikipedia:1';
el('right').value='ru.wikipedia:2';
el('right').handlers.change();
if(el('comparison').children.length!==2 || el('comparison').children[1].id!=='table') {
  throw Error('Exact comparison table missing');
}
const chart=el('comparison').children[0];
const weeks=chart.children[2].children;
if(chart.className!=='pair-chart' || weeks.length!==5 || weeks.some(w=>w.children[0].children.length!==2)) {
  throw Error('Five pairs of chart bars missing');
}
const tableRows=el('comparison').children[1].children[2].children;
if(tableRows.length!==5) throw Error('Weekly date-range rows absent');
const dates=JSON.parse(el('dataset').textContent).dates;
const daily=chart.children[3];
if(!daily||daily.id!=='details'||daily.className!=='pair-daily'||daily.children[0].textContent!=='Inspect all 35 exact UTC days (A and B)'){
  throw Error('Exact daily comparison disclosure missing');
}
const dailyTable=daily.children[1],dailyRows=dailyTable.children[2].children;
if(dailyTable.id!=='table'||dailyRows.length!==35||dailyTable.children[1].children[0].children.length!==3){
  throw Error('35-day three-column comparison table missing');
}
for(const i of [0,17,34]){
  const cells=dailyRows[i].children;
  if(cells.length!==3||cells[0].textContent!==dates[i]||cells[1].textContent!=='2'||cells[2].textContent!=='3'){
    throw Error('Exact daily comparison values mismatch at '+i);
  }
}
for(let i=0;i<5;i++){
  const label=tableRows[i].children[0];
  const expected=dates[7*i]+'–'+dates[7*i+6]+' UTC';
  if(label.textContent!=='W'+(i+1)||label.children[0].textContent!==expected)
    throw Error('Incorrect inclusive UTC week '+i);
}
const heights=weeks.flatMap(w=>w.children[0].children.map(b=>parseFloat(b.style.height)));
if(heights.length!==10 || heights.some(h=>!Number.isFinite(h)||h<0||h>112) || Math.abs(Math.max(...heights)-112)>0.00001) {
  throw Error('Pair bars do not use shared nonnegative scale');
}
if(!el('share-field').value.includes('dataset=current')) {
  throw Error('Recovered link still uses wrong dataset');
}
if(el('invalid-link').hidden!==true) {
  throw Error('Stale error is shown after recovery');
}
if(el('download-csv').hidden || !el('download-csv').href.startsWith('data:text/csv;charset=utf-8,')) {
  throw Error('Valid pair CSV not available');
}
const exported=decodeURIComponent(el('download-csv').href.split(',',2)[1]);
if(exported.trimEnd().split(/\r\n/).length!==36) {
  throw Error('Pair CSV must have a header and 35 exact UTC daily rows');
}
el('search').value='  Chess\t\n  ';
el('search').handlers.input();
el('edition').value='RU';el('edition').handlers.change();
el('sort').value='decrease';el('sort').handlers.change();
const shared=new URL(el('share-field').value);
if(shared.searchParams.get('q')!=='Chess'||shared.searchParams.get('ed')!=='RU'||shared.searchParams.get('order')!=='decrease'||!el('search').value.startsWith('  Chess'))throw Error('Discovery filters dropped from comparison share or edited the live input');
el('search').value='Black ';
el('search').handlers.input();
if(el('search').value!=='Black ')throw Error('Typing removed word separator');
el('search').value+='hole';
el('search').handlers.input();
if(el('search').value!=='Black hole'||new URL(el('share-field').value).searchParams.get('q')!=='Black hole')throw Error('Multiword title/share mismatch');
el('search').value='че\u0308рная дыра';
el('search').handlers.input();
if(new URL(el('share-field').value).searchParams.get('q')!==el('search').value)throw Error('Unicode source search was normalized in shared q');
el('right').value='en.wikipedia:1';
el('right').handlers.change();
if(el('download-csv').hidden!==true || el('download-csv').href!=='') {
  throw Error('Pair CSV available after invalid same-article comparison');
}
"""
        result = subprocess.run(
            ['node', '-'], input=setup + '\n' + script + '\n' + check,
            text=True, capture_output=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        restored_setup = setup.replace(
            "search:'?dataset=outdated&method=v0&left=en.wikipedia%3A1&right=ru.wikipedia%3A2'",
            "search:'?dataset=current&method=v0&left=en.wikipedia%3A1&right=ru.wikipedia%3A2&q=Chess&ed=RU&order=decrease'")
        restored_check = r"""
if(el('invalid-link').hidden!==true || el('search').value!=='Chess' ||
   el('edition').value!=='RU' || el('sort').value!=='decrease')
  throw Error('Rich share link did not restore exact discovery controls');
if(el('comparison').children.length!==2 || el('download-csv').hidden)
  throw Error('Rich share link did not restore the comparison');
if(!el('share-field').value.includes('q=Chess&ed=RU&order=decrease'))
  throw Error('Restored share URL lost filter state');
"""
        restored = subprocess.run(
            ['node', '-'], input=restored_setup + '\n' + script + '\n' + restored_check,
            text=True, capture_output=True, timeout=8, check=False)
        self.assertEqual(restored.returncode, 0, restored.stderr)



if __name__ == '__main__':
    unittest.main()
