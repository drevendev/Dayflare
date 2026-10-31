"""Synthetic injected transport ONLY: these tests do not establish source origin."""
from __future__ import annotations

from datetime import datetime, date, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.rolling_pageview_source import (
    FetchResult, SourceError, build, canonical, collect_to_new_directory,
    decode_entity, endpoint, parse_pageviews, sha, strict_json, verify_bundle,
)

NOW = datetime(2026, 10, 24, 3, 1, 2, tzinfo=timezone.utc)
END = date(2026, 10, 21)
START = END - timedelta(days=34)


def seeds():
    return {"schema_version": "dayflare.rolling-pageview-seeds.v1",
            "selected_at": "2026-10-20", "method_version": "v0-empirical-35d",
            "provider_lag_days": 2,
            "pages": [
                {"project": "en.wikipedia", "page_id": 1234, "title": "Chess", "subject": "sport"},
                {"project": "ru.wikipedia", "page_id": 5678, "title": "Книга", "subject": "books"},
            ]}


def body(project="en.wikipedia", title="Chess", n=35):
    return canonical({"items": [{"project": project, "article": title,
                                   "access": "all-access", "agent": "user", "granularity": "daily",
                                   "timestamp": (START + timedelta(days=i)).strftime("%Y%m%d00"),
                                   "views": 0 if i == 0 else 100 + i}
                                  for i in range(n)]})


def fake(url):
    if "/en.wikipedia.org/" in url:
        raw = body()
    else:
        raw = body("ru.wikipedia", "Книга")
    return FetchResult(200, raw, len(raw), sha(raw), "identity")


