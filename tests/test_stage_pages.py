"""Fail-closed immutable staging regressions for the historical M0 Pages ZIP."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from tools.build_static_release import build_zip, bundle_files
from tools.stage_pages import StageError, checked_files, stage, verify_stage


class PagesStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = bundle_files()
        cls.archive = build_zip(cls.files)
        cls.pin = hashlib.sha256(cls.files['release-manifest.json']).hexdigest()

    def test_stages_exact_immutable_candidate_and_checks_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'published-later'
            self.assertEqual(stage(self.archive, root, self.pin, self.files), 'STAGED_NOT_DEPLOYED')
            self.assertEqual(stage(self.archive, root, self.pin, self.files, check=True),
                             'STAGED_VERIFIED_NOT_DEPLOYED')
            with self.assertRaisesRegex(StageError, 'already exists'):
                stage(self.archive, root, self.pin, self.files)
            verify_stage(root, self.files)

    def test_missing_or_nonindependent_pin_fails_without_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'candidate'
            for pin in ('', 'abc', 'A'*64, '0'*64):
                with self.assertRaises(StageError):
                    stage(self.archive, root, pin, self.files)
            self.assertFalse(root.exists())

    def test_changed_archive_cannot_overwrite_previous_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'last-good'
            stage(self.archive, root, self.pin, self.files)
            original = (root / 'index.html').read_bytes()
            changed = dict(self.files)
            changed['index.html'] += b'<!-- unreviewed -->'
            with self.assertRaisesRegex(StageError, 'differs from current'):
                stage(build_zip(changed), root, self.pin, self.files)
            self.assertEqual((root/'index.html').read_bytes(), original)

    def test_zip_unknown_member_and_duplicate_member_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'stage'
            changed = dict(self.files)
            changed['unexpected.txt'] = b'bad'
            with self.assertRaisesRegex(StageError, 'differs from current'):
                stage(build_zip(changed), root, self.pin, self.files)
            self.assertFalse(root.exists())

    def test_staged_tampering_extra_members_missing_and_symlinks_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'candidate'
            stage(self.archive, root, self.pin, self.files)
            (root/'index.html').write_bytes(b'unreviewed')
            with self.assertRaisesRegex(StageError, 'Staged bytes differ'):
                stage(self.archive, root, self.pin, self.files, check=True)
            (root/'index.html').write_bytes(self.files['index.html'])
            (root/'extra-file.txt').write_text('bad')
            with self.assertRaisesRegex(StageError, 'member set'):
                stage(self.archive, root, self.pin, self.files, check=True)
            (root/'extra-file.txt').unlink()
            (root/'app.js').unlink()
            with self.assertRaisesRegex(StageError, 'member set'):
                stage(self.archive, root, self.pin, self.files, check=True)
            (root/'app.js').symlink_to(root/'index.html')
            with self.assertRaisesRegex(StageError, 'symlink'):
                stage(self.archive, root, self.pin, self.files, check=True)

    def test_invalid_expected_checkout_inventory_is_rejected(self):
        no_manifest = dict(self.files)
        del no_manifest['release-manifest.json']
        with self.assertRaisesRegex(StageError, 'inventory is incomplete'):
            checked_files(self.archive, self.pin, no_manifest)


if __name__ == '__main__':
    unittest.main()
