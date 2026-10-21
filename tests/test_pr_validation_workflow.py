"""Standard-library structural contracts, not a claim of hosted execution."""
from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/pr-validation.yml"


class OfflineWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_every_pr_is_checked_without_path_or_branch_filters(self):
        self.assertRegex(self.text, r"(?m)^  pull_request:\s*\n  push:")
        self.assertNotIn("paths:", self.text)
        self.assertNotIn("paths-ignore:", self.text)
        self.assertNotIn("pull_request_target", self.text)
        self.assertNotIn("schedule:", self.text)

    def test_read_only_token_and_no_credentials_or_live_collection(self):
        self.assertIn("permissions:\n  contents: read", self.text)
        self.assertIn("persist-credentials: false", self.text)
        for forbidden in ("contents: write", "pages: write", "id-token:",
                          "secrets.", "tools.d01_probe", "tools.d02_probe"):
            self.assertNotIn(forbidden, self.text)

    def test_exact_head_and_reviewed_action_pins(self):
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", self.text)
        actions = re.findall(r"uses: (actions/[a-z-]+)@([0-9a-f]{40})", self.text)
        self.assertEqual(len(actions), 2)
        self.assertEqual({name for name, _ in actions}, {"actions/checkout", "actions/setup-python"})
        self.assertEqual(len(re.findall(r"(?m)^\s+uses:", self.text)), 2)

    def test_bounded_matrix_runs_all_tests_and_compilation(self):
        self.assertIn("timeout-minutes: 5", self.text)
        self.assertIn("python-version: ['3.12', '3.13']", self.text)
        self.assertIn("cancel-in-progress: true", self.text)
        self.assertIn("python -m unittest discover -s tests -p 'test_*.py' -v", self.text)
        self.assertIn("python -m compileall -q tools tests", self.text)
        self.assertNotIn("continue-on-error:", self.text)


if __name__ == "__main__":
    unittest.main()
