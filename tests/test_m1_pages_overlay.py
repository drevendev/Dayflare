"""Synthetic-only overlay unit tests; no Pages deployment or Wikimedia claim."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.m1_publication_gate import PublicationError, SCHEMA, canonical
from tools.m1_pages_overlay import (
    APPROVED_RELEASE_METADATA_BLOBS, git_blob_sha1, inventory, sha, stage_overlay,
    verified_m0_root,
)


def m1_manifest(end="2026-10-25", retrieved="2026-10-28T15:33:50Z", c="a" * 64,
                html=b"M1 synthetic HTML", seed="c" * 64) -> dict:
    return {"schema_version": SCHEMA, "status": "DATED_ARCHIVE_NOT_LIVE",
            "dataset_id": "synthetic-" + end + "-" + retrieved,
            "method_version": "v0-empirical-35d", "observation_end": end,
            "retrieved_at": retrieved, "candidate_sha256": c,
            "html_sha256": sha(html), "source_receipt_sha256": "b" * 64,
            "source_seed_sha256": seed, "series": 20,
            "daily_observations": 700}


def write_m0(root: Path) -> None:
    (root / "evidence").mkdir(parents=True)
    files = {"index.html": b"M0 validated static site", ".nojekyll": b"",
             "styles.css": b"M0 style", "evidence/source.txt": b"M0 evidence"}
    for name, data in files.items():
        (root / name).write_bytes(data)
    (root / "release-manifest.json").write_text(json.dumps({
        "status": "UNPUBLISHED_STATIC_RELEASE_CANDIDATE",
        "files_sha256": {n: sha(d) for n, d in files.items()}}), encoding="utf-8")


def write_m1(root: Path, **kwargs) -> tuple[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    html = b"M1 synthetic HTML" + kwargs.pop("suffix", b"")
    manifest = m1_manifest(html=html, **kwargs)
    (root / "index.html").write_bytes(html)
    (root / ".nojekyll").write_bytes(b"")
    raw = canonical(manifest)
    (root / "release-manifest.json").write_bytes(raw)
    return manifest["candidate_sha256"], sha(raw)


class M1PagesOverlayTests(unittest.TestCase):
    def setUp(self):
        self.context = tempfile.TemporaryDirectory()
        self.addCleanup(self.context.cleanup)
        self.base = Path(self.context.name)
        self.m0 = self.base / "accepted-gh-pages"
        self.m0.mkdir()
        write_m0(self.m0)
        self.candidate = self.base / "gated-m1"
        self.pin, self.manifest_pin = write_m1(self.candidate)
        self.dest = self.base / "new-unpublished-tree"

    def stage(self, **kw):
        return stage_overlay(kw.get("root", self.m0), kw.get("candidate", self.candidate),
                             kw.get("dest", self.dest), kw.get("pin", self.pin),
                             kw.get("manifest_pin", self.manifest_pin))

    def test_first_additive_stage_preserves_every_m0_byte_and_no_public_claim(self):
        original = inventory(self.m0)
        result = self.stage()
        self.assertEqual(result["status"], "STAGED_NOT_DEPLOYED")
        self.assertIn("REQUIRES_SEPARATE", result["decision"])
        self.assertEqual({k: v for k, v in inventory(self.dest).items()
                          if not k.startswith("m1/")}, original)
        self.assertEqual((self.dest / "m1/index.html").read_bytes(),
                         (self.candidate / "index.html").read_bytes())
        self.assertEqual(inventory(self.m0), original)
        self.assertEqual(set((self.dest / "m1").iterdir()),
                         {self.dest / "m1/index.html", self.dest / "m1/.nojekyll",
                          self.dest / "m1/release-manifest.json"})

    def test_pinned_release_workflow_metadata_is_preserved_as_non_m0(self):
        path = ".github/workflows/m1-release-candidate.yml"
        data = b"name: synthetic read-only release acceptance\n"
        workflow = self.m0 / path
        workflow.parent.mkdir(parents=True)
        workflow.write_bytes(data)
        with patch.dict(APPROVED_RELEASE_METADATA_BLOBS,
                        {path: frozenset({git_blob_sha1(data)})}, clear=True):
            original = inventory(self.m0)
            self.stage()
            output = inventory(self.dest)
            self.assertEqual(output[path], data)
            self.assertEqual({k: v for k, v in output.items()
                              if not k.startswith("m1/")}, original)
            self.assertEqual(inventory(self.m0), original)

    def test_transition_accepts_only_five_exact_reviewed_metadata_blobs(self):
        path = ".github/workflows/m1-release-candidate.yml"
        first = b"name: reviewed read-only acceptance v1\\n"
        second = b"name: reviewed read-only acceptance v2\\n"
        third = b"name: reviewed read-only acceptance v3\\n"
        fourth = b"name: reviewed read-only acceptance v4\\n"
        fifth = b"name: reviewed read-only acceptance v5\\n"
        workflow = self.m0 / path
        workflow.parent.mkdir(parents=True)
        with patch.dict(APPROVED_RELEASE_METADATA_BLOBS,
                        {path: frozenset({git_blob_sha1(first), git_blob_sha1(second),
                                          git_blob_sha1(third), git_blob_sha1(fourth),
                                          git_blob_sha1(fifth)})},
                        clear=True):
            for accepted in (first, second, third, fourth, fifth):
                workflow.write_bytes(accepted)
                verified_m0_root(inventory(self.m0))
            workflow.write_bytes(second + b"# unreviewed mutation\\n")
            with self.assertRaisesRegex(PublicationError, "metadata digest mismatch"):
                verified_m0_root(inventory(self.m0))

    def test_release_100_relative_sort_and_20261101_age_pins_are_bounded(self):
        path = ".github/workflows/m1-release-candidate.yml"
        reviewed = APPROVED_RELEASE_METADATA_BLOBS[path]
        self.assertEqual(len(reviewed), 8)
        self.assertIn("68bc227fb8eb3585cc5df301a74610ea57e4e84d", reviewed)
        self.assertIn("f20477903f865c37a1a656b526a1872e0f3f35e3", reviewed)
        self.assertIn("7c84b1b928e965457470cbb793292e2f176890cf", reviewed)
        self.assertIn("a51e2fdfcba85c29e5a9d1c5c48608e484426294", reviewed)
        self.assertIn("d674555c610c9c29498d3656b8365672ff7978d4", reviewed)
        self.assertEqual(len(reviewed), len(set(reviewed)))

    def test_changed_or_unapproved_release_workflow_fails_closed(self):
        path = ".github/workflows/m1-release-candidate.yml"
        data = b"name: synthetic read-only release acceptance\n"
        workflow = self.m0 / path
        workflow.parent.mkdir(parents=True)
        workflow.write_bytes(data)
        with patch.dict(APPROVED_RELEASE_METADATA_BLOBS,
                        {path: frozenset({git_blob_sha1(data)})}, clear=True):
            workflow.write_bytes(data + b"# mutation\n")
            with self.assertRaisesRegex(PublicationError, "metadata digest mismatch"):
                self.stage()
            self.assertFalse(self.dest.exists())

            workflow.write_bytes(data)
            extra = self.m0 / ".github/workflows/unapproved.yml"
            extra.write_bytes(b"name: unreviewed workflow\n")
            with self.assertRaisesRegex(PublicationError, "M0 manifest/inventory mismatch"):
                self.stage()
            self.assertFalse(self.dest.exists())

            extra.unlink()
            (self.m0 / "styles.css").write_bytes(b"tampered M0")
            with self.assertRaisesRegex(PublicationError, "M0 asset changed"):
                self.stage()
            self.assertFalse(self.dest.exists())

    def test_staging_refuses_existing_target_without_modifying_inputs(self):
        self.dest.mkdir()
        marker = self.dest / "sentinel"
        marker.write_bytes(b"keep")
        with self.assertRaisesRegex(PublicationError, "overwrite"):
            self.stage()
        self.assertEqual(marker.read_bytes(), b"keep")

    def test_independent_pin_and_exact_html_required(self):
        for wrong in (dict(pin="0" * 64), dict(manifest_pin="0" * 64)):
            with self.subTest(wrong=wrong), self.assertRaises(PublicationError):
                self.stage(**wrong)
            self.assertFalse(self.dest.exists())
        (self.candidate / "index.html").write_bytes(b"altered")
        with self.assertRaisesRegex(PublicationError, "digest mismatch"):
            self.stage()
        self.assertFalse(self.dest.exists())

    def test_corrupt_m0_is_not_replaced(self):
        (self.m0 / "styles.css").write_bytes(b"corrupted")
        with self.assertRaisesRegex(PublicationError, "M0 asset changed"):
            self.stage()
        self.assertFalse(self.dest.exists())

    def test_input_links_extra_candidate_and_malformed_manifest_refused(self):
        (self.candidate / "extra.js").write_bytes(b"extra")
        with self.assertRaisesRegex(PublicationError, "candidate inventory"):
            self.stage()
        (self.candidate / "extra.js").unlink()
        (self.m0 / "linked.txt").symlink_to(self.m0 / "index.html")
        with self.assertRaisesRegex(PublicationError, "linked"):
            self.stage()
        (self.m0 / "linked.txt").unlink()
        (self.candidate / "release-manifest.json").write_text('{"x":1,"x":2}')
        with self.assertRaisesRegex(PublicationError, "accepted pin"):
            self.stage()
        self.assertFalse(self.dest.exists())

    def test_m1_manifest_dates_must_be_canonical_and_temporally_possible(self):
        original_m0 = inventory(self.m0)
        for observation, retrieval in (
            ("2026-10-25", "2026-10-25T23:59:59Z"),  # observation still in progress
            ("2026-10-25", "2026-10-24T00:00:00Z"),  # retrieval predates data
            ("20261025", "2026-10-28T15:33:50Z"),   # alternate date syntax
            ("2026-W43-7", "2026-10-28T15:33:50Z"), # ISO week date
            ("2026-10-25", "2026-10-28T15:33:50+00:00"),  # noncanonical UTC
            ("2026-10-25", "2026-10-28T15:33:50.000Z"),   # subsecond precision
            ("2026-10-25", "2026-10-28T17:33:50+02:00"),  # timezone offset
            ("2026-02-30", "2026-10-28T15:33:50Z"),  # impossible date
            ("9999-12-31", "9999-12-31T23:59:59Z"),  # max-year overflow guard
        ):
            with self.subTest(observation=observation, retrieval=retrieval):
                raw = canonical(m1_manifest(end=observation, retrieved=retrieval))
                (self.candidate / "release-manifest.json").write_bytes(raw)
                # Even a matching caller-provided manifest pin is insufficient:
                # invalid dates must fail before the output stage is created.
                with self.assertRaisesRegex(PublicationError, "invalid M1 observation/retrieval date"):
                    self.stage(manifest_pin=sha(raw))
                self.assertFalse(self.dest.exists())
                self.assertEqual(inventory(self.m0), original_m0)

    def test_retrieval_at_first_utc_midnight_after_observation_is_valid(self):
        raw = canonical(m1_manifest(retrieved="2026-10-26T00:00:00Z"))
        (self.candidate / "release-manifest.json").write_bytes(raw)
        result = self.stage(manifest_pin=sha(raw))
        self.assertEqual(result["status"], "STAGED_NOT_DEPLOYED")

    def test_monotonic_m1_refresh_preserves_m0_and_rejects_rollback(self):
        self.stage()
        prior = self.dest
        nextdir = self.base / "new-candidate"
        new_pin, new_manifest_pin = write_m1(nextdir, end="2026-11-01",
                                             retrieved="2026-11-04T15:33:50Z",
                                             c="d" * 64, suffix=b" updated")
        output = self.base / "future-tree"
        result = stage_overlay(prior, nextdir, output, new_pin, new_manifest_pin)
        self.assertIn("NEWER_CANDIDATE", result["decision"])
        self.assertEqual((output / "index.html").read_bytes(),
                         (self.m0 / "index.html").read_bytes())
        self.assertEqual((output / "m1/index.html").read_bytes(),
                         (nextdir / "index.html").read_bytes())
        with self.assertRaisesRegex(PublicationError, "rollback"):
            stage_overlay(output, self.candidate, self.base / "rollback", self.pin,
                          self.manifest_pin)
        with self.assertRaisesRegex(PublicationError, "unchanged"):
            stage_overlay(output, nextdir, self.base / "duplicate", new_pin,
                          new_manifest_pin)
        self.assertEqual((prior / "m1/index.html").read_bytes(),
                         (self.candidate / "index.html").read_bytes())

    def test_newer_reselected_seed_rejected_before_staging_and_preserves_previous_tree(self):
        self.stage()
        previous_bytes = inventory(self.dest)
        newer = self.base / "unreviewed-cohort"
        pin, manifest_pin = write_m1(newer, end="2026-11-01",
                                     retrieved="2026-11-04T15:33:50Z",
                                     c="d" * 64, seed="f" * 64,
                                     suffix=b" other cohort")
        rejected = self.base / "rejected-cohort"
        with self.assertRaisesRegex(PublicationError, "curated source seed changed"):
            stage_overlay(self.dest, newer, rejected, pin, manifest_pin)
        self.assertFalse(rejected.exists())
        self.assertEqual(inventory(self.dest), previous_bytes)

    def test_previous_m1_tampering_is_rejected(self):
        self.stage()
        (self.dest / "m1/index.html").write_bytes(b"changed")
        new_dir = self.base / "later"
        pin, receipt = write_m1(new_dir, end="2026-11-01",
                                retrieved="2026-11-04T15:33:50Z", c="d" * 64)
        with self.assertRaisesRegex(PublicationError, "HTML digest mismatch"):
            stage_overlay(self.dest, new_dir, self.base / "tampered-output", pin, receipt)


    def test_first_screen_release_workflow_is_byte_pinned_without_dropping_older_pins(self):
        approved = APPROVED_RELEASE_METADATA_BLOBS[
            ".github/workflows/m1-release-candidate.yml"]
        self.assertIn("d09acd822e61d5ee4f5407f109409ecc7ec93e1f", approved)
        self.assertIn("a51e2fdfcba85c29e5a9d1c5c48608e484426294", approved)
        self.assertEqual(len(approved), 9)
        self.assertNotIn("0" * 40, approved)


if __name__ == "__main__":
    unittest.main()
