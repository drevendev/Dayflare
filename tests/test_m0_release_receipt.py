"""Only accepted-master M0 CI may upload an unapproved, source-bound release artifact."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.build_static_release import bundle_files, digest
from tools.m0_release_receipt import (CandidateError, CONTENTS, candidate_bytes,
                                      check_candidate, exact_checkout, write_candidate)
from tools.stage_pages import StageError

REVISION = 'a' * 40


class M0ReleaseReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = bundle_files()

    def test_receipt_is_deterministic_and_explicitly_unapproved(self):
        result = candidate_bytes(self.files, REVISION)
        self.assertEqual(set(result), CONTENTS)
        self.assertEqual(result, candidate_bytes(self.files, REVISION))
        receipt = json.loads(result['release-receipt.json'])
        self.assertEqual(receipt['source_commit'], REVISION)
        self.assertEqual(receipt['archive_sha256'], digest(result['dayflare-m0.zip']))
        self.assertEqual(receipt['manifest_sha256'], digest(result['release-manifest.json']))
        self.assertEqual(receipt['status'], 'UNAPPROVED_MASTER_CANDIDATE_NOT_DEPLOYED')
        self.assertIs(receipt['independent_approval'], False)
        self.assertIs(receipt['live_verified'], False)
        self.assertEqual(receipt['dataset_id'], 'd02-20261018-084126')
        self.assertEqual(receipt['method_version'], 'v0-empirical-35d')
        self.assertEqual(receipt['observation_window_utc'], ['2026-08-11', '2026-09-14'])

    def test_cannot_self_attest_corrupt_or_incomplete_source(self):
        changed = dict(self.files)
        changed['index.html'] += b'changed without manifest update'
        with self.assertRaises(StageError):
            candidate_bytes(changed, REVISION)
        changed = dict(self.files)
        del changed['app.js']
        with self.assertRaises((StageError, KeyError)):
            candidate_bytes(changed, REVISION)
        for revision in ('', 'A'*40, '0'*39, 'not-a-commit'):
            with self.assertRaises(CandidateError):
                candidate_bytes(self.files, revision)

    def test_writes_once_then_detects_tampering_without_replacing_old_candidate(self):
        with tempfile.TemporaryDirectory() as base:
            target = Path(base) / 'candidate'
            expected = write_candidate(target, self.files, REVISION)
            check_candidate(target, expected)
            with self.assertRaisesRegex(CandidateError, 'already exists'):
                write_candidate(target, self.files, REVISION)
            self.assertEqual((target/'dayflare-m0.zip').read_bytes(), expected['dayflare-m0.zip'])
            (target/'release-receipt.json').write_text('{}')
            with self.assertRaisesRegex(CandidateError, 'bytes changed'):
                check_candidate(target, expected)
            (target/'release-receipt.json').write_bytes(expected['release-receipt.json'])
            (target/'extra.txt').write_text('not approved')
            with self.assertRaisesRegex(CandidateError, 'inventory'):
                check_candidate(target, expected)

    def test_checkout_is_exact_and_clean_before_claiming_a_commit(self):
        with patch('tools.m0_release_receipt.subprocess.check_output', return_value=REVISION + '\n'), \
             patch('tools.m0_release_receipt.subprocess.run') as diff:
            diff.return_value.returncode = 0
            exact_checkout(REVISION)
            diff.return_value.returncode = 1
            with self.assertRaisesRegex(CandidateError, 'Tracked source'):
                exact_checkout(REVISION)
        with patch('tools.m0_release_receipt.subprocess.check_output', return_value='b'*40 + '\n'):
            with self.assertRaisesRegex(CandidateError, 'Checked out'):
                exact_checkout(REVISION)

    def test_workflow_pins_master_and_acceptance_without_any_deploy(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/m0-preview-validation.yml').read_text()
        self.assertIn('  candidate:', workflow)
        candidate = workflow.split('  candidate:', 1)[1]
        self.assertIn("github.ref == 'refs/heads/master'", candidate)
        self.assertIn('needs: [python, browser, native_http]', candidate)
        self.assertIn('persist-credentials: false', candidate)
        self.assertIn('ref: ${{ github.sha }}', candidate)
        self.assertIn('tools.m0_release_receipt', candidate)
        self.assertIn('if-no-files-found: error', candidate)
        self.assertIn('retention-days: 7', candidate)
        self.assertNotIn('pages: write', workflow)
        self.assertNotIn('deploy-pages', workflow)
        self.assertNotIn('pull_request_target', workflow)
        self.assertNotIn('secrets.', workflow)


if __name__ == '__main__':
    unittest.main()
