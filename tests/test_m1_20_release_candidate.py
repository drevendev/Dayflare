"""Regression acceptance for an unpublished Nov 18 release-format candidate."""
from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.m1_20_release_candidate import build
from tools.m1_20_retained_source import CANDIDATE_SHA256, SEED_SHA256
from tools.m1_publication_gate import PublicationError, SCHEMA, canonical
from tools.m1_pages_overlay import verified_m1_candidate


class RetainedReleaseCandidateTests(unittest.TestCase):
    def test_two_real_source_replays_identical_and_publishable_format(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            a, b = root / "a", root / "b"
            first = build(a)
            second = build(b)
            self.assertEqual(first, second)
            self.assertEqual(first["result"], "STAGED_NOT_DEPLOYED")
            self.assertIn("PUBLICATION_APPROVAL", first["decision"])
            self.assertEqual(first["candidate_sha256"], CANDIDATE_SHA256)
            self.assertEqual(first["observation_end"], "2026-11-18")
            self.assertEqual(first["retrieved_at"], "2026-11-21T14:43:17Z")
            self.assertEqual({x.name for x in a.iterdir()},
                             {"index.html", ".nojekyll", "release-manifest.json"})
            for filename in ("index.html", ".nojekyll", "release-manifest.json"):
                self.assertEqual((a / filename).read_bytes(), (b / filename).read_bytes())
            self.assertEqual((a / ".nojekyll").read_bytes(), b"")
            raw = (a / "release-manifest.json").read_bytes()
            manifest = json.loads(raw)
            self.assertEqual(raw, canonical(manifest))
            self.assertEqual(manifest["schema_version"], SCHEMA)
            self.assertEqual(manifest["status"], "DATED_ARCHIVE_NOT_LIVE")
            self.assertEqual(manifest["method_version"], "v0-empirical-35d")
            self.assertEqual(manifest["source_seed_sha256"], SEED_SHA256)
            self.assertEqual((manifest["series"], manifest["daily_observations"]), (20, 700))
            self.assertEqual(sha256(raw).hexdigest(), first["manifest_sha256"])
            self.assertEqual(
                verified_m1_candidate(
                    {p.name: p.read_bytes() for p in a.iterdir()},
                    CANDIDATE_SHA256, first["manifest_sha256"],
                ), manifest,
            )
            html = (a / "index.html").read_bytes()
            self.assertEqual(sha256(html).hexdigest(), first["html_sha256"])
            page = html.decode("utf-8")
            self.assertIn("Dayflare · dated attention atlas", page)
            self.assertIn("DATED SOURCE EVIDENCE", page)
            self.assertIn("not</strong> a live feed", page)
            # Embedded JS documents same-file behavior for offline previews;
            # only the actual visitor-facing local-only labels must disappear.
            self.assertNotIn("Dayflare · dated attention atlas (local preview)", page)
            self.assertNotIn("This is an offline preview", page)
            self.assertNotIn("SYNTHETIC TEST DATA", page)
            self.assertIn("2026-10-15", page)
            self.assertIn("2026-11-18", page)
            # Print / Save as PDF must retain dated evidence after public-copy
            # label changes, without claiming an actual Pages deployment.
            self.assertIn('@media print{@page{size:auto;margin:14mm}', page)
            self.assertIn('caption{background:#fff!important;color:#101820!important', page)
            self.assertIn('table{table-layout:fixed!important;width:100%!important;'
                          'min-width:0!important;', page)
            self.assertIn('For a paper or PDF evidence copy', page)
            self.assertIn('Dated source notes and visible exact tables remain included', page)
            self.assertIn('id="overview"', page)
            self.assertIn('id="pair-compare"', page)
            self.assertEqual(len(re.findall(
                r'<article id="detail-(?:en|ru)-wikipedia-[0-9]+"', page)), 20)
            self.assertEqual(page.count('class="daily-curve"'), 20)

    def test_existing_destination_keeps_all_bytes(self):
        with TemporaryDirectory() as name:
            dest = Path(name) / "release"
            dest.mkdir()
            marker = dest / "user.txt"
            marker.write_bytes(b"keep")
            with self.assertRaisesRegex(PublicationError, "new path"):
                build(dest)
            self.assertEqual(marker.read_bytes(), b"keep")
            self.assertEqual({p.name for p in dest.iterdir()}, {"user.txt"})

    def test_source_or_presentation_error_leaves_no_candidate(self):
        with TemporaryDirectory() as name:
            dest = Path(name) / "release"
            with patch("tools.m1_20_release_candidate.build_local",
                       side_effect=ValueError("source verifier rejected")):
                with self.assertRaisesRegex(ValueError, "source verifier"):
                    build(dest)
            self.assertFalse(dest.exists())
            with patch("tools.m1_20_release_candidate.public_copy",
                       side_effect=PublicationError("unreviewed UI")):
                with self.assertRaisesRegex(PublicationError, "unreviewed UI"):
                    build(dest)
            self.assertFalse(dest.exists())

    def test_previous_manifest_guard_and_no_clobber(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            original = root / "original"
            build(original)
            prior = original / "release-manifest.json"
            same = build(root / "same", prior)
            self.assertEqual(same["decision"], "UNCHANGED_ALREADY_CURRENT")
            old = json.loads(prior.read_text())
            old["observation_end"] = "2026-11-19"
            old["retrieved_at"] = "2026-11-21T15:43:17Z"
            newer = root / "newer.json"
            newer.write_bytes(canonical(old))
            refused = root / "refused"
            with self.assertRaisesRegex(PublicationError, "rollback"):
                build(refused, newer)
            self.assertFalse(refused.exists())


if __name__ == "__main__":
    unittest.main()
