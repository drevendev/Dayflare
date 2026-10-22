"""Regression checks for the derived no-JS evidence projection."""
from pathlib import Path
import re
import tempfile
import unittest

from tools import build_nojs


class NoJsSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = build_nojs.PAGE.read_text(encoding="utf-8")
        cls.series = build_nojs.verified_series()
        cls.block = cls.html.split(build_nojs.START_MARKER)[1].split(build_nojs.END_MARKER)[0]

    def test_rendered_archive_is_exactly_current(self):
        self.assertEqual(build_nojs.updated_page(self.html, build_nojs.render(self.series)), self.html)

    def test_210_source_values_six_real_series_all_dated(self):
        self.assertEqual(len(self.series), 6)
        self.assertEqual(self.block.count('<details class="nojs-topic">'), 6)
        self.assertEqual(len(re.findall(r'<tr><th scope="row">2026-\d\d-\d\d</th><td>', self.block)), 210)
        self.assertEqual(sum(len(s['rows']) for s in self.series), 210)
        self.assertIn('Chess · English', self.block)
        self.assertIn('19,804 views; baseline: 18,369.5', self.block)
        self.assertIn('+7.8%', self.block)
        self.assertIn('Мастер и Маргарита', self.block)
        self.assertEqual(self.block.count('<th scope="col">Date (UTC)</th>'), 6)
        self.assertEqual(self.block.count('<th scope="row">2026-'), 210)

    def test_unverified_data_never_survives_corrupt_archive(self):
        raw = build_nojs.ARCHIVE.read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'corrupt.zip'
            file.write_bytes(raw[:-1] + bytes([raw[-1] ^ 0x01]))
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                build_nojs.verified_series(file)

    def test_summary_evidence_honestly_bounded(self):
        for term in ('not live or representative', 'page requests', 'not a validated trend label',
                     '11 August–14 September 2026', '18 October 2026'):
            self.assertIn(term, self.block)
        self.assertIn('evidence/d02-20261018/provenance.json', self.block)
        self.assertIn('href="https://ru.wikipedia.org/wiki/', self.block)
        self.assertNotIn('data:text/html', self.block)

    def test_generated_snapshot_no_duplicate_copy(self):
        self.assertEqual(self.html.count(build_nojs.START_MARKER), 1)
        self.assertEqual(self.html.count(build_nojs.END_MARKER), 1)
        self.assertIn('<noscript>', self.block)
        self.assertNotIn('<script', self.block)
        self.assertNotIn('<img', self.block)
        self.assertIn('<a class="skip" href="#discover">', self.html)
        self.assertIn('nojs-topic summary:focus-visible', (build_nojs.ROOT / 'site/styles.css').read_text())


if __name__ == '__main__':
    unittest.main()
