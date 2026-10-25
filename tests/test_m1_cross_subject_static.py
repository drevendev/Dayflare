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


    def test_display_only_corruption_fails_closed(self):
        # The underlying JSON and data-* metrics remain untouched in each
        # mutation. What visitors read must itself be authenticated by the
        # source-to-static verifier before a release can be built.
        data=JSON_FILE.read_bytes()
        html=HTML_FILE.read_bytes()
        mutations=[
            (b'<strong>387</strong>', b'<strong>999</strong>'),  # bar total
            ('<span>11–17 Aug</span>'.encode(), '<span>13–17 Aug</span>'.encode()),
            (b'style="width:93.3%"', b'style="width:1.0%"'),
            (b'<strong class="metric">392</strong>', b'<strong class="metric">999</strong>'),
            (b'<strong class="up">+1.16%</strong>', b'<strong class="up">+999.99%</strong>'),
            (b'<span>vs four-week median 387.5</span>',
             b'<span>vs four-week median 999</span>'),
            (b'+4.5 requests vs baseline', b'+999 requests vs baseline'),
            (b'<th scope="row">2026-08-11</th>',
             b'<th scope="row">2026-08-99</th>'),
            (b'<th scope="row">2026-08-11</th>', b'<th scope="row"></th>'),
            (b'<td>56</td>', b'<td>0,56</td>'),  # invalid grouping; commas stripped would hide it
            (b'<strong class="up">+1.16%</strong>', b''),
        ]
        for before,after in mutations:
            with self.subTest(before=before,after=after):
                self.assertIn(before,html)
                altered=html.replace(before,after,1)
                self.assertNotEqual(altered,html)
                with self.assertRaisesRegex(ValueError,'HTML|Visitor-visible'):
                    validate_assets(data,altered)

if __name__=='__main__':
    unittest.main()
