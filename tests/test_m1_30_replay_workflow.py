"""Structural contract for the read-only archived-source replay, not runtime proof."""
from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/m1-30-replay-acceptance.yml'


class ReplayWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding='utf-8')

    def test_scoped_read_only_triggers(self):
        self.assertIn('permissions:\n  contents: read\n  actions: read', self.text)
        self.assertIn('github.ref == \'refs/heads/master\'', self.text)
        self.assertIn('github.event.pull_request.head.repo.full_name == github.repository', self.text)
        self.assertIn('persist-credentials: false', self.text)
        self.assertIn('paths:\n      - .github/workflows/m1-30-replay-acceptance.yml', self.text)
        for forbidden in ('schedule:', 'pull_request_target:', ': write', 'git push',
                          'deploy-pages', 'rolling_pageview_source collect', '--location-trusted'):
            self.assertNotIn(forbidden, self.text)

    def test_bounded_pinned_original_and_explicit_manual_inputs(self):
        self.assertIn('inputs.artifact_id', self.text)
        self.assertIn('inputs.expected_sha256', self.text)
        self.assertIn('14935003422', self.text)
        self.assertIn('1721869d687dd5f1b08b9ba9dcd963f8477299151f7f1c5f24090222c14fc305', self.text)
        self.assertIn('--max-time 60 --max-filesize 4194304', self.text)
        self.assertIn('^[1-9][0-9]{0,19}$', self.text)
        self.assertIn('^[0-9a-f]{64}$', self.text)
        self.assertIn('sha256sum --check', self.text)
        self.assertNotIn('unzip ', self.text)
        self.assertEqual(self.text.count('GH_TOKEN:'), 1)

    def test_replay_and_browser_gate_before_success_only_retention(self):
        self.assertEqual(self.text.count('python -m tools.m1_30_replay'), 2)
        for path in ('index.html', 'preview-manifest.json'):
            self.assertIn(f'cmp artifacts/replay/{path} artifacts/repeat/{path}', self.text)
        browser = self.text.index('python tests/m1/browser_30_source_artifact.py')
        retain = self.text.index('uses: actions/upload-artifact@v4')
        self.assertLess(browser, retain)
        self.assertIn('if: success()\n        uses: actions/upload-artifact@v4', self.text)
        self.assertIn('artifacts/replay-browser/', self.text)
        self.assertNotIn('--render-only', self.text)



class RetainedReplayWorkflowTests(unittest.TestCase):
    def test_git_retained_replay_browser_and_success_only_artifact(self):
        root = WORKFLOW.parents[2]
        workflow = (root / '.github/workflows/m1-validation.yml').read_text(encoding='utf-8')
        self.assertIn('permissions:\n  contents: read\njobs:', workflow)
        self.assertNotIn('contents: write', workflow)
        self.assertNotIn('actions: read', workflow)
        self.assertNotIn('GH_TOKEN:', workflow)
        start = workflow.index('      - name: Rebuild retained Nov 21 30-title atlas')
        end = workflow.index('      - name: Verify identity-history evidence', start)
        section = workflow[start:end]
        for required in (
            'python -m tools.m1_30_source_capsule replay',
            'evidence/m1-30-20261124-source.xz.b64',
            '1721869d687dd5f1b08b9ba9dcd963f8477299151f7f1c5f24090222c14fc305',
            '10d7fa4ed4b7c2bdab98d3c7d4c64a70d12b27aa15df5d4fd67f16194b93c543',
            'python tests/m1/browser_30_source_artifact.py artifacts/m1-30-20261121-local artifacts/m1-30-20261121-browser',
            'if: success()',
            'artifacts/m1-30-20261121-replay.json',
            'artifacts/m1-30-20261121-browser/',
            'if-no-files-found: error',
        ):
            self.assertIn(required, section)
        self.assertLess(section.index('source_capsule replay'), section.index('browser_30_source_artifact.py'))
        self.assertLess(section.index('browser_30_source_artifact.py'), section.index('actions/upload-artifact'))
        for forbidden in ('curl ', '--render-only', 'deploy-pages', 'git push', '14935003422'):
            self.assertNotIn(forbidden, section)


if __name__ == '__main__':
    unittest.main()
