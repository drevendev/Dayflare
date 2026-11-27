"""Offline controls; these fixture IDs are synthetic and not measurements."""
import copy
from datetime import date
import unittest
from tools.m1_additional_coverage import ROOT, SEED, gate, load
from tools.m1_title_discovery import validate_curated


class AdditionalCoverageTests(unittest.TestCase):
    def setUp(self):
        self.curated = load(SEED)
        self.rows = validate_curated(self.curated, date(2026, 11, 27))
        self.report = dict(requested_count=10, candidate_count=10, excluded_count=0,
                           attempts=[dict(project=r['project'], requested_title=r['title'],
                                          page_id=i, status='candidate')
                                     for i, r in enumerate(self.rows, 1)])
        self.selected = [dict(project=r['project'], title=r['title'], subject=r['subject'],
                              page_id=i) for i, r in enumerate(self.rows, 1)]
        self.handoff = dict(candidate_count=10, excluded_count=0,
                            metric_scope='title_scoped_views_not_stable_page_id_history')

    def test_distinct_editorial_cohort(self):
        self.assertEqual(len(self.rows), 10)
        self.assertTrue(all(r['relation'] == 'ambiguous' for r in self.rows))
        for prior in ('m1_curated_expanded_30_enru.json', 'm1_curated_niche_20_enru.json'):
            old = load(ROOT / 'examples' / prior)['pages']
            self.assertFalse({(r['project'], r['title']) for r in old} &
                             {(r['project'], r['title']) for r in self.rows})
            self.assertFalse({r['topic_id'] for r in old} & {r['topic_id'] for r in self.rows})

    def test_complete_gate(self):
        gate(self.curated, self.report, self.selected, self.handoff)

    def test_missing_redirect_and_identity_mismatch(self):
        report = copy.deepcopy(self.report)
        report['attempts'][0]['status'] = 'excluded'
        with self.assertRaises(ValueError):
            gate(self.curated, report, self.selected, self.handoff)
        for field, bad in (('page_id', 999), ('title', 'Unrelated'), ('subject', 'other')):
            selected = copy.deepcopy(self.selected)
            selected[0][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                gate(self.curated, self.report, selected, self.handoff)
        with self.assertRaises(ValueError):
            gate(self.curated, self.report, self.selected[:-1], self.handoff)

    def test_duplicate_id_and_wrong_scope(self):
        report = copy.deepcopy(self.report)
        selected = copy.deepcopy(self.selected)
        report['attempts'][1]['page_id'] = report['attempts'][0]['page_id']
        selected[1]['page_id'] = selected[0]['page_id']
        with self.assertRaises(ValueError):
            gate(self.curated, report, selected, self.handoff)
        with self.assertRaises(ValueError):
            gate(self.curated, self.report, self.selected,
                 dict(self.handoff, metric_scope='historical_identity'))

    def test_workflow_is_master_only_and_read_only(self):
        text = (ROOT / '.github/workflows/m1-additional-coverage.yml').read_text()
        self.assertIn("if: github.ref == 'refs/heads/master'", text)
        self.assertIn('contents: read', text)
        self.assertIn('persist-credentials: false', text)
        self.assertNotIn('schedule:', text)
        self.assertNotIn('pull_request:', text)
        self.assertNotIn('contents: write', text)
        self.assertLess(text.index('m1_additional_coverage gate'), text.index('rolling_pageview_source collect'))
        self.assertLess(text.index('rolling_pageview_source verify artifacts/'), text.index('rolling_snapshot_preview artifacts/'))
