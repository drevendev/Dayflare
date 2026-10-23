"""Entirely fictional raw bodies and receipts. No Wikimedia requests."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.m1_bundle_verify import make_manifest_for_complete, verify_bundle
from tools.m1_source_verify import verify_sources
from tools.m1_collect import collect_to_new_directory, SEED_SCHEMA
from tools.m1_identity_panel import PanelError, canonical_bytes


class BundleVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed_path = self.root / "seed.json"
        self.seed_path.write_bytes(canonical_bytes({
            "schema_version": SEED_SCHEMA,
            "panel_id": "test.enru.20261021",
            "selected_at": "2026-10-21",
            "pages": [
                {"page_ref": {"project": "en.wikipedia", "page_id": 17},
                 "topic_id": "test.science", "subject": "science", "relation": "ambiguous"},
                {"page_ref": {"project": "ru.wikipedia", "page_id": 801},
                 "topic_id": "test.books", "subject": "books", "relation": "ambiguous"},
            ],
        }))
        self.output = self.root / "bundle"
        self.now = lambda: datetime(2026,10,21,10,0,tzinfo=timezone.utc)
        def fake_http(url):
            is_ru = "ru.wikipedia" in url
            row = {"pageid": 801 if is_ru else 17, "ns": 0,
                   "title": "Тестовая книга" if is_ru else "Test science"}
            row["pageprops"] = {"wikibase_item": "Q123" if is_ru else "Q42"}
            return 200, canonical_bytes({"batchcomplete": True, "query": {"pages": [row]}})
        self.fake_http = fake_http
        collect_to_new_directory(self.seed_path, self.output, fetch=self.fake_http,
                                 now=self.now, sleep=lambda _: None)

    def reject(self, fragment):
        with self.assertRaises(PanelError) as raised:
            verify_bundle(self.output)
        self.assertIn(fragment, str(raised.exception))

    def resign_manifest(self):
        path = self.output / "bundle-manifest.json"
        current = json.loads(path.read_text())
        # Deliberately recompute the manifest after tampering. The verifier must
        # still reject semantic receipt/report inconsistencies.
        panel = json.loads((self.output / "panel.json").read_text())
        path.write_bytes(canonical_bytes(make_manifest_for_complete(self.output, panel)))

    def test_valid_bundle_and_manifest_deterministic(self):
        first = verify_bundle(self.output)
        self.assertEqual(first["verified_pages"], 2)
        self.assertEqual(first["result"], "bundle_structurally_and_internally_consistent")
        self.assertEqual(first["observed_bytes"],
                         sum(path.stat().st_size for path in (self.output / "raw").iterdir()))
        self.assertEqual(canonical_bytes(first), canonical_bytes(verify_bundle(self.output)))
        self.assertEqual(json.loads((self.output / "bundle-manifest.json").read_text())["schema_version"],
                         "dayflare.identity-bundle.v1")

    def test_extra_raw_body_denied(self):
        (self.output / "raw" / "en.wikipedia.99999.json").write_bytes(b"{}")
        self.reject("unlisted raw members")

    def test_extra_root_file_denied(self):
        (self.output / "private.txt").write_text("SHOULD NOT LEAK")
        self.reject("unlisted bundle members")

    def test_extra_directory_denied(self):
        (self.output / "raw" / "other").mkdir()
        self.reject("unlisted raw members")

    def test_symlink_raw_directory_denied(self):
        external = self.root / "raw_copy"
        (self.output / "raw").rename(external)
        (self.output / "raw").symlink_to(external, target_is_directory=True)
        self.reject("symlink forbidden")

    def test_raw_tampering_detected(self):
        file = self.output / "raw" / "en.wikipedia.17.json"
        file.write_bytes(file.read_bytes() + b"\n")
        self.reject("manifest hash")

    def test_manifest_tampering_denied(self):
        file = self.output / "bundle-manifest.json"
        manifest = json.loads(file.read_text())
        manifest["files"]["panel.json"]["bytes"] += 1
        file.write_bytes(canonical_bytes(manifest))
        self.reject("manifest hash")

    def test_forged_report_count_denied_even_if_manifest_updated(self):
        file = self.output / "collection-report.json"
        data = json.loads(file.read_text())
        data["retained_count"] -= 1
        file.write_bytes(canonical_bytes(data))
        self.resign_manifest()
        self.reject("retained/unavailable totals mismatch")

    def test_forged_transferred_byte_count_denied_even_if_manifest_updated(self):
        file = self.output / "collection-report.json"
        data = json.loads(file.read_text())
        data["transferred_bytes"] += 1
        file.write_bytes(canonical_bytes(data))
        self.resign_manifest()
        self.reject("transferred bytes disagree")

    def test_mismatched_consistency_result_denied_with_updated_manifest(self):
        file = self.output / "internal-consistency.json"
        data = json.loads(file.read_text())
        data["verified_page_count"] += 1
        file.write_bytes(canonical_bytes(data))
        self.resign_manifest()
        self.reject("internal consistency result")

    def test_attempt_scope_is_independently_tied_to_retained_page(self):
        path = self.output / "collection-report.json"
        report = json.loads(path.read_text())
        report["attempts"][0]["topic_id"] = "other.unrelated"
        path.write_bytes(canonical_bytes(report))
        self.resign_manifest()
        self.reject("retained attempt scope disagrees")

    def test_forged_intended_coverage_denied_even_after_rehash(self):
        path = self.output / "collection-report.json"
        report = json.loads(path.read_text())
        report["intended_by_edition_subject"] = {"en.wikipedia": {"games": 2}}
        path.write_bytes(canonical_bytes(report))
        self.resign_manifest()
        self.reject("intended coverage disagrees with attempts")

    def test_report_date_tampering_rejected_after_rehash(self):
        path = self.output / "collection-report.json"
        report = json.loads(path.read_text())
        report["selected_at"] = "2026-10-20"
        path.write_bytes(canonical_bytes(report))
        self.resign_manifest()
        self.reject("selection date mismatch")

    def test_retrieval_before_curated_selection_denied_after_forged_rehash(self):
        # All local records are made mutually consistent and rehashed, but their
        # claimed retrieval precedes the panel's own selection date.
        panel_path = self.output / "panel.json"
        report_path = self.output / "collection-report.json"
        panel = json.loads(panel_path.read_text())
        report = json.loads(report_path.read_text())
        for page in panel["pages"]:
            page["source"]["requested_at"] = "2026-10-20T10:00:00Z"
            page["titles"][0]["date"] = "2026-10-20"
        for attempt in report["attempts"]:
            attempt["requested_at"] = "2026-10-20T10:00:00Z"
        panel_path.write_bytes(canonical_bytes(panel))
        report_path.write_bytes(canonical_bytes(report))
        proof = verify_sources(panel_path, self.output / "raw")
        (self.output / "internal-consistency.json").write_bytes(canonical_bytes(proof))
        self.resign_manifest()
        self.reject("retrieval predates curated selection")

    def make_partial_bundle(self):
        partial = self.root / "partial"
        def fake_with_missing(url):
            if "ru.wikipedia" in url:
                return 200, canonical_bytes({"query": {"pages": [{
                    "pageid": 801, "ns": 0, "title": "Missing page", "missing": True,
                }]}})
            return self.fake_http(url)
        collect_to_new_directory(self.seed_path, partial, fetch=fake_with_missing,
                                 now=self.now, sleep=lambda _: None)
        self.output = partial
        report = json.loads((partial / "collection-report.json").read_text())
        self.assertEqual(report["retained_count"], 1)
        self.assertEqual(report["unavailable_count"], 1)
        self.assertEqual(verify_bundle(partial)["verified_pages"], 1)

    def test_unavailable_identity_keeps_intended_edition_subject(self):
        self.make_partial_bundle()
        report = json.loads((self.output / "collection-report.json").read_text())
        self.assertEqual(report["intended_by_edition_subject"], {
            "en.wikipedia": {"science": 1}, "ru.wikipedia": {"books": 1}})
        self.assertEqual(report["obtained_by_edition_subject"], {"en.wikipedia": {"science": 1}})
        self.assertEqual(report["attempts"][-1]["reason"], "invalid_or_missing_identity")

    def test_tampered_unavailable_scope_cannot_fake_coverage(self):
        self.make_partial_bundle()
        path = self.output / "collection-report.json"
        report = json.loads(path.read_text())
        report["attempts"][-1]["subject"] = "science"
        path.write_bytes(canonical_bytes(report))
        self.resign_manifest()
        self.reject("intended coverage disagrees with attempts")

    def test_unavailable_attempt_must_preserve_url_and_failure_reason(self):
        self.make_partial_bundle()
        path = self.output / "collection-report.json"
        original = json.loads(path.read_text())
        wrong_url = json.loads(path.read_text())
        wrong_url["attempts"][-1]["endpoint"] = "https://en.wikipedia.org/w/api.php?action=query"
        path.write_bytes(canonical_bytes(wrong_url))
        self.resign_manifest()
        self.reject("expected exact Wikipedia Action API origin")
        missing_reason = json.loads(json.dumps(original))
        missing_reason["attempts"][-1].pop("reason")
        path.write_bytes(canonical_bytes(missing_reason))
        self.resign_manifest()
        self.reject("missing fields")

    def test_extra_unverified_report_claim_is_not_accepted(self):
        path = self.output / "collection-report.json"
        report = json.loads(path.read_text())
        report["verified_humans"] = True
        path.write_bytes(canonical_bytes(report))
        self.resign_manifest()
        self.reject("unrecognized fields")

    def test_cli_accepts_clean_and_rejects_altered_bundle(self):
        cmd = [sys.executable, "-m", "tools.m1_bundle_verify", str(self.output)]
        valid = subprocess.run(cmd, capture_output=True, cwd=Path(__file__).parents[1])
        self.assertEqual(valid.returncode, 0, valid.stderr.decode())
        self.assertEqual(json.loads(valid.stdout)["verified_pages"], 2)
        (self.output / "raw" / "junk.json").write_text("{}");
        invalid = subprocess.run(cmd, capture_output=True, cwd=Path(__file__).parents[1])
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(invalid.stdout, b"")
        self.assertIn(b"BUNDLE_INVALID", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
