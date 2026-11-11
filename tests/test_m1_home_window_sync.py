"""Offline homepage M1 release synchronization: positive/negative acceptance."""
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from tools.m1_readme_sync import SyncError, accepted_manifest, digest, render
from tools.m1_home_window_sync import render_window, run, _revisions

ROOT = Path(__file__).resolve().parents[1]


def make_release(folder: Path, end: date, retrieved: datetime, *,
                 html: bytes = b"accepted M1 fixture") -> str:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_bytes(html)
    manifest = {
        "candidate_sha256": "a" * 64,
        "daily_observations": 700,
        "dataset_id": "run-" + retrieved.strftime("%Y%m%d-%H%M%S") + "-a32c03ef7daa",
        "html_sha256": digest(html),
        "method_version": "v0-empirical-35d",
        "observation_end": end.isoformat(),
        "retrieved_at": retrieved.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "dayflare.m1.static-snapshot.v1",
        "series": 20,
        "source_receipt_sha256": "b" * 64,
        "source_seed_sha256": "c" * 64,
        "status": "DATED_ARCHIVE_NOT_LIVE",
    }
    payload = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (folder / "release-manifest.json").write_bytes(payload)
    return digest(payload)


class HomepageSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / "accepted-m1"
        self.site = self.root / "site" / "index.html"
        self.site.parent.mkdir()
        self.readme = self.root / "README.md"
        self.current_end = date(2026, 11, 6)
        self.current_retrieved = datetime(2026, 11, 9, 2, 31, 32)
        self.site.write_text("<!doctype html>\n<h1>Dayflare</h1>\n" +
                             render_window(self.current_end, self.current_retrieved) +
                             "\n<footer>Historical only</footer>\n", encoding="utf-8")
        self.set_release(7)

    def set_release(self, day: int, *, html: bytes | None = None,
                    retrieved: datetime | None = None):
        end = date(2026, 11, day)
        retrieved = retrieved or datetime(2026, 11, day + 3, 4, 33, 17)
        self.pin = make_release(self.folder, end, retrieved,
                                html=html or f"fixture-{day}".encode())
        manifest = accepted_manifest(self.folder, self.pin)
        self.readme.write_text("# Dayflare\n" + render(manifest) +
                               "\nKeep earlier evidence.\n", encoding="utf-8")

    def sync(self, *, write: bool = False, pin: str | None = None):
        return run(self.site, self.readme, self.folder, pin or self.pin, write=write)

    def test_first_screen_is_updated_without_changing_other_content(self):
        before = self.site.read_bytes()
        readme = self.readme.read_bytes()
        with self.assertRaisesRegex(SyncError, "homepage release window differs"):
            self.sync()
        self.assertEqual(self.site.read_bytes(), before)
        self.assertTrue(self.sync(write=True))
        after = self.site.read_text()
        self.assertIn('data-observed-start="2026-10-04"', after)
        self.assertIn('data-observed-end="2026-11-07"', after)
        self.assertIn('data-retrieved-at="2026-11-10T04:33:17Z"', after)
        self.assertIn("4 Oct</time>–<time datetime=\"2026-11-07\">7 Nov 2026", after)
        self.assertIn("Historical title requests, not live attention or unique people.", after)
        self.assertIn("<footer>Historical only</footer>", after)
        self.assertEqual(self.readme.read_bytes(), readme)
        self.assertFalse(self.sync())
        self.assertFalse(self.sync(write=True))

    def test_three_successive_accepted_windows_and_stale_replay(self):
        for day in (7, 8, 9):
            self.set_release(day)
            self.assertTrue(self.sync(write=True))
            self.assertIn(f'data-observed-end="2026-11-{day:02d}"', self.site.read_text())
        last = self.site.read_bytes()
        self.set_release(8)
        with self.assertRaisesRegex(SyncError, "stale accepted release"):
            self.sync(write=True)
        self.assertEqual(self.site.read_bytes(), last)

    def test_mismatched_readme_bad_pin_or_modified_html_never_writes(self):
        before = self.site.read_bytes()
        with self.assertRaisesRegex(SyncError, "independent acceptance pin"):
            self.sync(write=True, pin="f" * 64)
        self.readme.write_text("# wrong archive\n", encoding="utf-8")
        with self.assertRaisesRegex(SyncError, "README does not document"):
            self.sync(write=True)
        self.assertEqual(self.site.read_bytes(), before)
        self.set_release(7)
        (self.folder / "index.html").write_text("damaged", encoding="utf-8")
        with self.assertRaisesRegex(SyncError, "HTML differs"):
            self.sync(write=True)
        self.assertEqual(self.site.read_bytes(), before)

    def test_noncanonical_or_duplicate_homepage_marker_is_never_rewritten(self):
        for wrong in (
            self.site.read_text().replace("9 Nov 2026", "9 NOV 2026"),
            self.site.read_text().replace('id="accepted-window"', 'id="missing-window"'),
            self.site.read_text() + self.site.read_text(),
            self.site.read_text().replace('data-observed-start="2026-10-03"',
                                          'data-observed-start="2026-10-04"'),
        ):
            self.site.write_text(wrong, encoding="utf-8")
            with self.assertRaises(SyncError):
                self.sync(write=True)
            self.assertEqual(self.site.read_text(), wrong)

    def test_no_changes_to_accepted_archive_or_readme_and_no_linked_targets(self):
        original = self.site.read_bytes()
        readme = self.readme.read_bytes()
        archive = (self.folder / "index.html").read_bytes()
        self.site.unlink()
        self.site.symlink_to(self.readme)
        with self.assertRaises(SyncError):
            self.sync(write=True)
        self.site.unlink()
        self.site.write_bytes(original)
        with self.assertRaisesRegex(SyncError, "overlaps"):
            run(self.folder / "index.html", self.readme, self.folder, self.pin,
                write=True)
        self.assertEqual(self.readme.read_bytes(), readme)
        self.assertEqual((self.folder / "index.html").read_bytes(), archive)

    def test_linked_output_parent_does_not_touch_external_file(self):
        outside = self.root / "outside"
        outside.mkdir()
        original = self.site.read_bytes()
        external = outside / "index.html"
        external.write_bytes(original)
        self.site.unlink()
        self.site.parent.rmdir()
        try:
            self.site.parent.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlinks are unavailable on this filesystem")
        self.assertFalse(self.site.is_symlink())  # The leaf alone looks regular.
        self.assertTrue(self.site.parent.is_symlink())
        with self.assertRaisesRegex(SyncError, "linked/reparse"):
            self.sync(write=True)
        self.assertEqual(external.read_bytes(), original)

    def test_year_boundary_is_explicit_and_shipped_html_is_canonical(self):
        page = render_window(date(2027, 1, 9), datetime(2027, 1, 12, 4, 5, 6))
        self.assertIn("6 Dec 2026</time>–", page)
        self.assertIn("9 Jan 2027</time>", page)
        live_source = (ROOT / "site/index.html").read_text(encoding="utf-8")
        match, end, retrieved = _revisions(live_source)
        self.assertEqual(match.group(0), render_window(end, retrieved))
        self.assertEqual(end, date(2026, 11, 8))
        self.assertEqual(retrieved, datetime(2026, 11, 11, 6, 31, 2))


if __name__ == "__main__":
    unittest.main()
