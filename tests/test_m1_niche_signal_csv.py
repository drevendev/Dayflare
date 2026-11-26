"""Real retained 19-title CSV and fail-closed regression."""
import csv
from fractions import Fraction
from io import StringIO
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from tools.m1_niche_replay import NAMES, PARTS
from tools.m1_niche_signal_csv import export


class NicheSignalTests(unittest.TestCase):
    def test_exact_source_signals(self):
        with TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a.csv', Path(tmp) / 'b.csv'
            first = export(a)
            self.assertEqual(first, export(b))
            self.assertEqual(a.read_bytes(), first)
            rows = list(csv.DictReader(StringIO(first.decode('utf-8'))))
            self.assertEqual(len(rows), 19)
            self.assertEqual(len({r['project_page_id'] for r in rows}), 19)
            self.assertEqual(sum(int(r['opposite_nonzero_signs']) for r in rows), 4)
            for row in rows:
                weeks = [int(row[f'week{i}']) for i in range(1, 6)]
                ordered = sorted(weeks[:4])
                base = Fraction(ordered[1] + ordered[2], 2)
                self.assertEqual(Fraction(row['prior4_median']), base)
                self.assertEqual(Fraction(row['median_delta']), weeks[-1] - base)
                self.assertEqual(int(row['adjacent_week_step']), weeks[-1] - weeks[-2])
                self.assertEqual(row['observation_start'], '2026-10-20')
                self.assertEqual(row['observation_end'], '2026-11-23')
                self.assertEqual(row['retrieved_at'], '2026-11-26T05:24:57Z')
                self.assertEqual(row['candidate_sha256'],
                                 '10f78c6ab626a6ff2845b4db3e2e207144389ed387f88e22d31f4eeeeaaa905e')
                if base:
                    self.assertEqual(Fraction(int(row['relative_lift_numerator']),
                                              int(row['relative_lift_denominator'])),
                                     (weeks[-1] - base) / base)
                else:
                    self.assertEqual(row['relative_lift_numerator'], '')
                    self.assertEqual(row['relative_lift_denominator'], '')
            games = {r['title']: r for r in rows
                     if r['project_page_id'].startswith('en.wikipedia:')}
            for title, expected in (
                    ('NetHack', [1393, 1411, 1228, 1586, 1344]),
                    ('OpenTTD', [983, 878, 797, 793, 739])):
                row = games[title]
                self.assertEqual([int(row[f'week{i}']) for i in range(1, 6)], expected)
            with self.assertRaises(ValueError):
                export(a)
            self.assertEqual(a.read_bytes(), first)

    def test_tampered_archive_creates_no_output(self):
        with TemporaryDirectory() as tmp:
            parts = Path(tmp) / 'parts'
            shutil.copytree(PARTS, parts)
            part = parts / NAMES[0]
            raw = part.read_bytes()
            part.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            destination = Path(tmp) / 'bad.csv'
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                export(destination, parts)
            self.assertFalse(destination.exists())
