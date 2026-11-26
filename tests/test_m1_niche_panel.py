"""Regression for the independent, unmeasured niche-candidate panel."""
import copy
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
import unittest
from tools.m1_title_discovery import DiscoveryError, validate_curated

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / 'examples/m1_curated_niche_20_enru.json'
OLD = ROOT / 'examples/m1_curated_expanded_30_enru.json'
DAY = date(2026, 11, 25)


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


class NichePanelTests(unittest.TestCase):
    def setUp(self):
        self.panel = load(NEW)

    def test_existing_validator_accepts(self):
        rows = validate_curated(self.panel, DAY)
        self.assertEqual(len(rows), 20)
        self.assertEqual(rows, validate_curated(self.panel, DAY))

    def test_balanced_subject_edition_cells(self):
        rows = validate_curated(self.panel, DAY)
        expected = {(p, s): 2 for p in ('en.wikipedia', 'ru.wikipedia')
                    for s in ('books', 'culture', 'games', 'science', 'sport')}
        self.assertEqual(Counter((r['project'], r['subject']) for r in rows), expected)

    def test_no_overlap_with_prior_title_or_topic_candidates(self):
        rows = validate_curated(self.panel, DAY)
        old = validate_curated(load(OLD), DAY)
        self.assertFalse({(r['project'], r['title']) for r in rows} &
                         {(r['project'], r['title']) for r in old})
        self.assertFalse({r['topic_id'] for r in rows} & {r['topic_id'] for r in old})
        self.assertNotEqual(self.panel['panel_id'], load(OLD)['panel_id'])

    def test_editorial_pairs_are_not_asserted_equivalent(self):
        pairs = defaultdict(list)
        for row in validate_curated(self.panel, DAY):
            self.assertEqual(row['relation'], 'ambiguous')
            pairs[row['topic_id']].append(row)
        self.assertEqual(len(pairs), 10)
        for rows in pairs.values():
            self.assertEqual(len(rows), 2)
            self.assertEqual({r['project'] for r in rows}, {'en.wikipedia', 'ru.wikipedia'})
            self.assertEqual(len({r['subject'] for r in rows}), 1)

    def test_duplicate_title_rejected(self):
        panel = copy.deepcopy(self.panel)
        panel['pages'].append(panel['pages'][0])
        with self.assertRaises(DiscoveryError):
            validate_curated(panel, DAY)

    def test_future_selection_rejected(self):
        with self.assertRaises(DiscoveryError):
            validate_curated(self.panel, date(2026, 11, 24))


if __name__ == '__main__':
    unittest.main()
