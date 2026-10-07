"""Guard the bounded, read-only D02 target-runtime path (no YAML dependency)."""
from pathlib import Path
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/d02-runtime-probe.yml'


class D02RuntimeWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding='utf-8')

    def test_runs_on_pr_and_default_branch_not_only_a_probe_branch(self) -> None:
        self.assertIn('  pull_request:\n', self.text)
        self.assertIn('    branches: [master]\n', self.text)
        self.assertIn('  workflow_dispatch:\n', self.text)
        self.assertNotIn('research/d02-35day-probe', self.text)
        self.assertNotIn('pull_request_target', self.text)
        self.assertNotIn('schedule:', self.text)

    def test_has_read_only_repository_permissions_and_no_persisted_credentials(self) -> None:
        self.assertIn('permissions:\n  contents: read\n', self.text)
        self.assertIn('persist-credentials: false\n', self.text)
        self.assertNotIn('secrets.', self.text)
        self.assertNotIn('write', self.text)

    def test_tests_the_exact_head_with_module_entrypoint(self) -> None:
        self.assertIn('ref: ${{ github.event.pull_request.head.sha || github.sha }}', self.text)
        self.assertIn('run: python -m tools.d02_probe\n', self.text)
        self.assertIn("python -m unittest discover -s tests -p 'test_d0*.py' -v", self.text)
        self.assertNotIn('run: python tools/d02_probe.py', self.text)

    def test_retains_only_bounded_evidence_even_on_failure(self) -> None:
        self.assertIn('if: always()\n', self.text)
        self.assertIn('            artifacts/d02/sample.json\n', self.text)
        self.assertIn('            artifacts/d02/receipt.json\n', self.text)
        self.assertIn('if-no-files-found: error\n', self.text)
        self.assertIn('retention-days: 7\n', self.text)

    def test_runtime_and_concurrency_are_bounded(self) -> None:
        self.assertIn('timeout-minutes: 5\n', self.text)
        self.assertIn('cancel-in-progress: true\n', self.text)
        self.assertIn('group: d02-probe-', self.text)


if __name__ == '__main__':
    unittest.main()