class RollingSourceTests(unittest.TestCase):
    def test_success_injected_bounded_complete_and_zero(self):
        candidate, receipt, bodies = build(seeds(), now=lambda: NOW, fetch=fake, sleep=lambda _: None, injected=True)
        self.assertEqual(candidate["observation_end"], "2026-10-21")
        self.assertEqual(len(bodies), 2)
        self.assertEqual(candidate["series"][0]["daily"][0]["views"], 0)
        self.assertEqual(receipt["requests_attempted"], 2)
        self.assertEqual(receipt["provenance_status"], "synthetic_injected_not_upstream_evidence")
        self.assertEqual(receipt["candidate_sha256"], sha(canonical(candidate)))
        self.assertEqual(candidate["series"][0]["source"]["endpoint"],
                         endpoint("en.wikipedia", "Chess", START, END))

    def test_end_to_end_retained_bytes_and_offline_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_path = root / "seeds-input.json"
            seed_path.write_bytes(canonical(seeds()))
            target = root / "evidence"
            result = collect_to_new_directory(seed_path, target, now=lambda: NOW, fetch=fake,
                                              sleep=lambda _: None, injected=True)
            self.assertEqual(result["observations"], 70)
            self.assertEqual(result["provenance_status"], "synthetic_injected_not_upstream_evidence")
            self.assertEqual(verify_bundle(target, now=NOW)["result"],
                             "all_retained_bodies_internally_consistent")
            with self.assertRaisesRegex(SourceError, "already exists"):
                collect_to_new_directory(seed_path, target, now=lambda: NOW, fetch=fake,
                                         sleep=lambda _: None, injected=True)

    def test_source_verified_stage_refuses_candidate_swap_after_check(self):
        # A valid but unrelated candidate must not replace the source-checked
        # bytes between retained-body verification and local pointer promotion.
        from unittest import mock
        from tools.rolling_pageview_source import stage_verified_bundle
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_path = root / "seed.json"
            seed_path.write_bytes(canonical(seeds()))
            source = root / "evidence"
            # A simulated non-injected transport exercises the positive path;
            # it is not independent evidence of a real Wikimedia request.
            collect_to_new_directory(seed_path, source, now=lambda: NOW, fetch=fake,
                                     sleep=lambda _: None, injected=False)
            valid = stage_verified_bundle(source, root / "normal-stage", now=NOW)
            self.assertEqual(valid["source_bundle"]["candidate_sha256"],
                             valid["local_stage"]["version_sha256"])
            self.assertEqual(valid["local_stage"]["result"], "PROMOTED_LOCAL_CANDIDATE_ONLY")

            verified = verify_bundle
            def swap_after_source_check(bundle, *, now=None):
                proof = verified(bundle, now=now)
                candidate_path = Path(bundle) / "candidate.json"
                changed = json.loads(candidate_path.read_text())
                changed["dataset_id"] = "unverified-swap"
                changed["series"][0]["daily"][0]["views"] = 999
                candidate_path.write_bytes(canonical(changed))
                return proof

            rejected_stage = root / "rejected-stage"
            with mock.patch("tools.rolling_pageview_source.verify_bundle",
                            side_effect=swap_after_source_check):
                with self.assertRaisesRegex(SourceError,
                                            "candidate changed after source verification"):
                    stage_verified_bundle(source, rejected_stage, now=NOW)
            self.assertFalse(rejected_stage.exists())

    def test_source_bound_stage_preserves_receipts_after_original_evidence_is_removed(self):
        from tools.rolling_pageview_source import stage_verified_bundle
        from tools.stage_rolling_version import StageError, _current
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_path = root / "seed.json"
            seed_path.write_bytes(canonical(seeds()))
            source = root / "evidence"
            # Simulated non-injected transport exercises persistence only,
            # NOT authenticity of a real Wikimedia response.
            collect_to_new_directory(seed_path, source, now=lambda: NOW, fetch=fake,
                                     sleep=lambda _: None, injected=False)
            stage_root = root / "stage"
            result = stage_verified_bundle(source, stage_root, now=NOW)
            digest = result["local_stage"]["version_sha256"]
            version = stage_root / "versions" / digest
            manifest = json.loads((version / "manifest.json").read_bytes())
            retained = version / "source"
            self.assertEqual(manifest["schema_version"], "dayflare.rolling-stage.v2")
            self.assertEqual(manifest["source_receipt_sha256"],
                             sha((source / "source-receipt.json").read_bytes()))
            self.assertEqual(manifest["source_provenance_status"],
                             "runtime_reported_transport_not_independently_authenticated")
            self.assertEqual((retained / "raw" / "en.wikipedia.1234.json").read_bytes(),
                             (source / "raw" / "en.wikipedia.1234.json").read_bytes())
            pointer = (stage_root / "current.json").read_bytes()
            shutil.rmtree(source)
            self.assertEqual(_current(stage_root)["version_sha256"], digest)
            (retained / "raw" / "en.wikipedia.1234.json").write_bytes(b'{}\\n')
            with self.assertRaisesRegex(StageError, "stored source bundle failed"):
                _current(stage_root)
            self.assertEqual((stage_root / "current.json").read_bytes(), pointer)

    def test_source_backed_stage_rejects_unverified_newer_revision(self):
        # The transport is simulated, not proof of Wikimedia origin. Its
        # retained-body v2 stage still must not regress to a source-less v1.
        from tools.rolling_pageview_source import stage_verified_bundle
        from tools.stage_rolling_version import StageError, _current, stage
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_path = root / "seed.json"
            seed_path.write_bytes(canonical(seeds()))
            source = root / "first-source"
            collect_to_new_directory(seed_path, source, now=lambda: NOW,
                                     fetch=fake, sleep=lambda _: None, injected=False)
            stage_root = root / "stage"
            initial = stage_verified_bundle(source, stage_root, now=NOW)
            before_pointer = (stage_root / "current.json").read_bytes()
            before_versions = {p.name for p in (stage_root / "versions").iterdir()}

            later_time = NOW + timedelta(seconds=2)
            unverified = json.loads((source / "candidate.json").read_bytes())
            unverified["dataset_id"] = "source-less-newer-revision"
            unverified["retrieved_at"] = later_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            with self.assertRaisesRegex(StageError, "source-backed"):
                stage(unverified, stage_root, now=later_time)
            self.assertEqual((stage_root / "current.json").read_bytes(), before_pointer)
            self.assertEqual({p.name for p in (stage_root / "versions").iterdir()},
                             before_versions)
            self.assertEqual(_current(stage_root)["version_sha256"],
                             initial["local_stage"]["version_sha256"])

            # A genuinely retained-body successor still advances normally.
            second = root / "later-source"
            collect_to_new_directory(seed_path, second, now=lambda: later_time,
                                     fetch=fake, sleep=lambda _: None, injected=False)
            promoted = stage_verified_bundle(second, stage_root, now=later_time)
            self.assertEqual(promoted["local_stage"]["result"],
                             "PROMOTED_LOCAL_CANDIDATE_ONLY")
            self.assertNotEqual(promoted["local_stage"]["version_sha256"],
                                initial["local_stage"]["version_sha256"])
            self.assertEqual(_current(stage_root)["version_sha256"],
                             promoted["local_stage"]["version_sha256"])

    def test_source_changed_during_immutable_copy_leaves_no_current_pointer(self):
        from unittest import mock
        from tools.rolling_pageview_source import stage_verified_bundle
        from tools.stage_rolling_version import StageError, _write_once
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_path = root / "seed.json"
            seed_path.write_bytes(canonical(seeds()))
            source = root / "evidence"
            collect_to_new_directory(seed_path, source, now=lambda: NOW, fetch=fake,
                                     sleep=lambda _: None, injected=False)
            stage_root = root / "stage"
            def corrupt_original_after_receipt_copy(path, payload):
                _write_once(path, payload)
                if path.name == "source-receipt.json" and path.parent.name == "source":
                    (source / "raw" / "en.wikipedia.1234.json").write_bytes(b'{}\\n')
            with mock.patch("tools.stage_rolling_version._write_once",
                            side_effect=corrupt_original_after_receipt_copy):
                with self.assertRaisesRegex(StageError, "source changed during immutable staging"):
                    stage_verified_bundle(source, stage_root, now=NOW)
            self.assertFalse((stage_root / "current.json").exists())
            self.assertFalse(any((stage_root / "versions").iterdir()))

    def test_corrupt_copied_source_cannot_replace_last_valid_pointer(self):
        # A successful v2 stage must survive an interrupted/corrupted *later*
        # immutable source copy. Both transports here are simulated, not
        # evidence of a real Wikimedia response.
        from unittest import mock
        from tools.rolling_pageview_source import stage_verified_bundle
        from tools.stage_rolling_version import StageError, _current, _write_once
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_path = root / "seed.json"
            seed_path.write_bytes(canonical(seeds()))
            first = root / "accepted-source"
            collect_to_new_directory(seed_path, first, now=lambda: NOW, fetch=fake,
                                     sleep=lambda _: None, injected=False)
            stage_root = root / "stage"
            initial = stage_verified_bundle(first, stage_root, now=NOW)
            first_sha = initial["local_stage"]["version_sha256"]
            pointer_before = (stage_root / "current.json").read_bytes()
            versions_before = {p.name for p in (stage_root / "versions").iterdir()}
            self.assertEqual(_current(stage_root)["version_sha256"], first_sha)

            next_time = NOW + timedelta(seconds=1)
            second = root / "newer-source"
            collect_to_new_directory(seed_path, second, now=lambda: next_time, fetch=fake,
                                     sleep=lambda _: None, injected=False)
            self.assertNotEqual(sha((second / "candidate.json").read_bytes()), first_sha)

            def corrupt_retained_copy_after_write(path, payload):
                _write_once(path, payload)
                if path.name == "en.wikipedia.1234.json" and path.parent.name == "raw":
                    # Damage the staged copy, not the source. Verification must
                    # fail before current.json is changed.
                    path.write_bytes(b'{}\\n')

            with mock.patch("tools.stage_rolling_version._write_once",
                            side_effect=corrupt_retained_copy_after_write):
                with self.assertRaisesRegex(StageError, "source changed during immutable staging"):
                    stage_verified_bundle(second, stage_root, now=next_time)

            self.assertEqual((stage_root / "current.json").read_bytes(), pointer_before)
            self.assertEqual({p.name for p in (stage_root / "versions").iterdir()},
                             versions_before)
            self.assertEqual(_current(stage_root)["version_sha256"], first_sha)
            self.assertEqual((stage_root / "versions" / first_sha / "source" / "raw" /
                              "en.wikipedia.1234.json").read_bytes(),
                             (first / "raw" / "en.wikipedia.1234.json").read_bytes())

    def test_direct_source_aware_stage_refuses_explicit_synthetic_evidence(self):
        from tools.stage_rolling_version import StageError, stage
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_path = root / "seed.json"
            seed_path.write_bytes(canonical(seeds()))
            source = root / "explicit-synthetic"
            collect_to_new_directory(seed_path, source, now=lambda: NOW, fetch=fake,
                                     sleep=lambda _: None, injected=True)
            candidate = json.loads((source / "candidate.json").read_bytes())
            target = root / "must-not-be-staged"
            with self.assertRaisesRegex(StageError, "synthetic source"):
                stage(candidate, target, now=NOW, source_bundle=source)
            self.assertFalse(target.exists())

    def test_explicit_synthetic_bundle_cannot_change_valid_local_pointer(self):
        from tools.rolling_pageview_source import stage_verified_bundle
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_path = root / "seed.json"
            seed_path.write_bytes(canonical(seeds()))
            # Fake transport here is a synthetic TEST even when injected=False;
            # the simulated reported-transport label exercises only the guard.
            simulated = root / "simulated-transport"
            collect_to_new_directory(seed_path, simulated, now=lambda: NOW, fetch=fake,
                                     sleep=lambda _: None, injected=False)
            stage_root = root / "local-stage"
            baseline = stage_verified_bundle(simulated, stage_root, now=NOW)
            self.assertEqual(baseline["local_stage"]["result"], "PROMOTED_LOCAL_CANDIDATE_ONLY")
            before_pointer = (stage_root / "current.json").read_bytes()
            before_versions = {p.name for p in (stage_root / "versions").iterdir()}

            synthetic = root / "explicit-synthetic"
            collect_to_new_directory(seed_path, synthetic, now=lambda: NOW, fetch=fake,
                                     sleep=lambda _: None, injected=True)
            self.assertEqual(verify_bundle(synthetic, now=NOW)["provenance_status"],
                             "synthetic_injected_not_upstream_evidence")
            with self.assertRaisesRegex(SourceError, "synthetic/test source"):
                stage_verified_bundle(synthetic, stage_root, now=NOW)
            self.assertEqual((stage_root / "current.json").read_bytes(), before_pointer)
            self.assertEqual({p.name for p in (stage_root / "versions").iterdir()}, before_versions)

            fresh_stage = root / "stage-must-not-be-created"
            with self.assertRaisesRegex(SourceError, "synthetic/test source"):
                stage_verified_bundle(synthetic, fresh_stage, now=NOW)
            self.assertFalse(fresh_stage.exists())

    def test_modified_source_does_not_pass_manifest_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_path = root / "seeds-input.json"
            seed_path.write_bytes(canonical(seeds()))
            target = root / "evidence"
            collect_to_new_directory(seed_path, target, now=lambda: NOW, fetch=fake,
                                     sleep=lambda _: None, injected=True)
            raw = target / "raw" / "en.wikipedia.1234.json"
            raw.write_bytes(raw.read_bytes() + b" ")
            with self.assertRaisesRegex(SourceError, "hash mismatch"):
                verify_bundle(target, now=NOW)

    def test_missing_or_extra_body_and_symlink_rejected(self):
        for mode in ("missing", "extra", "symlink"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                seed_path = root / "seed.json"
                seed_path.write_bytes(canonical(seeds()))
                target = root / "evidence"
                collect_to_new_directory(seed_path, target, now=lambda: NOW, fetch=fake,
                                         sleep=lambda _: None, injected=True)
                if mode == "missing":
                    (target / "raw" / "en.wikipedia.1234.json").unlink()
                if mode == "extra":
                    (target / "raw" / "evil.json").write_text("x")
                if mode == "symlink":
                    raw = target / "raw" / "en.wikipedia.1234.json"
                    data = target / "backup"
                    data.write_bytes(raw.read_bytes())
                    raw.unlink()
                    raw.symlink_to(data)
                with self.assertRaisesRegex(SourceError, "missing/extra|unsafe"):
                    verify_bundle(target, now=NOW)

    def test_missing_dates_is_not_zero(self):
        bad = body(n=34)
        with self.assertRaisesRegex(SourceError, "incomplete"):
            parse_pageviews(bad, seeds()["pages"][0], START, END)

    def test_out_of_order_and_duplicate_dates_fail(self):
        doc = json.loads(body())
        doc["items"][2]["timestamp"] = doc["items"][1]["timestamp"]
        with self.assertRaisesRegex(SourceError, "date"):
            parse_pageviews(canonical(doc), seeds()["pages"][0], START, END)

    def test_incomparable_metrics_and_wrong_title_fail(self):
        for k,v in (("agent", "all-agents"), ("article", "Other"),
                    ("project", "ru.wikipedia"), ("granularity", "monthly")):
            with self.subTest(field=k):
                doc = json.loads(body()); doc["items"][0][k] = v
                with self.assertRaisesRegex(SourceError, "mismatched"):
                    parse_pageviews(canonical(doc), seeds()["pages"][0], START, END)

    def test_negative_bool_float_and_oversize_number_fail(self):
        for value in (True, -1, 1.5, 2**53):
            with self.subTest(value=value):
                doc = json.loads(body()); doc["items"][0]["views"] = value
                with self.assertRaisesRegex(SourceError, "views"):
                    parse_pageviews(canonical(doc), seeds()["pages"][0], START, END)

    def test_duplicate_keys_and_nonfinite_source_fail(self):
        for raw in (b'{"items":[],"items":[]}', b'{"items":NaN}'):
            with self.assertRaises(SourceError):
                strict_json(raw, "source", max_bytes=100)

    def test_429_503_timeout_fail_before_output(self):
        for code in (429, 503):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); seed_path = root / "seed.json"
                seed_path.write_bytes(canonical(seeds()))
                def failed(url):
                    return FetchResult(code, b'{}', 2, sha(b'{}'), "identity")
                with self.assertRaisesRegex(SourceError, "unsuccessful"):
                    collect_to_new_directory(seed_path, root / "evidence", now=lambda: NOW,
                                             fetch=failed, sleep=lambda _: None, injected=True)
                self.assertFalse((root / "evidence").exists())
        with self.assertRaises(TimeoutError):
            build(seeds(), now=lambda: NOW, fetch=lambda url: (_ for _ in ()).throw(TimeoutError()),
                  sleep=lambda _: None, injected=True)

    def test_truncated_gzip_trailing_and_zipbomb_rejected(self):
        import gzip
        raw = body()
        wire = gzip.compress(raw)
        self.assertEqual(decode_entity(wire, "gzip"), raw)
        for corrupt in (wire[:-3], wire+b'junk', wire+wire):
            with self.assertRaises(SourceError):
                decode_entity(corrupt, "gzip")
        huge_wire = gzip.compress(b'x' * (1024*1024+1))
        with self.assertRaises(SourceError):
            decode_entity(huge_wire, "gzip")

    def test_non_utc_clock_duplicate_ref_bad_lag_and_no_fake_data(self):
        for change in ("dupe", "bad_lag", "future_selection"):
            s = seeds()
            if change == "dupe": s["pages"].append(dict(s["pages"][0]))
            if change == "bad_lag": s["provider_lag_days"] = 0
            if change == "future_selection": s["selected_at"] = "2026-11-01"
            with self.subTest(change=change), self.assertRaises(SourceError):
                build(s, now=lambda: NOW, fetch=fake, sleep=lambda _:None, injected=True)
        with self.assertRaises(SourceError):
            build(seeds(), now=lambda: datetime(2026,10,24), fetch=fake, injected=True)

    def test_validation_rejects_candidate_rewritten_to_other_counts_even_if_hash_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); seeds_path = root / "seed.json"
            seeds_path.write_bytes(canonical(seeds()))
            target = root / "bundle"
            collect_to_new_directory(seeds_path, target, now=lambda: NOW, fetch=fake,
                                     sleep=lambda _:None, injected=True)
            path = target / "candidate.json"
            c = json.loads(path.read_text())
            c["series"][0]["daily"][0]["views"] = 999
            path.write_bytes(canonical(c))
            receipt = json.loads((target / "source-receipt.json").read_text())
            receipt["candidate_sha256"] = sha(path.read_bytes())
            (target / "source-receipt.json").write_bytes(canonical(receipt))
            with self.assertRaisesRegex(SourceError, "candidate observations differ"):
                verify_bundle(target, now=NOW)


if __name__ == "__main__":
    unittest.main()
