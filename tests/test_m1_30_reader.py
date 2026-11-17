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


if __name__ == '__main__':
    unittest.main()
