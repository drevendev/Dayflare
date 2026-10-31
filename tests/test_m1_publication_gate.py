"""Synthetic-only gate regression tests; not evidence of Wikimedia origin."""
from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZipInfo

from tools.m1_publication_gate import (
    PublicationError, SCHEMA, compare_release, public_copy, read_archive,
)


def manifest(*, end="2026-10-25", retrieval="2026-10-28T12:25:21Z", digest="a" * 64):
    return {
        "schema_version": SCHEMA, "status": "DATED_ARCHIVE_NOT_LIVE",
        "dataset_id": f"run-{end}-{retrieval}", "method_version": "v0-empirical-35d",
        "observation_end": end, "retrieved_at": retrieval,
        "candidate_sha256": digest, "html_sha256": "b" * 64,
        "source_receipt_sha256": "c" * 64, "source_seed_sha256": "d" * 64,
        "series": 20, "daily_observations": 700,
    }


class MonotonicReleaseTests(unittest.TestCase):
    def test_first_candidate_does_not_assert_deployment(self):
        self.assertIn("REQUIRES_SEPARATE", compare_release(None, manifest()))

    def test_newer_complete_window_is_eligible_not_deployed(self):
        current = manifest()
        next_one = manifest(end="2026-11-01", retrieval="2026-11-04T12:25:21Z", digest="e" * 64)
        self.assertIn("REQUIRES_PUBLICATION_APPROVAL", compare_release(current, next_one))
        self.assertEqual(compare_release(current, dict(current)), "UNCHANGED_ALREADY_CURRENT")

    def test_old_window_or_retrieval_never_rolls_back(self):
        with self.assertRaisesRegex(PublicationError, "rollback"):
            compare_release(manifest(), manifest(end="2026-10-18"))
        with self.assertRaisesRegex(PublicationError, "rollback"):
            compare_release(manifest(), manifest(retrieval="2026-10-28T12:25:20Z"))

    def test_collision_and_reused_dataset_id_refused(self):
        old = manifest()
        with self.assertRaisesRegex(PublicationError, "collision"):
            compare_release(old, dict(old, candidate_sha256="e" * 64))
        with self.assertRaisesRegex(PublicationError, "reused"):
            compare_release(old, dict(old, retrieved_at="2026-10-28T13:25:21Z"))

    def test_noncanonical_or_impossible_revision_rejected_on_every_path(self):
        valid = manifest()
        future = manifest(end="2026-11-01", retrieval="2026-11-04T12:25:21Z")
        for observation, retrieval in (
            ("20261025", "2026-10-28T12:25:21Z"),
            ("2026-W43-7", "2026-10-28T12:25:21Z"),
            ("2026-02-30", "2026-10-28T12:25:21Z"),
            ("2026-10-25", "2026-10-25T23:59:59Z"),
            ("2026-10-25", "2026-10-24T00:00:00Z"),
            ("2026-10-25", "2026-10-28T12:25:21+00:00"),
            ("2026-10-25", "2026-10-28T12:25:21.000Z"),
            ("2026-10-25", "2026-10-28T14:25:21+02:00"),
            ("9999-12-31", "9999-12-31T23:59:59Z"),
        ):
            with self.subTest(observation=observation, retrieval=retrieval):
                bad = manifest(end=observation, retrieval=retrieval)
                for old, new in ((None, bad), (valid, bad), (bad, future)):
                    with self.assertRaisesRegex(PublicationError, "revision time"):
                        compare_release(old, new)

    def test_first_valid_next_day_midnight_is_allowed(self):
        first = manifest(retrieval="2026-10-26T00:00:00Z")
        self.assertIn("REQUIRES_SEPARATE", compare_release(None, first))
        self.assertEqual(compare_release(first, dict(first)), "UNCHANGED_ALREADY_CURRENT")

    def test_m0_method_and_bad_previous_refused(self):
        with self.assertRaisesRegex(PublicationError, "not M1"):
            compare_release({"schema_version": "dayflare.m0"}, manifest())
        with self.assertRaisesRegex(PublicationError, "method change"):
            compare_release(dict(manifest(), method_version="v1"), manifest())
        with self.assertRaisesRegex(PublicationError, "digest"):
            compare_release(manifest(digest="invalid"), manifest(end="2026-11-01",
                                                                  retrieval="2026-11-04T12:25:21Z"))
        with self.assertRaisesRegex(PublicationError, "time"):
            compare_release(manifest(retrieval="not-a-time"), manifest())

    def make_zip(self, names):
        with io.BytesIO() as stream:
            with ZipFile(stream, "w") as z:
                for name in names:
                    z.writestr(name, b"test")
            return stream.getvalue()

    def read_blob(self, blob):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "test.zip"
            path.write_bytes(blob)
            return read_archive(path)

    def test_unsafe_zip_members_refused(self):
        for names in (("a", "a"), ("../secret",), ("/root",),
                      ("x/./y",), ("x//y",), ("x\\y",)):
            with self.subTest(names=names), self.assertRaises(PublicationError):
                self.read_blob(self.make_zip(names))
        with io.BytesIO() as stream:
            with ZipFile(stream, "w") as z:
                info = ZipInfo("escape")
                info.external_attr = 0o120777 << 16
                z.writestr(info, b"target")
            with self.assertRaisesRegex(PublicationError, "non-regular"):
                self.read_blob(stream.getvalue())
        with io.BytesIO() as stream:
            with ZipFile(stream, "w") as z:
                z.writestr("big", b"x" * (512 * 1024 + 1))
            with self.assertRaisesRegex(PublicationError, "oversized"):
                self.read_blob(stream.getvalue())

    def test_public_text_retains_uncertainty_and_is_idempotence_safe(self):
        source = (
            "Dayflare · dated attention atlas (local preview)\n"
            "<strong>LOCAL EVIDENCE — UPSTREAM ORIGIN NOT INDEPENDENTLY VERIFIED</strong>. "
            "This is an offline preview, <strong>not</strong> a public release, live feed, "
            "stable historical page-ID series or representative ranking.\n"
            "A rolling preview is not a live publication."
        ).encode()
        output = public_copy(source)
        self.assertIn(b"DATED SOURCE EVIDENCE", output)
        self.assertIn(b"not</strong> a live feed", output)
        self.assertNotIn(b"offline preview", output)
        with self.assertRaisesRegex(PublicationError, "unknown preview"):
            public_copy(output)
        with self.assertRaises(PublicationError):
            public_copy(source + b"SYNTHETIC TEST DATA")


if __name__ == "__main__":
    unittest.main()
