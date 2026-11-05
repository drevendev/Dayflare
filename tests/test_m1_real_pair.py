"""No-network regressions for the retained real 4–5 Nov EN/RU identity pair."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from zipfile import ZipFile

from tools import m1_real_pair as m


class RealPairTests(unittest.TestCase):
    def test_real_pinned_ids_and_no_invented_lifecycle_changes(self):
        before, after, p, report, proof = m.load_pair()
        self.assertEqual(sha256(before).hexdigest(), p['baseline']['panel_sha256'])
        self.assertEqual(sha256(after).hexdigest(), m.PANEL_SHA256)
        self.assertEqual(proof['verified_pages'], 20)
        self.assertEqual(p['source']['run_id'], 41941385394)
        self.assertEqual(p['source']['artifact_id'], 13377025842)
        self.assertEqual(report['summary']['change_counts'], {'unchanged_observation': 20})
        self.assertEqual([x['observation_date_utc'] for x in report['inputs']],
                         ['2026-11-04', '2026-11-05'])
        self.assertEqual(len({(x['page_ref']['project'], x['page_ref']['page_id'])
                              for x in report['pages']}), 20)
        self.assertTrue(all(x['continuity'] == 'unverified_between_observations'
                            and not x['pageview_join_allowed'] for x in report['pages']))

    def test_deterministic_canonical_viewer_keyboard_and_nojs(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a', Path(tmp) / 'b'
            m.build(a)
            m.build(b)
            for name in ('history.json', 'index.html', 'manifest.json'):
                self.assertEqual((a / name).read_bytes(), (b / name).read_bytes())
            html = (a / 'index.html').read_text()
            self.assertIn('2026-11-04 → 2026-11-05 UTC', html)
            self.assertIn('REPORTED METADATA', html)
            self.assertIn('Skip to identity index', html)
            self.assertIn('No event supplied; this is not proof of no event.', html)
            self.assertNotIn('<script', html)
            self.assertNotIn('SYNTHETIC DEMONSTRATION', html)
            self.assertEqual(html.count('<article '), 20)
            with self.assertRaises(FileExistsError):
                m.build(a)
            self.assertTrue((a / 'manifest.json').is_file())

    def test_deterministic_offline_zip_matches_accepted_visitor_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, first, second = root / 'report', root / 'first.zip', root / 'second.zip'
            m.build(raw)
            m.build_archive(first)
            m.build_archive(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with ZipFile(first) as archive:
                self.assertEqual(archive.namelist(),
                                 ['index.html', 'history.json', 'manifest.json'])
                self.assertTrue(all(not item.is_dir() and item.compress_type == 8
                                    for item in archive.infolist()))
                for name in ('index.html', 'history.json', 'manifest.json'):
                    self.assertEqual(archive.read(name), (raw / name).read_bytes())
                self.assertNotIn(b'<script', archive.read('index.html'))
                self.assertIn(b'history.json', archive.read('index.html'))
            with self.assertRaises(FileExistsError):
                m.build_archive(first)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_invalid_later_evidence_cannot_publish_offline_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changed = root / 'changed'
            shutil.copytree(m.AFTER, changed)
            (changed / 'source-delta.json').write_bytes(b'not the approved delta')
            destination = root / 'blocked.zip'
            with self.assertRaisesRegex(ValueError, 'Unreviewed later metadata delta'):
                m.build_archive(destination, changed)
            self.assertFalse(destination.exists())

    def test_tamper_rejected_without_completed_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changed = root / 'tampered'
            shutil.copytree(m.AFTER, changed)
            f = changed / 'source-delta.json'
            f.write_bytes(f.read_bytes() + b'corrupt')
            with self.assertRaisesRegex(ValueError, 'Unreviewed later metadata delta'):
                m.build(root / 'bad', changed)
            self.assertFalse((root / 'bad').exists())
            other = root / 'provenance-changed'
            shutil.copytree(m.AFTER, other)
            f = other / 'provenance.json'
            p = json.loads(f.read_text())
            p['observation_date_utc'] = '2026-11-04'
            f.write_text(json.dumps(p))
            with self.assertRaisesRegex(ValueError, 'Unreviewed later provenance'):
                m.build(root / 'bad2', other)
            self.assertFalse((root / 'bad2').exists())


if __name__ == '__main__':
    unittest.main()
