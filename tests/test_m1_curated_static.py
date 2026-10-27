"""Curated 20-series visitor data must fail closed on source or visible tampering."""
import copy
import json
from pathlib import Path
import unittest

from tools.m1_curated_static import validate_assets

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class CuratedStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = (SITE / "m1-curated-20261023.json").read_bytes()
        cls.html = (SITE / "m1-curated-20261023.html").read_bytes()
        cls.observed = (SITE / "identities-m1-20261024.json").read_bytes()

    def test_exact_source_bound_series_are_visible_and_complete(self):
        outcome = validate_assets(self.data, self.html, self.observed)
        self.assertEqual(outcome["measured_series"], 20)
        self.assertEqual(outcome["daily_observations"], 700)
        self.assertFalse(outcome["historical_page_id_continuity"])
        self.assertEqual(self.html.count(b'<article class="topic"'), 20)
        self.assertEqual(self.html.count(b'<tr><th scope="row">'), 700)
        self.assertIn(b'<nav class="pill-links"', self.html)
        self.assertIn(b'data-curated-explorer hidden', self.html)
        self.assertIn(b'<script src="curated-explorer.js" defer></script>', self.html)
        for required in (b'id="curated-query"', b'id="curated-subject"',
                         b'id="curated-edition"', b'id="curated-count"',
                         b'id="curated-share"', b'id="curated-reset"',
                         b'id="curated-empty"', b'id="curated-incompatible"'):
            self.assertIn(required, self.html)
        self.assertIn(b'.curated-compare-scroll', self.html)
        self.assertIn(b'.curated-compare-fields', self.html)
        self.assertIn(b'prefers-reduced-motion:reduce', self.html)
        self.assertIn(b':focus-visible', self.html)

    def assert_rejected_data(self, mutate):
        src = json.loads(self.data)
        mutate(src)
        with self.assertRaises(ValueError):
            validate_assets(json.dumps(src, ensure_ascii=False, allow_nan=False).encode(),
                            self.html, self.observed)

    def test_source_daily_value_mutation_is_rejected(self):
        self.assert_rejected_data(lambda x: x["series"][0]["daily_views"].__setitem__(0, 999_999))
        self.assert_rejected_data(lambda x: x["series"][0]["daily_views"].__setitem__(0, None))

    def test_source_metrics_or_identity_mutations_are_rejected(self):
        self.assert_rejected_data(lambda x: x["series"][0]["computed"].__setitem__("latest", 1))
        self.assert_rejected_data(lambda x: x["series"][0].__setitem__("title", "Another title"))
        self.assert_rejected_data(lambda x: x["series"][0].__setitem__("observed_page_id", 9))
        self.assert_rejected_data(lambda x: x["series"][0].__setitem__("raw_response_sha256", "0"*64))
        self.assert_rejected_data(lambda x: x.__setitem__("cross_edition_equivalence", "CONFIRMED"))
        self.assert_rejected_data(lambda x: x.__setitem__("retrieved_at_utc", "2026-10-27T00:00:00Z"))

    def test_duplicate_json_key_is_rejected(self):
        altered = self.data.replace(b'"schema":', b'"schema":"wrong","schema":', 1)
        self.assertNotEqual(altered, self.data)
        with self.assertRaises(ValueError):
            validate_assets(altered, self.html, self.observed)

    def test_html_number_and_source_tamper_is_rejected(self):
        for old, new in [
            (b'data-latest="37759"', b'data-latest="37760"'),
            (b'>37,759</strong>', b'>37,999</strong>'),
            (b'>37,759</span>', b'>37,999</span>'),
            (b'>2026-09-19</th>', b'>2026-09-18</th>'),
            (b'original-not-present', b'different'),
            (b'>Basketball</h3>', b'>Basket</h3>'),
        ]:
            if old == b'original-not-present':
                continue
            changed = self.html.replace(old, new, 1)
            self.assertNotEqual(changed, self.html, old)
            with self.subTest(old=old), self.assertRaises(ValueError):
                validate_assets(self.data, changed, self.observed)

    def test_weekly_bar_geometry_tampering_is_rejected(self):
        original = b'<span class="week-fill" style="width:49%"></span>'
        self.assertIn(original, self.html)
        for modified in (
            b'<span class="week-fill" style="width:99%"></span>',
            b'<span class="week-fill" style="width:49.5%"></span>',
            b'<span class="week-fill" style="width:049%"></span>',
            b'',
        ):
            with self.subTest(modified=modified):
                tampered = self.html.replace(original, modified, 1)
                self.assertNotEqual(tampered, self.html)
                with self.assertRaises(ValueError):
                    validate_assets(self.data, tampered, self.observed)

    def test_missing_or_wrong_observed_context_rejected(self):
        observed = json.loads(self.observed)
        observed["pages"][0]["title"] = "Unverified renamed title"
        with self.assertRaises(ValueError):
            validate_assets(self.data, self.html, json.dumps(observed).encode())


if __name__ == "__main__":
    unittest.main()
