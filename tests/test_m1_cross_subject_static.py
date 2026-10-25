"""Independent data-to-visitor regression: historical titles remain title-scoped."""
from pathlib import Path
import copy
import json
import unittest

from tools.m1_cross_subject_static import DATASET, validate_assets
from tools.build_static_release import bundle_files

ROOT=Path(__file__).resolve().parents[1]
JSON_FILE=ROOT/'site/m1-cross-subject-20261025.json'
HTML_FILE=ROOT/'site/m1-cross-subject-20261025.html'

class CrossSubjectAtlasTests(unittest.TestCase):
    def test_four_source_bound_histories_and_readable_no_js_tables(self):
        raw=JSON_FILE.read_bytes()
        html=HTML_FILE.read_bytes()
        meta=validate_assets(raw,html)
        self.assertEqual(meta['daily_observations'],140)
        self.assertEqual(meta['historical_page_id_continuity'],'not_verified')
        self.assertIn(DATASET.encode(),html)
        self.assertIn(b'<details id="games-ru-table">',html)
        self.assertIn(b'Video game',html)
        self.assertIn('Кинематограф'.encode(),html)
        self.assertIn(b'href="#culture"',html)
        self.assertNotIn(b'<script',html)
        public=bundle_files()
        self.assertEqual(public['m1-cross-subject-20261025.json'],raw)
        self.assertEqual(public['m1-cross-subject-20261025.html'],html)
        self.assertEqual(json.loads(public['release-manifest.json'])['auxiliary_cross_subject_dataset'],meta)

    def test_fail_closed_on_one_modified_day_and_missing_evidence(self):
        original=json.loads(JSON_FILE.read_text())
        html=HTML_FILE.read_bytes()
        bad=copy.deepcopy(original)
        bad['series'][0]['daily_views'][0]+=1
        with self.assertRaisesRegex(ValueError,'metrics|HTML'):
            validate_assets(json.dumps(bad).encode(),html)
        with self.assertRaisesRegex(ValueError,'checksum'):
            validate_assets(JSON_FILE.read_bytes(),html.replace(
                b'ab81b8372fb51260d1c1a58a4d16d1b96568108afc411e17e626799d72d068ba',b'0'*64))
        bad=copy.deepcopy(original)
        bad['series'][2]['daily_views'][0]=None
        with self.assertRaisesRegex(ValueError,'invalid daily'):
            validate_assets(json.dumps(bad).encode(),html)

if __name__=='__main__':
    unittest.main()
