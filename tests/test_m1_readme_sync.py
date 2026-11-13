"""Offline regression tests for independently pinned M1 README facts."""
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from tools.m1_readme_sync import SyncError, digest, run


def release(root: Path, *, day: int = 6, html: bytes = b"M1 archived fixture") -> str:
    root.mkdir(parents=True, exist_ok=True)
    end = date(2026, 11, day).isoformat()
    datepart = date(2026, 11, day + 1).strftime("%Y%m%d")
    manifest = {
        "candidate_sha256": "a" * 64,
        "daily_observations": 700,
        "dataset_id": f"run-{datepart}-023132-a32c03ef7daa",
        "html_sha256": digest(html),
        "method_version": "v0-empirical-35d",
        "observation_end": end,
        "retrieved_at": date(2026, 11, day + 1).isoformat() + "T02:31:32Z",
        "schema_version": "dayflare.m1.static-snapshot.v1",
        "series": 20,
        "source_receipt_sha256": "b" * 64,
        "source_seed_sha256": "c" * 64,
        "status": "DATED_ARCHIVE_NOT_LIVE",
    }
    (root / "index.html").write_bytes(html)
    raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (root / "release-manifest.json").write_bytes(raw)
    return digest(raw)


class READMEReleaseSyncTests(unittest.TestCase):
    def setUp(self):
        self.ctx = tempfile.TemporaryDirectory()
        self.addCleanup(self.ctx.cleanup)
        self.root = Path(self.ctx.name)
        self.folder = self.root / "m1"
        self.pin = release(self.folder)
        self.readme = self.root / "README.md"
        self.initial = ("# Dayflare\n\n**Latest accepted archive (old release):** old facts."
                        "\n\n### Earlier accepted release example\nKeep historical section.\n")
        self.readme.write_text(self.initial)

    def sync(self, *, write=False, bootstrap=False, pin=None):
        return run(self.readme, self.folder, pin or self.pin,
                   write=write, bootstrap=bootstrap)

    def test_shipped_quickstart_uses_current_accepted_manifest_pin(self):
        """A documentation consistency regression, not independent approval."""
        import re
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        marker = readme.split("<!-- dayflare:m1-release:start -->", 1)[1].split(
            "<!-- dayflare:m1-release:end -->", 1
        )[0]
        summary = re.search(
            r"Latest accepted archive [(]observed [0-9-]+–([0-9-]+) UTC",
            marker,
        )
        example = re.search(
            r"[*][*]Current accepted example [(]observed ([0-9-]+) UTC[)]:[*][*] "
            r".*?manifest SHA-256 `([0-9a-f]{64})`",
            readme,
        )
        self.assertIsNotNone(summary)
        self.assertIsNotNone(example)
        self.assertEqual(example.group(1), summary.group(1))
        self.assertEqual(
            re.findall(
                r"(?m)^python -m tools\.m1_readme_sync[^\n]*"
                r"--expected-manifest-sha256 ([0-9a-f]{64})", readme
            ),
            [example.group(2)] * 2,
            "README check/write examples must match the dated accepted manifest",
        )
        offline = readme.split("**One-command verified offline download", 1)[1].split(
            "<!-- dayflare:m1-release:start -->", 1
        )[0]
        self.assertIn(
            "--expected-manifest-sha256 " + example.group(2), offline,
            "The independently pinned offline example must match the accepted release",
        )

    def test_bootstrap_requires_explicit_write_and_independent_pin(self):
        with self.assertRaisesRegex(SyncError, "requires --write"):
            self.sync(bootstrap=True)
        with self.assertRaisesRegex(SyncError, "independent acceptance pin"):
            self.sync(write=True, bootstrap=True, pin="f" * 64)
        self.assertEqual(self.readme.read_text(), self.initial)
        self.assertTrue(self.sync(write=True, bootstrap=True))
        value = self.readme.read_text()
        self.assertIn("observed 2026-10-03–2026-11-06 UTC", value)
        self.assertIn("run-20261107-023132", value)
        self.assertIn("historical section", value)
        self.assertIn("**not** people", value)
        self.assertFalse(self.sync())
        self.assertFalse(self.sync(write=True))

    def test_three_successive_updates_and_check_failure_leave_last_valid(self):
        self.sync(write=True, bootstrap=True)
        prior = self.readme.read_bytes()
        for day in (7, 8, 9):
            self.pin = release(self.folder, day=day, html=f"m1-{day}".encode())
            with self.assertRaisesRegex(SyncError, "release facts differ"):
                self.sync()
            self.assertEqual(self.readme.read_bytes(), prior)
            self.assertTrue(self.sync(write=True))
            value = self.readme.read_text()
            self.assertIn(date(2026, 11, day).isoformat(), value)
            self.assertIn(f"run-202611{day+1:02d}-023132", value)
            self.assertNotIn("old facts", value)
            prior = self.readme.read_bytes()
            self.assertFalse(self.sync())

    def test_old_accepted_pin_and_equal_revision_conflict_cannot_rollback(self):
        old_pin = self.pin
        self.assertTrue(self.sync(write=True, bootstrap=True))
        self.pin = release(self.folder, day=7, html=b"newer")
        self.assertTrue(self.sync(write=True))
        latest = self.readme.read_bytes()

        # An older release remains authentic, but is not the latest release.
        self.pin = release(self.folder, day=6)
        self.assertEqual(self.pin, old_pin)
        with self.assertRaisesRegex(SyncError, "stale or conflicting"):
            self.sync(write=True)
        self.assertEqual(self.readme.read_bytes(), latest)

        # Even a later retrieval of the *older observation window* is stale.
        doc = json.loads((self.folder / "release-manifest.json").read_text())
        doc["retrieved_at"] = "2026-11-10T02:31:32Z"
        raw = (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode()
        (self.folder / "release-manifest.json").write_bytes(raw)
        with self.assertRaisesRegex(SyncError, "stale or conflicting"):
            self.sync(write=True, pin=digest(raw))
        self.assertEqual(self.readme.read_bytes(), latest)

        # Two different accepted inputs with identical observation/retrieval
        # revision cannot silently overwrite each other's advertised hashes.
        self.pin = release(self.folder, day=7, html=b"other approved content")
        with self.assertRaisesRegex(SyncError, "stale or conflicting"):
            self.sync(write=True)
        self.assertEqual(self.readme.read_bytes(), latest)

        # Repeating the identical accepted release remains idempotent.
        self.pin = release(self.folder, day=7, html=b"newer")
        self.assertFalse(self.sync())
        self.assertFalse(self.sync(write=True))

        # Same complete window with later retrieval may legitimately advance.
        doc = json.loads((self.folder / "release-manifest.json").read_text())
        doc["retrieved_at"] = "2026-11-09T02:31:32Z"
        raw = (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode()
        (self.folder / "release-manifest.json").write_bytes(raw)
        self.pin = digest(raw)
        self.assertTrue(self.sync(write=True))
        latest = self.readme.read_bytes()
        # Replaying the older retrieval of the same window now fails closed.
        self.pin = release(self.folder, day=7, html=b"newer")
        with self.assertRaisesRegex(SyncError, "stale or conflicting"):
            self.sync(write=True)
        self.assertEqual(self.readme.read_bytes(), latest)

    def test_damaged_documented_revision_cannot_be_replaced(self):
        self.sync(write=True, bootstrap=True)
        original = self.readme.read_text()
        self.readme.write_text(original.replace(
            "observed 2026-10-03–2026-11-06 UTC",
            "observed not-a-date–2026-11-06 UTC",
        ))
        malformed = self.readme.read_bytes()
        self.pin = release(self.folder, day=7)
        with self.assertRaisesRegex(SyncError, "cannot determine current"):
            self.sync(write=True)
        self.assertEqual(self.readme.read_bytes(), malformed)

    def test_changed_html_or_self_rehashed_manifest_cannot_be_adopted(self):
        self.sync(write=True, bootstrap=True)
        before = self.readme.read_bytes()
        (self.folder / "index.html").write_bytes(b"tampered")
        with self.assertRaisesRegex(SyncError, "HTML differs"):
            self.sync(write=True)
        self.assertEqual(self.readme.read_bytes(), before)
        self.pin = release(self.folder, day=7)
        manifest = json.loads((self.folder / "release-manifest.json").read_text())
        manifest["html_sha256"] = "f" * 64
        raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        (self.folder / "release-manifest.json").write_bytes(raw)
        with self.assertRaisesRegex(SyncError, "independent acceptance pin"):
            self.sync(write=True)
        self.assertEqual(self.readme.read_bytes(), before)

    def test_unapproved_scope_dates_duplicate_key_or_symlink_fail_closed(self):
        self.sync(write=True, bootstrap=True)
        before = self.readme.read_bytes()
        manifest = json.loads((self.folder / "release-manifest.json").read_text())
        manifest["series"] = 19
        raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        (self.folder / "release-manifest.json").write_bytes(raw)
        with self.assertRaisesRegex(SyncError, "incompatible M1"):
            self.sync(write=True, pin=digest(raw))
        manifest["series"] = 20
        manifest["retrieved_at"] = "2026-11-06T02:31:32Z"
        raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        (self.folder / "release-manifest.json").write_bytes(raw)
        with self.assertRaisesRegex(SyncError, "chronology"):
            self.sync(write=True, pin=digest(raw))
        raw = b'{"dataset_id":"a","dataset_id":"b"}\n'
        (self.folder / "release-manifest.json").write_bytes(raw)
        with self.assertRaisesRegex(SyncError, "duplicate release manifest key"):
            self.sync(write=True, pin=digest(raw))
        self.assertEqual(self.readme.read_bytes(), before)
        self.pin = release(self.folder)
        (self.folder / "index.html").unlink()
        (self.folder / "index.html").symlink_to(self.readme)
        with self.assertRaisesRegex(SyncError, "linked input"):
            self.sync(write=True)
        self.assertEqual(self.readme.read_bytes(), before)

    def test_broken_markers_and_ambiguous_bootstrap_never_rewrite(self):
        self.sync(write=True, bootstrap=True)
        old = self.readme.read_text().replace("<!-- dayflare:m1-release:end -->", "")
        self.readme.write_text(old)
        with self.assertRaisesRegex(SyncError, "markers"):
            self.sync(write=True)
        self.assertEqual(self.readme.read_text(), old)
        self.readme.write_text(self.initial + self.initial)
        with self.assertRaisesRegex(SyncError, "safely bootstrap"):
            self.sync(write=True, bootstrap=True)
        self.assertEqual(self.readme.read_text(), self.initial * 2)


if __name__ == "__main__":
    unittest.main()
