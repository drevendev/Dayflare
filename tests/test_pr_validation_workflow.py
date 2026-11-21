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
        self.assertEqual(len(actions), 5)
        self.assertEqual({name for name, _ in actions},
                         {"actions/checkout", "actions/setup-python", "actions/upload-artifact"})
        pins = dict(actions)
        self.assertEqual(pins["actions/upload-artifact"],
                         "ea165f8d65b6e75b540449e92b4886f43607fa02")
        self.assertEqual(len(re.findall(r"(?m)^\s+uses:", self.text)), 5)
        # All three distinct read-only artifacts use the same reviewed pin.
        self.assertEqual(sum(name == "actions/upload-artifact" for name, _ in actions), 3)
        self.assertIn("python -m tools.m1_20_local_atlas artifacts/m1-20-20261118-local", self.text)
        self.assertIn("name: m1-20-20261118-local-${{ github.event.pull_request.head.sha || github.sha }}", self.text)
        self.assertIn("path: artifacts/m1-20-20261118-local/", self.text)
        self.assertIn("python -m tools.m1_20_release_candidate artifacts/m1-20-20261118-candidate", self.text)
        self.assertIn("name: m1-20-20261118-release-candidate-${{ github.event.pull_request.head.sha || github.sha }}", self.text)
        self.assertIn("path: artifacts/m1-20-20261118-candidate/", self.text)
        candidate_upload = self.text.split(
            "name: m1-20-20261118-release-candidate-", 1)[1].split(
            "      - name: Build dated unpublished 30-title", 1)[0]
        self.assertIn("include-hidden-files: true", candidate_upload)
        self.assertIn("retention-days: 14", candidate_upload)
        self.assertIn("name: m1-30-unpublished-portable-${{ github.event.pull_request.head.sha || github.sha }}", self.text)
        self.assertIn("if: matrix.python-version == '3.13'", self.text)
        self.assertIn("python -m tools.m1_30_portable_bundle --output", self.text)
        self.assertIn("if-no-files-found: error", self.text)
        self.assertIn("retention-days: 14", self.text)

    def test_bounded_matrix_runs_all_tests_and_compilation(self):
        self.assertIn("timeout-minutes: 5", self.text)
        self.assertIn("python-version: ['3.12', '3.13']", self.text)
        self.assertIn("cancel-in-progress: true", self.text)
        self.assertIn("python -m unittest discover -s tests -p 'test_*.py' -v", self.text)
        self.assertIn("python -m compileall -q tools tests", self.text)
        self.assertNotIn("continue-on-error:", self.text)


if __name__ == "__main__":
    unittest.main()
