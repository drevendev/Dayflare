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

    def handle_starttag(self, tag, attrs):
        if tag == 'article':
            self.articles += 1
        if tag == 'tr':
            self.rows += 1


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
        self.assertIn('Retrieved 2026-11-17T08:30:55Z', text)
        self.assertIn('OFFLINE · UNPUBLISHED', text)
        self.assertIn('Original raw HTTP response bodies', text)
        self.assertIn(self.candidate['dataset_id'], text)
        self.assertIn('History, values &amp; evidence', text)
        self.assertIn('dataset:data.dataset,method:data.method', text)

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
        self.assertIn('Object.prototype.hasOwnProperty.call(rows,id)', own_key)
        self.assertIn("hasHistory(params.get('left'))", predicate)
        self.assertIn("hasHistory(params.get('right'))", predicate)
        if not shutil.which('node'):
            self.skipTest('Node is unavailable for JavaScript URL validation')
        js = ("const rows={'en.wikipedia:1':{},'ru.wikipedia:2':{}};"
              "const data={dataset:'d',method:'m'};"
              "const hasHistory=" + own_key + ";"
              "function check(s){const params=new URLSearchParams(s);"
              "let valid=" + predicate + ";return !!valid;}"
              "const url=(left,right,dataset='d')=>new URLSearchParams({"
              "dataset,method:'m',left,right}).toString();"
              "if(!check(url('en.wikipedia:1','ru.wikipedia:2')))process.exit(10);"
              "for(const id of ['toString','constructor','__proto__','unknown'])"
              "if(check(url(id,'ru.wikipedia:2')))process.exit(11);"
              "if(check(url('en.wikipedia:1','ru.wikipedia:2','old')))process.exit(12);"
              "if(check(url('en.wikipedia:1','en.wikipedia:1')))process.exit(13);")
        result = subprocess.run(['node', '-'], input=js, text=True,
                                capture_output=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pair_csv_export_requires_complete_equivalent_utc_dates(self):
        html = render(self.candidate).decode('utf-8')
        self.assertIn('id="download-csv" download="dayflare-30-pair.csv" hidden', html)
        self.assertIn('utc_date,left_page_id,left_requests,right_page_id,right_requests,dataset_id,method_version', html)
        self.assertIn('data:text/csv;charset=utf-8,', html)
        self.assertIn("csvLink.hidden=true;csvLink.href=''", html)
        clone = json.loads(json.dumps(self.candidate))
        clone['series'][1]['daily'][18]['date'] = '2026-10-11'
        with self.assertRaisesRegex(ValueError, 'incomparable observation window'):
            render(clone)

    def test_no_js_fallback_hides_inoperative_actions(self):
        """Static histories remain usable without inert interactive controls."""
        html = render(self.candidate).decode('utf-8')
        self.assertIn('<noscript><style>.controls,#compare{display:none!important}</style>', html)
        head, body = html.split('</head>', 1)
        self.assertIn('<noscript><style>.controls,#compare{display:none!important}</style>', head)
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
    this.dataset={}; this.children=[]; this.handlers={};
  }
  addEventListener(type,fn){this.handlers[type]=fn;}
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
  createElement:tag=>new Element(tag)
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
if(el('comparison').children.length!==1) {
  throw Error('Valid comparison table missing');
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



if __name__ == '__main__':
    unittest.main()
