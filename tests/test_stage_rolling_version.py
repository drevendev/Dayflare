"""Offline only: synthetic rolling data, durable monotonic local candidate storage."""
from __future__ import annotations

import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import multiprocessing
from pathlib import Path
from unittest import mock
import tempfile
import unittest

from tools.rolling_window_gate import WindowError, canonical, validate
from tools.stage_rolling_version import StageError, stage, _current
from test_rolling_window_gate import example, NOW


def worker(root, candidate, queue):
    try:
        queue.put(stage(candidate, Path(root), now=NOW)["result"])
    except (StageError, WindowError) as exc:
        queue.put(type(exc).__name__)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "rolling"
        self.doc = example()

    def accepted(self, candidate=None):
        return stage(candidate or self.doc, self.root, now=NOW)

    def pointer_bytes(self):
        return (self.root / "current.json").read_bytes()

    def versions(self):
        return sorted(p.name for p in (self.root / "versions").iterdir() if not p.name.startswith(".incoming"))

    def test_first_stage_and_exact_idempotence(self):
        first = self.accepted()
        self.assertEqual(first["result"], "PROMOTED_LOCAL_CANDIDATE_ONLY")
        self.assertEqual(first["publication_status"], "LOCAL_CANDIDATE_ONLY_NOT_PUBLISHED")
        original = self.pointer_bytes()
        replay = self.accepted()
        self.assertEqual(replay["result"], "UNCHANGED_IDEMPOTENT")
        self.assertFalse(replay["version_created"])
        self.assertEqual(self.pointer_bytes(), original)
        self.assertEqual(self.versions(), [first["version_sha256"]])

    def test_two_separate_builds_are_byte_identical(self):
        first = self.accepted()
        other = Path(self.tmp.name) / "second"
        stage(self.doc, other, now=NOW)
        self.assertEqual((other / "current.json").read_bytes(), self.pointer_bytes())
        for name in ("candidate.json", "gate-report.json", "manifest.json"):
            self.assertEqual((self.root / "versions" / first["version_sha256"] / name).read_bytes(),
                             (other / "versions" / first["version_sha256"] / name).read_bytes())

    def test_newer_retrieval_same_window_promotes_and_keeps_older(self):
        old = self.accepted()
        changed = copy.deepcopy(self.doc)
        changed["dataset_id"] = "run-20261023b"
        changed["retrieved_at"] = "2026-10-23T11:05:00Z"
        result = self.accepted(changed)
        self.assertEqual(result["result"], "PROMOTED_LOCAL_CANDIDATE_ONLY")
        self.assertEqual(_current(self.root)["dataset_id"], "run-20261023b")
        self.assertIn(old["version_sha256"], self.versions())
        self.assertIn(result["version_sha256"], self.versions())

    def test_stale_rollback_and_equal_revision_collision_preserve_current(self):
        self.accepted()
        before = self.pointer_bytes()
        older = copy.deepcopy(self.doc)
        older["retrieved_at"] = "2026-10-23T11:00:00Z"
        with self.assertRaisesRegex(StageError, "rollback"):
            self.accepted(older)
        equal = copy.deepcopy(self.doc)
        equal["dataset_id"] = "different-run"
        with self.assertRaisesRegex(StageError, "collision"):
            self.accepted(equal)
        self.assertEqual(self.pointer_bytes(), before)

    def test_identical_dataset_id_for_changed_content_rejected(self):
        self.accepted()
        before = self.pointer_bytes()
        changed = copy.deepcopy(self.doc)
        changed["retrieved_at"] = "2026-10-23T11:06:00Z"
        with self.assertRaisesRegex(StageError, "dataset ID reused"):
            self.accepted(changed)
        self.assertEqual(self.pointer_bytes(), before)

    def test_invalid_missing_day_preserves_pointer_and_versions(self):
        self.accepted()
        before, versions = self.pointer_bytes(), self.versions()
        missing = copy.deepcopy(self.doc)
        missing["series"][0]["daily"].pop()
        with self.assertRaises(WindowError):
            self.accepted(missing)
        self.assertEqual(self.pointer_bytes(), before)
        self.assertEqual(self.versions(), versions)

    def test_corrupted_current_digest_fails_closed(self):
        self.accepted()
        before = self.pointer_bytes()
        ptr = self.root / "current.json"
        ptr.write_bytes(b'{"broken":true}\n')
        with self.assertRaises(StageError):
            self.accepted()
        self.assertNotEqual(ptr.read_bytes(), before)
        self.assertEqual(ptr.read_bytes(), b'{"broken":true}\n')

    def test_corrupted_version_bytes_fails_closed(self):
        first = self.accepted()
        before = self.pointer_bytes()
        (self.root / "versions" / first["version_sha256"] / "candidate.json").write_bytes(b'{}\n')
        newer = copy.deepcopy(self.doc)
        newer["dataset_id"] = "fresh-run"
        newer["retrieved_at"] = "2026-10-23T11:03:00Z"
        with self.assertRaisesRegex(StageError, "digest|version name|candidate bytes"):
            self.accepted(newer)
        self.assertEqual(self.pointer_bytes(), before)

    def test_forged_gate_report_and_matching_manifest_hash_fail_closed(self):
        first = self.accepted()
        before = self.pointer_bytes()
        version = self.root / "versions" / first["version_sha256"]
        report_path = version / "gate-report.json"
        manifest_path = version / "manifest.json"
        forged_report = json.loads(report_path.read_bytes())
        forged_report["observations"] += 35
        forged_bytes = canonical(forged_report)
        report_path.write_bytes(forged_bytes)
        forged_manifest = json.loads(manifest_path.read_bytes())
        forged_manifest["gate_report_sha256"] = hashlib.sha256(forged_bytes).hexdigest()
        manifest_path.write_bytes(canonical(forged_manifest))
        # Previously both files were self-consistent, so the stored version
        # passed readback although its claimed coverage was untrue.
        newer = copy.deepcopy(self.doc)
        newer["dataset_id"] = "next"
        newer["retrieved_at"] = "2026-10-23T11:03:00Z"
        with self.assertRaisesRegex(StageError, "gate report differs"):
            self.accepted(newer)
        self.assertEqual(self.pointer_bytes(), before)
        self.assertEqual(self.versions(), [first["version_sha256"]])

    def test_late_staging_cannot_make_early_retrieval_complete(self):
        early = copy.deepcopy(self.doc)
        early["retrieved_at"] = "2026-10-22T12:05:00Z"
        for row in early["series"]:
            row["source"]["requested_at"] = "2026-10-22T12:00:00Z"
        # October 23 staging satisfies lag=2, but October 22 retrieval
        # does not. Never promote an immature source after the fact.
        with self.assertRaisesRegex(StageError, "not complete at retrieval time"):
            self.accepted(early)
        self.assertFalse(self.root.exists())

    def test_failed_atomic_replace_keeps_previous_pointer(self):
        self.accepted()
        before = self.pointer_bytes()
        changed = copy.deepcopy(self.doc)
        changed["dataset_id"] = "next"
        changed["retrieved_at"] = "2026-10-23T11:02:00Z"
        with mock.patch("tools.stage_rolling_version.os.replace", side_effect=OSError("simulated power loss")):
            with self.assertRaisesRegex(OSError, "simulated power loss"):
                self.accepted(changed)
        self.assertEqual(self.pointer_bytes(), before)
        # Crash may leave an unreferenced verified version; restart reuses it.
        again = self.accepted(changed)
        self.assertEqual(again["result"], "PROMOTED_LOCAL_CANDIDATE_ONLY")
        self.assertFalse(again["version_created"])

    def test_orphan_temp_is_not_current(self):
        self.accepted()
        before = self.pointer_bytes()
        orphan = self.root / "versions" / ".incoming-interrupted"
        orphan.mkdir()
        (orphan / "candidate.json").write_bytes(b'partial')
        self.assertEqual(_current(self.root)["dataset_id"], self.doc["dataset_id"])
        self.assertEqual(self.pointer_bytes(), before)

    def test_newer_refresh_cannot_drop_substitute_or_retitle_cohort(self):
        first = self.accepted()
        before_pointer, before_versions = self.pointer_bytes(), self.versions()
        for mode in ("dropped", "substituted", "retitled"):
            with self.subTest(mode=mode):
                changed = copy.deepcopy(self.doc)
                changed["dataset_id"] = f"run-{mode}"
                changed["retrieved_at"] = "2026-10-23T11:05:00Z"
                if mode == "dropped":
                    changed["series"].pop()
                elif mode == "substituted":
                    changed["series"][0]["page_id"] += 100
                else:
                    row = changed["series"][0]
                    row["title"] = "Retitled_English"
                    row["source"]["endpoint"] = row["source"]["endpoint"].replace(
                        "Example_English", "Retitled_English")
                # All three are individually complete and valid candidate
                # snapshots: the failure is continuity across revisions.
                self.assertEqual(validate(changed, now=NOW)["window_days"], 35)
                with self.assertRaisesRegex(StageError, "cohort changed"):
                    self.accepted(changed)
                self.assertEqual(self.pointer_bytes(), before_pointer)
                self.assertEqual(self.versions(), before_versions)
        # A new retrieval of the same curated histories is still eligible.
        good = copy.deepcopy(self.doc)
        good["dataset_id"] = "run-same-cohort"
        good["retrieved_at"] = "2026-10-23T11:06:00Z"
        accepted = self.accepted(good)
        self.assertEqual(accepted["result"], "PROMOTED_LOCAL_CANDIDATE_ONLY")
        self.assertIn(first["version_sha256"], self.versions())
        self.assertEqual(len(self.versions()), 2)

    def test_method_version_requires_explicit_migration(self):
        self.accepted()
        changed = copy.deepcopy(self.doc)
        changed["method_version"] = "not-compatible"
        changed["dataset_id"] = "new"
        changed["retrieved_at"] = "2026-10-23T11:03:00Z"
        with self.assertRaisesRegex(StageError, "method version"):
            self.accepted(changed)

    def test_symlink_current_and_versions_rejected(self):
        self.accepted()
        actual = self.root / "current.json"
        actual.rename(self.root / "real.json")
        actual.symlink_to("real.json")
        with self.assertRaisesRegex(StageError, "linked artifact"):
            self.accepted()
        actual.unlink()
        (self.root / "real.json").rename(actual)
        versions = self.root / "versions"
        versions.rename(self.root / "real_versions")
        versions.symlink_to("real_versions", target_is_directory=True)
        with self.assertRaisesRegex(StageError, "unsafe"):
            self.accepted()

    def test_competing_processes_preserve_newest_revision(self):
        old = copy.deepcopy(self.doc)
        new = copy.deepcopy(self.doc)
        old["dataset_id"] = "first"
        old["retrieved_at"] = "2026-10-23T11:02:00Z"
        new["dataset_id"] = "second"
        new["retrieved_at"] = "2026-10-23T11:04:00Z"
        queue = multiprocessing.Queue()
        jobs = [multiprocessing.Process(target=worker, args=(str(self.root), d, queue)) for d in (old, new)]
        for job in jobs: job.start()
        for job in jobs:
            job.join(8)
            self.assertEqual(job.exitcode, 0)
        answers = [queue.get(timeout=2) for _ in jobs]
        self.assertEqual(_current(self.root)["dataset_id"], "second")
        self.assertIn("PROMOTED_LOCAL_CANDIDATE_ONLY", answers)
        self.assertTrue(set(answers) <= {"PROMOTED_LOCAL_CANDIDATE_ONLY", "StageError"})


if __name__ == "__main__":
    unittest.main()
