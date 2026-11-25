import csv
from fractions import Fraction
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.m1_30_signal_csv import export, render_csv, signals

ROOT = Path(__file__).resolve().parents[1]
CAPSULE = ROOT / 'evidence/m1-30-20261124-source.xz.b64'
CAPSULE_PIN = '10d7fa4ed4b7c2bdab98d3c7d4c64a70d12b27aa15df5d4fd67f16194b93c543'
ORIGINAL_PIN = '1721869d687dd5f1b08b9ba9dcd963f8477299151f7f1c5f24090222c14fc305'


class SignalTests(unittest.TestCase):
    def test_distinct_signs(self):
        self.assertEqual(signals([20, 21, 22, 10, 15]),
                         (Fraction(41, 2), Fraction(-11, 2), Fraction(-11, 41), 5, True))
        self.assertFalse(signals([10, 10, 10, 5, 10])[-1])

    def test_zero_and_tiny_baseline(self):
        self.assertEqual(signals([0, 0, 0, 0, 2]), (0, 2, None, 2, False))
        self.assertEqual(signals([1, 1, 1, 1, 10])[2], 9)

    def test_invalid(self):
        for weekly in ([1]*4, [1, 2, 3, 4, True], [1, 2, 3, 4, -1]):
            with self.assertRaises(ValueError):
                signals(weekly)
        with self.assertRaises(ValueError):
            render_csv({}, {'provenance_status': 'synthetic_injected_not_upstream_evidence'})

    def test_retained_source(self):
        with TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a.csv', Path(tmp)/'b.csv'
            first = export(CAPSULE, a, CAPSULE_PIN, ORIGINAL_PIN)
            self.assertEqual(first, export(CAPSULE, b, CAPSULE_PIN, ORIGINAL_PIN))
            self.assertEqual(a.read_bytes(), first)
            rows = list(csv.DictReader(StringIO(first.decode('utf-8'))))
            self.assertEqual(len(rows), 30)
            self.assertEqual(sum(int(r['opposite_nonzero_signs']) for r in rows), 7)
            for r in rows:
                weeks = [int(r[f'week{i}']) for i in range(1, 6)]
                base = Fraction(r['prior4_median'])
                delta = Fraction(r['median_delta'])
                self.assertEqual(delta, weeks[-1] - base)
                self.assertEqual(int(r['adjacent_week_step']), weeks[-1] - weeks[-2])
                self.assertEqual(Fraction(int(r['relative_lift_numerator']),
                                          int(r['relative_lift_denominator'])), delta / base)
            with self.assertRaises(FileExistsError):
                export(CAPSULE, a, CAPSULE_PIN, ORIGINAL_PIN)
            rejected = Path(tmp)/'bad.csv'
            with self.assertRaises(ValueError):
                export(CAPSULE, rejected, '0'*64, ORIGINAL_PIN)
            self.assertFalse(rejected.exists())
