"""Regression tests for the pinned 30-title offline reader."""
import json
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
