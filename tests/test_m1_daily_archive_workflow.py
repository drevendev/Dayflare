"""Static guardrails for the bounded, unpublished M1 daily source archive.

These checks complement transport/staging tests; they do not claim a
successful scheduled run, Wikimedia provenance, or a public Pages release.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/m1-curated-rolling-pageviews.yml"
DOC = ROOT / "docs/M1_ROLLING_PREVIEW.md"


class DailyArchiveWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.documentation = DOC.read_text(encoding="utf-8")

    def test_uses_existing_read_only_workflow_with_default_branch_schedule(self):
        text = self.workflow
        self.assertIn("  pull_request:\n", text)
        self.assertIn("  workflow_dispatch:\n", text)
        self.assertIn("  schedule:\n    - cron: '17 6 * * *'", text)
        self.assertEqual(text.count("  schedule:\n"), 1)
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", text)
        self.assertIn("permissions:\n  contents: read\n", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("pages: write", text)
        self.assertNotIn("deploy-pages@", text)
        self.assertNotIn("git push", text)
        self.assertNotIn("pull_request_target:", text)

    def test_scheduled_retrieval_cannot_cancel_running_archives(self):
        text = self.workflow
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", text)
        self.assertNotIn("cancel-in-progress: true", text)
        self.assertIn("timeout-minutes: 15", text)
        self.assertIn("if: success()\n        uses: actions/upload-artifact@v4", text)

    def test_successful_snapshot_is_bounded_and_retained(self):
        text = self.workflow
        self.assertIn("python -m tools.rolling_pageview_source verify", text)
        self.assertIn("python -m tools.rolling_pageview_source stage", text)
        self.assertIn("python -m tools.rolling_snapshot_preview --from-stage", text)
        self.assertIn("retention-days: 30", text)
        self.assertIn("if-no-files-found: error", text)
        self.assertIn("artifacts/m1-curated-stage/versions/", text)
        self.assertIn("artifacts/m1-curated-source/", text)
        self.assertIn("artifacts/index.html", text)

    def test_docs_do_not_call_archives_live_or_permanent_publication(self):
        doc = self.documentation
        self.assertIn("06:17 UTC", doc)
        self.assertIn("30 days", doc)
        self.assertIn("no durable cross-run", doc)
        self.assertIn("not** a permanent last-valid website guarantee", doc)
        self.assertIn("authorized Pages configuration", doc)


    def test_real_m0_m1_overlay_is_staged_only_after_source_archive_retained(self):
        text = self.workflow
        archive_position = text.index("name: Retain exact raw source and local candidate")
        overlay_position = text.index("name: Reproduce M0+M1 Pages overlay")
        self.assertLess(archive_position, overlay_position)
        self.assertIn("git ls-remote origin refs/heads/gh-pages", text)
        self.assertIn("git fetch --no-tags --depth=1 origin refs/heads/gh-pages", text)
        self.assertIn('test "$(git rev-parse FETCH_HEAD)" = "$pages_base"', text)
        self.assertIn('git archive "$pages_base" | tar -x', text)
        self.assertIn("python -m tools.m1_pages_overlay", text)
        self.assertIn("--expected-candidate-sha256", text)
        self.assertIn("--expected-manifest-sha256", text)
        self.assertIn("M0 root changed in staged candidate", text)
        self.assertIn("M1 subtree differs from source-gated candidate", text)
        self.assertIn("STAGED_NOT_DEPLOYED", text)
        self.assertIn("m1-pages-stage-receipt.json", text)
        self.assertIn("m1-pages-stage/", text)
        self.assertEqual(text.count("retention-days: 30"), 2)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("git push", text)
        self.assertNotIn("deploy-pages@", text)


if __name__ == "__main__":
    unittest.main()
