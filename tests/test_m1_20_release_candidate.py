"""Regression acceptance for an unpublished Nov 18 release-format candidate."""
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.m1_20_release_candidate import build, main, verify_existing
from tools.m1_20_retained_source import CANDIDATE_SHA256, SEED_SHA256
from tools.m1_publication_gate import PublicationError, SCHEMA, canonical
from tools.m1_pages_overlay import verified_m1_candidate


class RetainedReleaseCandidateTests(unittest.TestCase):
    def test_existing_release_audit_requires_external_pin_and_never_rebuilds(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            dest = root / "accepted-candidate"
            staged = build(dest)
            manifest = (dest / "release-manifest.json").read_bytes()
            html = (dest / "index.html").read_bytes()
            pin = sha256(manifest).hexdigest()
            with patch("tools.m1_20_release_candidate.build_local",
                       side_effect=AssertionError("audit must never rebuild")):
                proof = verify_existing(dest, pin)
                self.assertEqual(proof["result"], "VERIFIED_NOT_APPROVED_NOT_DEPLOYED")
                self.assertEqual(proof["manifest_sha256"], staged["manifest_sha256"])
                self.assertEqual(proof["html_sha256"], staged["html_sha256"])
                self.assertEqual(proof["observation_end"], "2026-11-18")
                with io.StringIO() as out, redirect_stdout(out):
                    self.assertEqual(main([str(dest), "--verify-manifest-sha256", pin]), 0)
                    self.assertEqual(json.loads(out.getvalue()), proof)
            self.assertEqual((dest / "release-manifest.json").read_bytes(), manifest)
            self.assertEqual((dest / "index.html").read_bytes(), html)

    def test_existing_release_audit_fails_closed_on_tampering_or_linked_paths(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            dest = root / "candidate"
            build(dest)
            manifest_path = dest / "release-manifest.json"
            html_path = dest / "index.html"
            manifest = manifest_path.read_bytes()
            html = html_path.read_bytes()
            pin = sha256(manifest).hexdigest()
            for invalid in ("not-a-digest", "0" * 64):
                with self.subTest(pin=invalid):
                    with self.assertRaises(PublicationError):
                        verify_existing(dest, invalid)

            with io.StringIO() as err, redirect_stderr(err):
                self.assertEqual(main([str(dest), "--verify-manifest-sha256", pin,
                                       "--previous-manifest", str(manifest_path)]), 2)
                self.assertIn("only for staging", err.getvalue())

            extra = dest / "untrusted.txt"
            extra.write_bytes(b"unapproved")
            with self.assertRaisesRegex(PublicationError, "inventory"):
                verify_existing(dest, pin)
            extra.unlink()

            marker = dest / ".nojekyll"
            marker.unlink()
            with self.assertRaisesRegex(PublicationError, "inventory"):
                verify_existing(dest, pin)
            marker.write_bytes(b"")

            html_path.write_bytes(b"altered HTML")
            with self.assertRaises(PublicationError):
                verify_existing(dest, pin)
            html_path.write_bytes(html)

            manifest_path.write_bytes(b'{"status":"fake"}')
            with self.assertRaises(PublicationError):
                verify_existing(dest, pin)
            manifest_path.write_bytes(manifest)

            outside = root / "outside.html"
            outside.write_bytes(html)
            html_path.unlink()
            html_path.symlink_to(outside)
            with self.assertRaisesRegex(PublicationError, "linked"):
                verify_existing(dest, pin)
            html_path.unlink()
            html_path.write_bytes(html)

            linked = root / "hardlink.html"
            os.link(html_path, linked)
            with self.assertRaisesRegex(PublicationError, "linked"):
                verify_existing(dest, pin)
            linked.unlink()

            alias = root / "alias"
            alias.symlink_to(dest, target_is_directory=True)
            with self.assertRaisesRegex(PublicationError, "non-symlink"):
                verify_existing(alias, pin)

            self.assertEqual(verify_existing(dest, pin)["manifest_sha256"], pin)
            self.assertEqual(html_path.read_bytes(), html)
            self.assertEqual(manifest_path.read_bytes(), manifest)

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
            self.assertIn("Complete selected atlas: all 20 selected title histories "
                          "and exact weekly comparisons are included in this printout",
                          page)
            self.assertIn(".cards>.card[hidden]{display:block!important}", page)
            self.assertIn("#compare-table tbody tr[hidden]{display:table-row!important}",
                          page)
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
