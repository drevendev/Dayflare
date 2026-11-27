"""Offline controls; these fixture IDs are synthetic and not measurements."""
import copy
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.m1_additional_coverage import ROOT, SEED, gate, load
from tools.m1_title_discovery import validate_curated


class AdditionalCoverageTests(unittest.TestCase):
    def setUp(self):
        self.curated = load(SEED)
        self.rows = validate_curated(self.curated, date(2026, 11, 27))
        self.report = dict(requested_count=10, candidate_count=10, excluded_count=0,
                           attempts=[dict(project=r['project'], requested_title=r['title'],
                                          page_id=i, status='candidate')
                                     for i, r in enumerate(self.rows, 1)])
        self.selected = [dict(project=r['project'], title=r['title'], subject=r['subject'],
                              page_id=i) for i, r in enumerate(self.rows, 1)]
        self.handoff = dict(candidate_count=10, excluded_count=0,
                            metric_scope='title_scoped_views_not_stable_page_id_history')

    def test_distinct_editorial_cohort(self):
        self.assertEqual(len(self.rows), 10)
        self.assertTrue(all(r['relation'] == 'ambiguous' for r in self.rows))
        for prior in ('m1_curated_expanded_30_enru.json', 'm1_curated_niche_20_enru.json'):
            old = load(ROOT / 'examples' / prior)['pages']
            self.assertFalse({(r['project'], r['title']) for r in old} &
                             {(r['project'], r['title']) for r in self.rows})
            self.assertFalse({r['topic_id'] for r in old} & {r['topic_id'] for r in self.rows})

    def test_complete_gate(self):
        gate(self.curated, self.report, self.selected, self.handoff)

    def test_missing_redirect_and_identity_mismatch(self):
        report = copy.deepcopy(self.report)
        report['attempts'][0]['status'] = 'excluded'
        with self.assertRaises(ValueError):
            gate(self.curated, report, self.selected, self.handoff)
        for field, bad in (('page_id', 999), ('title', 'Unrelated'), ('subject', 'other')):
            selected = copy.deepcopy(self.selected)
            selected[0][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                gate(self.curated, self.report, selected, self.handoff)
        with self.assertRaises(ValueError):
            gate(self.curated, self.report, self.selected[:-1], self.handoff)

    def test_duplicate_id_and_wrong_scope(self):
        report = copy.deepcopy(self.report)
        selected = copy.deepcopy(self.selected)
        report['attempts'][1]['page_id'] = report['attempts'][0]['page_id']
        selected[1]['page_id'] = selected[0]['page_id']
        with self.assertRaises(ValueError):
            gate(self.curated, report, selected, self.handoff)
        with self.assertRaises(ValueError):
            gate(self.curated, self.report, self.selected,
                 dict(self.handoff, metric_scope='historical_identity'))

    def test_all_excluded_discovery_retains_replay_without_collection_seed(self):
        from tools import m1_title_discovery as discovery
        raw = discovery.canonical({"batchcomplete": True, "query": {
            "pages": [{"missing": True}]}})
        clock = lambda: datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
        real_discover = discovery.discover
        def synthetic(doc, **kwargs):
            return real_discover(doc, fetch=lambda _: raw, clock=clock,
                                 sleep=lambda _: None, **kwargs)
        with self.assertRaisesRegex(discovery.DiscoveryError, "no unambiguous"):
            synthetic(self.curated)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "excluded"
            with patch.object(discovery, "discover", side_effect=lambda doc, **kw:
                    synthetic(doc, **kw) if "fetch" not in kw else real_discover(doc, **kw)):
                receipt = discovery.run(SEED, out, retain_exclusions=True)
            self.assertEqual(receipt["candidate_count"], 0)
            self.assertEqual(receipt["excluded_count"], 10)
            self.assertEqual(receipt["status"], "LOCAL_ONLY_ALL_TITLES_EXCLUDED_NO_SEEDS")
            self.assertEqual(len(list((out / "raw").iterdir())), 10)
            self.assertFalse((out / "identity-seeds.json").exists())
            self.assertEqual(discovery.verify(SEED, out, retain_exclusions=True), receipt)
            with self.assertRaises(discovery.DiscoveryError):
                discovery.verify(SEED, out)
            (out / "identity-seeds.json").write_bytes(b"null")
            with self.assertRaises(discovery.DiscoveryError):
                discovery.verify(SEED, out, retain_exclusions=True)
            (out / "identity-seeds.json").unlink()
            (out / "raw/00.json").write_bytes(b"{}")
            with self.assertRaises(discovery.DiscoveryError):
                discovery.verify(SEED, out, retain_exclusions=True)

    def test_all_excluded_independent_handoff_does_not_export_seeds(self):
        from tools import m1_pageview_handoff as handoff
        panel = {"panel_id": "panel.test", "selection": {"evidence_kind": "reported_retrieval"},
                 "pages": [
                     {"page_ref": {"project": row["project"], "page_id": i},
                      "titles": [{"title": row["title"], "date": "2026-11-27"}],
                      "source": {"requested_at": "2026-11-27T08:00:00Z"},
                      "subject": row["subject"], "continuity": "ambiguous",
                      "redirect_to": {"target_ref": {"project": row["project"], "page_id": 100+i}},
                      "events": []}
                     for i, row in enumerate(self.rows, 1)]}
        proof = {"result": "bundle_structurally_and_internally_consistent",
                 "panel_id": "panel.test", "manifest_sha256": "e"*64}
        with tempfile.TemporaryDirectory() as tmp:
            identity = Path(tmp) / "verified-identity"
            identity.mkdir()
            marker = identity / "panel.json"
            marker.write_text("synthetic fixture marker")
            out = Path(tmp) / "handoff"
            with patch("tools.m1_bundle_verify.verify_bundle", return_value=proof), \
                 patch("tools.m1_identity_panel.load_panel", return_value=panel):
                with self.assertRaisesRegex(handoff.HandoffError, "no eligible"):
                    handoff.export(identity, out, today=date(2026, 11, 27))
            self.assertFalse(out.exists())
            self.assertEqual(marker.read_text(), "synthetic fixture marker")

    def test_workflow_is_master_only_and_read_only(self):
        text = (ROOT / '.github/workflows/m1-additional-coverage.yml').read_text()
        self.assertIn("if: github.ref == 'refs/heads/master'", text)
        self.assertIn('contents: read', text)
        self.assertIn('persist-credentials: false', text)
        self.assertNotIn('schedule:', text)
        self.assertNotIn('pull_request:', text)
        self.assertNotIn('contents: write', text)
        self.assertLess(text.index('Preserve discovery including exclusions'), text.index('Stop if discovery returned only exclusions'))
        self.assertLess(text.index('test -s artifacts/additional-title/identity-seeds.json'), text.index('python -m tools.m1_collect'))
        self.assertLess(text.index('python -m tools.m1_bundle_verify'), text.index('Preserve independently re-queried identity before handoff'))
        self.assertLess(text.index('Preserve independently re-queried identity before handoff'), text.index('python -m tools.m1_pageview_handoff'))
        self.assertLess(text.index('python -m tools.m1_pageview_handoff'), text.index('m1_additional_coverage gate'))
        self.assertLess(text.index('m1_additional_coverage gate'), text.index('rolling_pageview_source collect'))
        self.assertNotIn('continue-on-error', text)
        self.assertLess(text.index('rolling_pageview_source verify artifacts/'), text.index('rolling_snapshot_preview artifacts/'))
