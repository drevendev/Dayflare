"""Real-source offline regression: Nov 18 retained HTML must be usable and pinned."""
from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.m1_20_local_atlas import (
    CANDIDATE_SHA256, OBSERVATION_END, PROVENANCE, RETRIEVED_AT, build,
)


class LocalAtlasTests(unittest.TestCase):
    def test_real_source_build_is_deterministic_and_useful_without_scripts(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first"
            second = root / "second"
            a, b = build(first), build(second)
            self.assertEqual(a, b)
            self.assertEqual(a["schema_version"], "dayflare.local-rolling-preview.v1")
            self.assertEqual(a["candidate_sha256"], CANDIDATE_SHA256)
            self.assertEqual(a["observation_end"], OBSERVATION_END)
            self.assertEqual(a["retrieved_at"], RETRIEVED_AT)
            self.assertEqual(a["provenance_status"], PROVENANCE)
            self.assertEqual(a["publication_status"], "LOCAL_PREVIEW_NOT_PUBLISHED")
            self.assertEqual(a["series"], 20)
            self.assertEqual({p.name for p in first.iterdir()},
                             {"index.html", "preview-manifest.json"})
            html = (first / "index.html").read_bytes()
            self.assertEqual(html, (second / "index.html").read_bytes())
            self.assertEqual(sha256(html).hexdigest(), a["html_sha256"])
            self.assertEqual(json.loads((first / "preview-manifest.json").read_text()), a)
            page = html.decode("utf-8")
            self.assertIn("Where did attention change?", page)
            self.assertIn("2026-10-15", page)
            self.assertIn(OBSERVATION_END, page)
            self.assertIn(RETRIEVED_AT, page)
            self.assertIn("offline preview", page)
            self.assertIn('id="overview"', page)
            self.assertIn('id="pair-compare"', page)
            self.assertIn('id="compare-table"', page)
            self.assertIn('id="atlas-method"', page)
            self.assertEqual(len(re.findall(r'<article id="detail-(?:en|ru)-wikipedia-[0-9]+"', page)), 20)
            self.assertEqual(page.count('class="daily-curve"'), 20)
            self.assertIn("https://wikimedia.org/api/rest_v1/metrics/pageviews/", page)
            self.assertIn("not</strong> a public release", page)

    def test_existing_destination_is_not_replaced(self):
        with TemporaryDirectory() as temp:
            dest = Path(temp) / "atlas"
            dest.mkdir()
            marker = dest / "mine.txt"
            marker.write_text("preserve")
            with self.assertRaisesRegex(ValueError, "new path"):
                build(dest)
            self.assertEqual(marker.read_text(), "preserve")
            self.assertEqual([p.name for p in dest.iterdir()], ["mine.txt"])

    def test_failed_source_verification_does_not_publish_partial_preview(self):
        with TemporaryDirectory() as temp:
            dest = Path(temp) / "atlas"
            with patch("tools.m1_20_local_atlas.unpack", side_effect=ValueError("pin mismatch")):
                with self.assertRaisesRegex(ValueError, "pin mismatch"):
                    build(dest)
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
