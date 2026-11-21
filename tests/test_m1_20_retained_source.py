"""Offline, no-network regression checks for pinned Nov 21 source."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from tools.m1_20_retained_source import (
    CAPSULE, CAPSULE_SHA256, CANDIDATE_SHA256, CapsuleError,
    pinned_members, unpack,
)

class RetainedSourceTests(unittest.TestCase):
    def test_exact_retained_source(self):
        raw = CAPSULE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), CAPSULE_SHA256)
        members = pinned_members()
        self.assertEqual(len(members), 23)
        self.assertEqual(hashlib.sha256(members["candidate.json"]).hexdigest(),
                         CANDIDATE_SHA256)

    def test_no_clobber_and_full_source_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "evidence"
            report = unpack(target)
            self.assertEqual(report["series"], 20)
            self.assertEqual(report["observations"], 700)
            self.assertEqual(report["publication_status"], "NOT_PUBLISHED")
            self.assertEqual(len(list((target / "raw").iterdir())), 20)
            with self.assertRaises(CapsuleError):
                unpack(target)
            self.assertEqual(hashlib.sha256((target / "candidate.json").read_bytes()).hexdigest(), CANDIDATE_SHA256)

    def test_corrupt_source_fails_before_extraction(self):
        raw = bytearray(CAPSULE.read_bytes())
        raw[100] ^= 1
        with self.assertRaisesRegex(CapsuleError, "pin mismatch"):
            pinned_members(bytes(raw))

if __name__ == "__main__":
    unittest.main()
