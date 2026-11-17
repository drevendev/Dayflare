"""Read-only same-run 30-title pageview pipeline contract (offline structural tests).

Passing tests do not establish a real provider run or public deployment.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/m1-real-identity-evidence.yml"


class ThirtyTitlePageviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full = WORKFLOW.read_text(encoding="utf-8")
        cls.source, cls.views = cls.full.split("\n  pageviews:\n", 1)

    def test_reuses_exact_same_run_identity_bundle_and_sha(self):
        text = self.views
        self.assertIn("needs: acquire", text)
        self.assertIn("if: ${{ needs.acquire.result == 'success' }}", text)
        self.assertIn("name: m1-real-identity-${{ github.sha }}-${{ github.run_attempt }}", text)
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("receipt['source_commit'] != source_sha", text)
        self.assertIn("verify_discovery(curated, root / 'm1-title')", text)
        self.assertIn("verify_bundle(root / 'm1-identity')", text)

    def test_rejects_partial_or_ambiguous_inputs_before_network(self):
        text = self.views
        handoff = text.index("name: Replay both source bundles")
        request = text.index("name: Acquire exactly 30 complete 35-day title histories")
        self.assertLess(handoff, request)
        for needle in ("receipt['selected_titles'] != 30",
                       "receipt['current_id_candidates'] != 30",
                       "receipt['independently_retained_identities'] != 30",
                       "receipt['title_exclusions'] != 0",
                       "receipt['independent_requery_unavailable'] != 0",
                       "handoff['candidate_count'] != 30",
                       "handoff['excluded_count'] != 0",
                       "proof['verified_pages'] != 30",
                       "identity_manifest_sha256",
                       "discovery_receipt_sha256",
                       "title_scoped_views_not_stable_page_id_history"):
            self.assertIn(needle, text)
        self.assertIn("coverage != Counter({(edition, subject): 3", text)

    def test_requires_1050_observed_days_and_reproducible_visitor_html(self):
        text = self.views
        for needle in ("python -m tools.rolling_pageview_source collect",
                       "python -m tools.rolling_pageview_source verify",
                       "python -m tools.rolling_pageview_source stage",
                       "python -m tools.rolling_snapshot_preview --from-stage",
                       "sum(len(s['daily']) for s in candidate['series']) != 1050",
                       "len(receipt['sources']) != 30",
                       "atlas.cards != 30", "len(atlas.details) != 30",
                       "atlas.links != atlas.details",
                       "Non-deterministic 30-title visitor build",
                       "LOCAL_PREVIEW_NOT_PUBLISHED",
                       "LOCAL_CANDIDATE_ONLY_NOT_PUBLISHED"):
            self.assertIn(needle, text)

    def test_no_publishing_or_trust_upgrade_on_provider_failure(self):
        text = self.full
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("pages: write", text)
        self.assertNotIn("git push", text)
        self.assertNotIn("deploy-pages@", text)
        self.assertNotIn("pull_request_target:", text)
        self.assertIn("if: success()\n        uses: actions/upload-artifact@v4", self.views)
        self.assertIn("retention-days: 30", self.views)
        # Read-only identity evidence and source-derived pageviews are retained
        # long enough for later-run review; the unrelated manual followup stays 7 days.
        self.assertEqual(self.source.count("retention-days: 30"), 1)
        self.assertEqual(self.source.count("retention-days: 7"), 1)
        self.assertEqual(self.views.count("retention-days: 30"), 1)
        self.assertNotIn("retention-days: 7", self.views)
        self.assertNotIn("if: always()", self.views)
        self.assertIn("UNPUBLISHED_SOURCE_REVIEW_REQUIRED", self.views)

    def test_embedded_python_blocks_compile_without_execution(self):
        import re
        import textwrap
        scripts = re.findall(r"^          python - <<'PY'\n(.*?)^          PY$",
                             self.views, flags=re.MULTILINE | re.DOTALL)
        self.assertEqual(len(scripts), 2)
        for index, script in enumerate(scripts):
            with self.subTest(index=index):
                compile(textwrap.dedent(script), "m1-30-inline.py", "exec")

    def test_real_30_title_html_chromium_gate_before_artifact_upload(self):
        text = self.views
        browser = text.index("name: Check generated 30-title HTML with Chromium before retention")
        retain = text.index("name: Retain validated raw provenance, local HTML and browser screenshots")
        self.assertLess(browser, retain)
        self.assertIn("python -m pip install playwright==1.55.0", text)
        self.assertIn("python -m playwright install --with-deps chromium", text)
        self.assertIn("python tests/m1/browser_30_source_artifact.py artifacts/m1-30-preview artifacts/m1-30-browser", text)
        self.assertIn("artifacts/m1-30-browser/", text)
        self.assertIn("if: success()\n        uses: actions/upload-artifact@v4", text)
        script = (ROOT / "tests/m1/browser_30_source_artifact.py").read_text(encoding="utf-8")
        for needle in ("ThreadingHTTPServer", "page.goto(", "320, False",
                       "390, True", "1280, False", "1050",
                       'geometry["document"] <= geometry["viewport"]',
                       'assert not geometry["overflowingTitles"]',
                       "LOCAL_PREVIEW_NOT_PUBLISHED", "NOT_PUBLISHED_NOT_LIVE_VERIFIED"):
            self.assertIn(needle, script)

    def test_existing_manual_followup_still_20_ids_and_unmodified(self):
        self.assertIn("seed_for_same_ids(baseline, receipt['followup_observed_utc'])", self.source)
        self.assertIn("assert len(seed['pages']) == 20", self.source)
        self.assertIn("if: ${{ github.event_name == 'workflow_dispatch' && inputs.task == 'stable-id-followup' }}", self.source)
        self.assertIn("followup:\n", self.source)


if __name__ == "__main__":
    unittest.main()
