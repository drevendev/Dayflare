"""Read-only contract for the explicitly manual real stable-ID follow-up mode.

This test never calls Wikimedia or launches an Actions workflow.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.github/workflows/m1-real-identity-evidence.yml'


class ManualFollowupWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = SOURCE.read_text(encoding='utf-8')
        cls.header, cls.acquisition = cls.workflow.split('\n' + 'jobs:\n', 1)
        cls.discover, cls.followup = cls.acquisition.split('\n  followup:\n', 1)

    def test_manual_only_mode_and_read_only_permissions(self):
        self.assertIn('workflow_dispatch:\n    inputs:\n      task:', self.header)
        self.assertIn('default: discover', self.header)
        self.assertIn('options: [discover, stable-id-followup]', self.header)
        self.assertIn('permissions:\n  contents: read', self.header)
        self.assertNotIn('contents: write', self.workflow)
        self.assertNotIn('schedule:', self.header)
        self.assertNotIn('pull_request_target:', self.header)
        self.assertIn('branches: [master]', self.header)
        self.assertNotIn('branches: [feature/', self.header)

    def test_existing_discovery_and_followup_are_mutually_exclusive(self):
        self.assertIn("github.event_name != 'workflow_dispatch' || inputs.task == 'discover'", self.discover)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.task == 'stable-id-followup'", self.followup)
        self.assertIn('test "$SOURCE_REF" = "refs/heads/master"', self.followup)
        self.assertIn('ref: ${{ github.sha }}', self.followup)
        self.assertIn('persist-credentials: false', self.followup)
        self.assertIn('timeout-minutes: 15', self.followup)
        self.assertNotIn('git push', self.followup)

    def test_source_validation_before_upload_and_no_auto_publish(self):
        self.assertIn('eligible_snapshot(panel, provenance, clock=utc_now())', self.followup)
        self.assertIn('seed_for_same_ids(panel, day)', self.followup)
        self.assertIn('python -m tools.m1_identity_followup', self.followup)
        self.assertIn('verify_bundle(folder / "followup-source")', self.followup)
        self.assertIn('verify_attempted_selection(seed, attempts)', self.followup)
        self.assertIn('compare_bytes(baseline_bytes, later_bytes)', self.followup)
        self.assertIn('render_html(report)', self.followup)
        self.assertIn('if-no-files-found: error', self.followup)
        self.assertIn('retention-days: 7', self.followup)
        self.assertNotIn('deploy-pages', self.followup)
        self.assertNotIn('gh-pages', self.followup)
        self.assertNotIn('secrets.', self.followup)
        self.assertLess(self.followup.index('eligible_snapshot('), self.followup.index('python -m tools.m1_identity_followup'))
        self.assertLess(self.followup.index('verify_bundle('), self.followup.index('uses: actions/upload-artifact@v4'))


if __name__ == '__main__':
    unittest.main()
