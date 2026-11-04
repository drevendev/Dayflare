"""Offline regression acceptance for the D03 snapshot comparison (synthetic controls)."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from tools.m1_identity_history import compare_bytes, render_html, write_bundle, main, SCHEMA
from tools.m1_identity_history_demo import example_panels, SOURCE
from tools.m1_identity_panel import canonical_bytes, PanelError, MAX_BYTES


class IdentityHistoryTests(unittest.TestCase):
    def setUp(self):
        self.before, self.after = example_panels()

    def report(self):
        return compare_bytes(canonical_bytes(self.before), canonical_bytes(self.after))

    def row(self, project, pid):
        return next(row for row in self.report()["pages"]
                    if row["page_ref"] == {"project": project, "page_id": pid})

    def test_stable_refs_do_not_merge_equal_titles_or_cross_editions(self):
        report = self.report()
        self.assertEqual(report["summary"]["identities_in_union"], 7)
        self.assertEqual(report["summary"]["observed_in_both"], 5)
        self.assertEqual(report["summary"]["only_before"], 1)
        self.assertEqual(report["summary"]["only_after"], 1)
        self.assertIn("not_observed_after", self.row("en.wikipedia", 4)["changes"])
        self.assertIn("not_observed_before", self.row("en.wikipedia", 5)["changes"])
        self.assertIn("unchanged_observation", self.row("ru.wikipedia", 1)["changes"])

    def test_move_is_reported_not_assumed_continuity(self):
        row = self.row("en.wikipedia", 1)
        self.assertEqual(row["changes"], ["move_reported", "title_changed"])
        self.assertEqual(row["continuity"], "unverified_between_observations")
        self.assertFalse(row["pageview_join_allowed"])
        self.after["pages"][0]["events"] = []
        self.assertEqual(self.row("en.wikipedia", 1)["changes"], ["title_changed"])

    def test_delete_restore_boundary_and_omitted_old_event_are_preserved(self):
        row = self.row("ru.wikipedia", 2)
        self.assertIn("delete_restore_boundary", row["changes"])
        self.assertEqual(row["continuity"], "boundary_present")
        self.before["pages"][4]["events"] = [{"date": "2026-09-30", "kind": "restore", "source_url": SOURCE}]
        self.assertEqual(self.row("ru.wikipedia", 1)["continuity"], "boundary_present")

    def test_redirect_is_a_separate_edge_and_never_aggregates_views(self):
        row = self.row("en.wikipedia", 3)
        self.assertIn("redirect_changed", row["changes"])
        self.assertEqual(row["after"]["redirect_to"]["target_ref"]["page_id"], 1)
        self.assertTrue(all(not row["pageview_join_allowed"] for row in self.report()["pages"]))

    def test_observed_and_resolved_qids_are_not_rewritten_or_joined(self):
        row = self.row("en.wikipedia", 2)
        self.assertIn("mapping_changed", row["changes"])
        self.assertIn("mapping_collision", row["changes"])
        self.assertEqual(row["before"]["wikidata"]["observed_qid"], "Q102")
        self.assertEqual(row["after"]["wikidata"]["observed_qid"], "Q103")
        self.assertIsNone(row["after"]["wikidata"]["resolved_qid"])

    def test_same_title_same_qid_different_id_still_separate(self):
        self.after["pages"][3]["wikidata"] = deepcopy(self.before["pages"][3]["wikidata"])
        self.assertEqual(self.report()["summary"]["only_after"], 1)

    def test_conflicting_retained_history_is_explicit(self):
        self.after["pages"][0]["titles"][0]["title"] = "Contradictory old title"
        row = self.row("en.wikipedia", 1)
        self.assertIn("conflicting_title_history", row["changes"])
        self.assertEqual(row["continuity"], "conflicting_evidence")

    def test_editorial_reassignment_is_not_identity_replacement(self):
        self.after["pages"][4]["topic_id"] = "another-topic"
        self.after["pages"][4]["relation"] = "narrower"
        self.assertIn("topic_assignment_changed", self.row("ru.wikipedia", 1)["changes"])
        self.assertEqual(self.report()["summary"]["observed_in_both"], 5)

    def test_no_input_mutation(self):
        before, after = deepcopy(self.before), deepcopy(self.after)
        self.report()
        self.assertEqual((self.before, self.after), (before, after))

    def test_output_determinism_and_exact_input_hashes(self):
        first, second = self.report(), self.report()
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        self.assertEqual(render_html(first), render_html(second))
        self.assertEqual(first["inputs"][0]["input_sha256"], sha256(canonical_bytes(self.before)).hexdigest())
        self.assertEqual(first["schema_version"], SCHEMA)
        self.assertIn("synthetic", first["evidence_kind"])

    def test_iteration_order_does_not_change_rows(self):
        expected = self.report()["pages"]
        self.before["pages"].reverse()
        self.after["pages"].reverse()
        self.assertEqual(self.report()["pages"], expected)

    def test_partial_selection_is_counted_without_zero_interest(self):
        self.before["selection"]["intended_count"] = 20
        report = self.report()
        self.assertEqual(report["inputs"][0]["coverage"]["unresolved_count"], 14)
        self.assertNotIn("views", report["summary"])

    def test_same_day_reverse_and_empty_snapshots_are_rejected(self):
        raw = canonical_bytes(self.before)
        for first, second in [(raw, raw), (canonical_bytes(self.after), raw)]:
            with self.assertRaises(PanelError):
                compare_bytes(first, second)
        self.before["pages"] = []
        with self.assertRaises(PanelError):
            self.report()

    def test_mixed_observation_days_and_future_events_are_rejected(self):
        self.after["pages"][0]["titles"][-1]["date"] = "2026-10-09"
        with self.assertRaises(PanelError):
            self.report()
        self.after = example_panels()[1]
        self.after["pages"][0]["events"][0]["date"] = "2026-10-09"
        with self.assertRaises(PanelError):
            self.report()

    def test_future_observation_and_invalid_schema_are_rejected(self):
        self.after["schema_version"] = "unknown"
        with self.assertRaises(PanelError):
            self.report()
        self.after = example_panels()[1]
        for row in self.after["pages"]:
            row["titles"][-1]["date"] = "2999-01-01"
        with self.assertRaises(PanelError):
            self.report()

    def test_mixed_synthetic_and_reported_inputs_are_rejected(self):
        self.after["selection"]["evidence_kind"] = "reported_retrieval"
        for row in self.after["pages"]:
            row["source"] = {"endpoint": "https://en.wikipedia.org/w/api.php", "requested_at": "2026-10-08T12:00:00Z",
                             "http_status": 200, "body_sha256": "a" * 64, "response_bytes": 1}
        with self.assertRaisesRegex(PanelError, "cannot be mixed"):
            self.report()

    def test_malformed_duplicate_nonfinite_and_oversized_inputs(self):
        for raw in [b"{", b"\xff", b'{"x":1,"x":2}', b'{"x":NaN}', b" " * (MAX_BYTES + 1), b""]:
            with self.subTest(raw=raw[:40]), self.assertRaises(PanelError):
                compare_bytes(raw, canonical_bytes(self.after))

    def test_invalid_ids_duplicates_and_source_urls_are_rejected(self):
        for field, value in [("page_ref", {"project": "en.wikipedia", "page_id": True}),
                             ("titles", [{"date": "2026-10-01", "title": "Bad", "source_url": "javascript:alert(1)"}])]:
            before = deepcopy(self.before)
            before["pages"][0][field] = value
            with self.assertRaises(PanelError):
                compare_bytes(canonical_bytes(before), canonical_bytes(self.after))
        self.before["pages"][1]["page_ref"] = deepcopy(self.before["pages"][0]["page_ref"])
        with self.assertRaises(PanelError):
            self.report()

    def test_html_escapes_titles_and_contains_no_remote_executables(self):
        self.after["pages"][0]["titles"][-1]["title"] = '<script>alert("x")</script>'
        html = render_html(self.report()).decode()
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("<iframe", html)
        self.assertIn("SYNTHETIC DEMONSTRATION", html)
        self.assertIn("not real Wikipedia changes", html)
        self.assertIn("history.json", html)
        self.assertIn("manifest.json", html)
        self.assertIn("Exact observations and retained evidence", html)

    def test_report_anchors_change_with_input_version(self):
        first = self.report()
        self.after["pages"][0]["titles"][-1]["title"] = "Another title"
        second = self.report()
        self.assertNotEqual(first["report_id"], second["report_id"])
        self.assertIn(first["report_id"], render_html(first).decode())

    def test_immutable_bundle_manifest_and_double_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before, after = root / "before.json", root / "after.json"
            before.write_bytes(canonical_bytes(self.before)); after.write_bytes(canonical_bytes(self.after))
            first, second = root / "first", root / "second"
            manifest = write_bundle(before, after, first)
            write_bundle(before, after, second)
            for name in ("history.json", "index.html", "manifest.json"):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            for name, expected in manifest["files"].items():
                self.assertEqual(sha256((first / name).read_bytes()).hexdigest(), expected)
            original = (first / "history.json").read_bytes()
            with self.assertRaises(FileExistsError):
                write_bundle(before, after, first)
            self.assertEqual((first / "history.json").read_bytes(), original)
            after.write_text("invalid", encoding="utf-8")
            self.assertEqual(main([str(before), str(after), str(root / "bad")]), 2)
            self.assertFalse((root / "bad").exists())
            self.assertEqual((first / "history.json").read_bytes(), original)

    def test_concurrent_bundle_writers_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before, after, output = root / "before.json", root / "after.json", root / "output"
            before.write_bytes(canonical_bytes(self.before)); after.write_bytes(canonical_bytes(self.after))
            def attempt(_):
                try:
                    write_bundle(before, after, output)
                    return "built"
                except FileExistsError:
                    return "preserved"
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sorted(pool.map(attempt, range(2))), ["built", "preserved"])
            self.assertTrue((output / "manifest.json").is_file())

    def test_symlink_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, link = root / "source.json", root / "link.json"
            source.write_bytes(canonical_bytes(self.before)); link.symlink_to(source)
            with self.assertRaises(PanelError):
                write_bundle(link, source, root / "output")

    def test_partial_io_failure_does_not_leave_a_complete_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before, after, output = root / "before.json", root / "after.json", root / "output"
            before.write_bytes(canonical_bytes(self.before)); after.write_bytes(canonical_bytes(self.after))
            original = Path.open
            def failing(path, *args, **kwargs):
                if path.name == "index.html":
                    raise OSError("simulated disk failure")
                return original(path, *args, **kwargs)
            with patch.object(Path, "open", failing), self.assertRaises(OSError):
                write_bundle(before, after, output)
            self.assertFalse((output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
