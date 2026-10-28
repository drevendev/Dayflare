"""Synthetic-only overlay unit tests; no Pages deployment or Wikimedia claim."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from tools.m1_publication_gate import PublicationError, SCHEMA, canonical
from tools.m1_pages_overlay import inventory, sha, stage_overlay


def m1_manifest(end="2026-10-25", retrieved="2026-10-28T15:33:50Z", c="a" * 64,
                html=b"M1 synthetic HTML") -> dict:
    return {"schema_version": SCHEMA, "status": "DATED_ARCHIVE_NOT_LIVE",
            "dataset_id": "synthetic-" + end + "-" + retrieved,
            "method_version": "v0-empirical-35d", "observation_end": end,
            "retrieved_at": retrieved, "candidate_sha256": c,
            "html_sha256": sha(html), "source_receipt_sha256": "b" * 64,
            "source_seed_sha256": "c" * 64, "series": 20,
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

    def test_previous_m1_tampering_is_rejected(self):
        self.stage()
        (self.dest / "m1/index.html").write_bytes(b"changed")
        new_dir = self.base / "later"
        pin, receipt = write_m1(new_dir, end="2026-11-01",
                                retrieved="2026-11-04T15:33:50Z", c="d" * 64)
        with self.assertRaisesRegex(PublicationError, "HTML digest mismatch"):
            stage_overlay(self.dest, new_dir, self.base / "tampered-output", pin, receipt)


if __name__ == "__main__":
    unittest.main()
