"""Offline end-to-end tests with invented HTTP-shaped data, NOT real retrieval."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from tools import m1_identity_capsule as c
from tools.m1_identity_capsule_demo import fixture_bundle, SYNTHETIC_REVISION
from tools.m1_identity_panel import canonical_bytes, load_panel
from tools.m1_source_verify import verify_sources
from tools.m1_bundle_verify import make_manifest, verify_bundle


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.hrefs, self.tags = set(), [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if 'href' in attrs:
            self.hrefs.append(attrs['href'])


class CapsuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = fixture_bundle(self.root / 'bundle')

    def build(self, **options):
        return c.build_capsule(self.bundle, source_revision=SYNTHETIC_REVISION,
                               evidence_kind='synthetic_test_fixture', **options)

    def contents(self, raw=None):
        with ZipFile(io.BytesIO(raw or self.build())) as archive:
            return {n: archive.read(n) for n in archive.namelist()}

    def assert_bad(self, raw, text=None):
        with self.assertRaisesRegex(c.CapsuleError, text or '.'):
            c.verify_capsule(raw, c.digest(raw))

    def refresh_manifest(self):
        (self.bundle / 'bundle-manifest.json').unlink()
        (self.bundle / 'internal-consistency.json').write_bytes(canonical_bytes(
            verify_sources(self.bundle / 'panel.json', self.bundle / 'raw')))
        panel = load_panel(self.bundle / 'panel.json')
        (self.bundle / 'bundle-manifest.json').write_bytes(canonical_bytes(make_manifest(self.bundle, panel)))

    def test_valid_roundtrip_runs_original_source_and_bundle_gates(self):
        raw = self.build()
        files, receipt = c.verify_capsule(raw, c.digest(raw))
        self.assertEqual((receipt['intended_count'], receipt['retained_count'], receipt['unavailable_count']), (20, 19, 1))
        self.assertFalse(receipt['network_origin_verified'])
        self.assertEqual(receipt['evidence_kind'], 'synthetic_test_fixture')
        self.assertEqual(len(files), 25)
        self.assertEqual(receipt['observation_date_utc'], '2026-10-01')
        self.assertEqual(receipt['last_request_started_at_utc'], '2026-10-01T12:00:19Z')

    def test_preserves_every_original_source_byte(self):
        files = self.contents()
        for path in self.bundle.rglob('*.json'):
            self.assertEqual(files['source/' + path.relative_to(self.bundle).as_posix()], path.read_bytes())

    def test_two_builds_are_identical_without_changing_inputs(self):
        before = {p.relative_to(self.bundle): p.read_bytes() for p in self.bundle.rglob('*.json')}
        self.assertEqual(self.build(), self.build())
        self.assertEqual(before, {p.relative_to(self.bundle): p.read_bytes() for p in self.bundle.rglob('*.json')})

    def test_unpack_is_a_real_reusable_bundle_for_original_validator(self):
        raw = self.build()
        destination = self.root / 'unpacked'
        c.unpack_capsule(raw, c.digest(raw), destination)
        self.assertEqual(verify_bundle(destination / 'source')['verified_pages'], 19)
        self.assertEqual((destination / 'index.html').read_bytes(), self.contents(raw)['index.html'])

    def test_original_validator_rejects_corrupted_body(self):
        next((self.bundle / 'raw').glob('*.json')).write_bytes(b'{}')
        with self.assertRaisesRegex(c.CapsuleError, 'invalid source bundle'):
            self.build()

    def test_missing_source_member(self):
        (self.bundle / 'internal-consistency.json').unlink()
        with self.assertRaises(c.CapsuleError):
            self.build()

    def test_extra_source_file(self):
        (self.bundle / 'secret.txt').write_text('must never be copied')
        with self.assertRaises(c.CapsuleError):
            self.build()

    def test_invalid_raw_filename(self):
        (self.bundle / 'raw' / 'other.json').write_text('{}')
        with self.assertRaises(c.CapsuleError):
            self.build()

    def test_metadata_allowlist_rejects_article_content(self):
        row = {'pageid': 1, 'ns': 0, 'title': 'Test', 'revisions': [{'content': 'excluded article'}]}
        with self.assertRaisesRegex(c.CapsuleError, 'article content'):
            c.metadata_only(canonical_bytes({'batchcomplete': True, 'query': {'pages': [row]}}))

    def test_metadata_allowlist_rejects_unknown_root(self):
        with self.assertRaisesRegex(c.CapsuleError, 'root fields'):
            c.metadata_only(canonical_bytes({'batchcomplete': True, 'query': {}, 'extract': 'no'}))

    def test_metadata_allowlist_rejects_unknown_pageprops(self):
        row = {'pageid': 1, 'ns': 0, 'title': 'Test', 'pageprops': {'description': 'excluded'}}
        with self.assertRaisesRegex(c.CapsuleError, 'page properties'):
            c.metadata_only(canonical_bytes({'batchcomplete': True, 'query': {'pages': [row]}}))

    def test_nonfinite_duplicate_and_deep_json_fail(self):
        for raw in (b'{"x":NaN}', b'{"x":1,"x":2}', b'{"x":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}', b'[]', b'\xff'):
            with self.subTest(raw=raw[:30]), self.assertRaises(c.CapsuleError):
                c.strict_json(raw)

    def test_symlink_source_is_rejected(self):
        path = self.bundle / 'panel.json'
        target = self.root / 'panel.json'
        path.rename(target)
        path.symlink_to(target)
        with self.assertRaises(c.CapsuleError):
            self.build()

    def test_symlink_ancestor_is_rejected(self):
        linked = self.root / 'linked'
        linked.symlink_to(self.bundle, target_is_directory=True)
        with self.assertRaises(c.CapsuleError):
            c.snapshot_directory(linked)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO check')
    def test_nonregular_source_never_blocks(self):
        path = self.bundle / 'panel.json'
        path.unlink()
        os.mkfifo(path)
        with self.assertRaisesRegex(c.CapsuleError, 'regular'):
            self.build()

    def test_zero_length_and_oversized_file(self):
        path = self.root / 'raw'
        for data in (b'', b'12345'):
            path.write_bytes(data)
            with self.assertRaises(c.CapsuleError):
                c.read_regular(path, 4)

    def test_external_pin_required_and_mismatch_rejected(self):
        raw = self.build()
        for pin in (None, '', 'x' * 64, '0' * 64, c.digest(raw).upper()):
            with self.subTest(pin=pin), self.assertRaises(c.CapsuleError):
                c.verify_capsule(raw, pin)

    def test_changed_source_revision_changes_capsule(self):
        changed = c.build_capsule(self.bundle, source_revision='a' * 40, evidence_kind='synthetic_test_fixture')
        self.assertNotEqual(changed, self.build())

    def test_revision_and_run_url_are_bounded_and_scoped(self):
        for sha in ('main', 'a' * 39, None, 'A' * 40):
            with self.subTest(sha=sha), self.assertRaises(c.CapsuleError):
                c.build_capsule(self.bundle, source_revision=sha, evidence_kind='synthetic_test_fixture')
        for url in ('https://github.com/elsewhere/repo/actions/runs/1', 'https://github.com/drevendev/Dayflare/actions/runs/1?token=bad'):
            with self.subTest(url=url), self.assertRaises(c.CapsuleError):
                self.build(source_run_url=url)
        raw = self.build(source_run_url='https://github.com/drevendev/Dayflare/actions/runs/123')
        self.assertEqual(c.verify_capsule(raw, c.digest(raw))[1]['source_run_url'].split('/')[-1], '123')

    def test_archive_path_traversal_and_unknown_files(self):
        for name in ('../escape', '/absolute', 'source/raw/../escape', 'source\\panel.json', 'script.js'):
            changed = self.contents()
            changed[name] = b'bad'
            self.assert_bad(c.zip_bytes(changed), 'unlisted|member count')
        self.assertFalse((self.root / 'escape').exists())

    def test_archive_duplicate_member(self):
        stream = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with ZipFile(stream, 'w') as archive:
                for _ in range(2):
                    info = ZipInfo('index.html')
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    archive.writestr(info, b'a')
        self.assert_bad(stream.getvalue(), 'duplicate')

    def test_archive_symlink_and_compression_rejected(self):
        for mode, compression in ((stat.S_IFLNK | 0o777, 0), (stat.S_IFREG | 0o644, ZIP_DEFLATED)):
            stream = io.BytesIO()
            with ZipFile(stream, 'w') as archive:
                info = ZipInfo('index.html')
                info.create_system = 3
                info.external_attr = mode << 16
                info.compress_type = compression
                archive.writestr(info, b'x' * 100)
            self.assert_bad(stream.getvalue(), 'linked, compressed')

    def test_appended_truncated_and_invalid_archives(self):
        raw = self.build()
        for changed in (raw + b'unlisted', raw[:-32], b'not a zip'):
            with self.subTest(size=len(changed)):
                self.assert_bad(changed)

    def test_archive_member_budget(self):
        changed = self.contents()
        changed['capsule.json'] = b'x' * (32 * 1024 + 1)
        self.assert_bad(c.zip_bytes(changed), 'oversized')

    def test_archive_total_budget(self):
        raw = self.build()
        with patch.object(c, 'MAX_ARCHIVE', len(raw) - 1):
            self.assert_bad(raw, 'oversized')

    def test_changed_rendered_page_rejected_even_with_new_outer_hash(self):
        changed = self.contents()
        changed['index.html'] += b'<p>invented freshness</p>'
        self.assert_bad(c.zip_bytes(changed), 'unreviewed evidence page')

    def test_false_coverage_and_authenticity_receipts_rejected(self):
        for field, value in (('retained_count', 20), ('network_origin_verified', True), ('observation_date_utc', '2026-11-03')):
            changed = self.contents()
            receipt = json.loads(changed['capsule.json'])
            receipt[field] = value
            changed['capsule.json'] = canonical_bytes(receipt)
            self.assert_bad(c.zip_bytes(changed), 'receipt differs')

    def test_midnight_collection_rejected_despite_valid_source_bundle(self):
        report_path = self.bundle / 'collection-report.json'
        report = json.loads(report_path.read_text())
        # The last attempt is unavailable and has no retained raw body.
        report['attempts'][-1]['requested_at'] = '2026-10-02T00:00:01Z'
        report_path.write_bytes(canonical_bytes(report))
        self.refresh_manifest()
        verify_bundle(self.bundle)
        with self.assertRaisesRegex(c.CapsuleError, 'UTC observation date'):
            self.build()

    def test_frozen_snapshot_is_checked_not_mutated_original(self):
        frozen = c.snapshot_directory(self.bundle)
        next((self.bundle / 'raw').glob('*.json')).write_bytes(b'{}')
        with patch.object(c, 'snapshot_directory', return_value=frozen):
            raw = self.build()
        c.verify_capsule(raw, c.digest(raw))

    def test_no_overwrite_existing_archive(self):
        destination = self.root / 'accepted.zip'
        destination.write_bytes(b'old valid publication')
        with self.assertRaises(c.CapsuleError):
            c.write_capsule(destination, self.build())
        self.assertEqual(destination.read_bytes(), b'old valid publication')

    def test_no_overwrite_existing_unpack_directory(self):
        destination = self.root / 'accepted'
        destination.mkdir()
        (destination / 'index.html').write_bytes(b'accepted')
        raw = self.build()
        with self.assertRaises(FileExistsError):
            c.unpack_capsule(raw, c.digest(raw), destination)
        self.assertEqual((destination / 'index.html').read_bytes(), b'accepted')

    def test_invalid_input_creates_no_output(self):
        destination = self.root / 'absent'
        with self.assertRaises(c.CapsuleError):
            c.unpack_capsule(b'bad', c.digest(b'bad'), destination)
        self.assertFalse(destination.exists())

    def test_concurrent_archive_writers_exactly_one_wins(self):
        raw = self.build()
        destination = self.root / 'race.zip'
        def write():
            try:
                return c.write_capsule(destination, raw)
            except (c.CapsuleError, FileExistsError):
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: write(), range(2)))
        self.assertEqual(sum(v is not None for v in results), 1)
        self.assertEqual(destination.read_bytes(), raw)
        self.assertEqual(list(self.root.glob('.dayflare-capsule-*')), [])

    def test_partial_archive_io_leaves_no_promoted_output(self):
        raw = self.build()
        destination = self.root / 'failed.zip'
        with patch.object(c.os, 'fsync', side_effect=OSError('injected I/O failure')):
            with self.assertRaises(OSError):
                c.write_capsule(destination, raw)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob('.dayflare-capsule-*')), [])

    def test_partial_unpack_has_no_completion_page(self):
        raw = self.build()
        destination = self.root / 'partial'
        original = Path.open
        def failing(path, *args, **kwargs):
            if path == destination / 'source/panel.json':
                raise OSError('injected I/O failure')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', failing), self.assertRaises(OSError):
            c.unpack_capsule(raw, c.digest(raw), destination)
        self.assertFalse((destination / 'index.html').exists())

    def test_final_html_io_failure_leaves_no_completion_page(self):
        raw = self.build()
        destination = self.root / 'partial-html'
        with patch.object(c.os, 'fsync', side_effect=OSError('injected final HTML failure')):
            with self.assertRaises(OSError):
                c.unpack_capsule(raw, c.digest(raw), destination)
        self.assertTrue((destination / 'source/panel.json').is_file())
        self.assertFalse((destination / 'index.html').exists())
        self.assertEqual(list(destination.glob('.dayflare-capsule-*')), [])

    def test_html_all_local_links_resolve_without_remote_assets(self):
        files = self.contents()
        parser = Links()
        parser.feed(files['index.html'].decode())
        self.assertFalse(set(parser.tags) & {'script', 'img', 'iframe', 'link'})
        for link in parser.hrefs:
            if link.startswith('#'):
                self.assertIn(link[1:], parser.ids)
            elif not link.startswith('https://'):
                self.assertIn(link, files)

    def test_html_escapes_hostile_title_and_labels_unknowns(self):
        self.bundle = fixture_bundle(self.root / 'hostile', title_override='<script>alert("x")</script>')
        html = self.contents()['index.html'].decode()
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('SYNTHETIC TEST FIXTURE', html)
        self.assertIn('Unavailable selected identities', html)
        self.assertIn('Not resolved', html)
        self.assertIn('These are not deletions or zero interest', html)

    def test_unsupported_evidence_kind_and_old_projection_rejected(self):
        with self.assertRaises(c.CapsuleError):
            c.build_capsule(self.bundle, source_revision=SYNTHETIC_REVISION, evidence_kind='real_verified')
        (self.bundle / 'panel.json').write_bytes(canonical_bytes({'schema_version': 'dayflare.m1.observed-identity-panel.v1'}))
        with self.assertRaises(c.CapsuleError):
            self.build()

    def test_cli_pack_verify_unpack_and_fail_closed(self):
        archive = self.root / 'cli.zip'
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(c.main(['pack', str(self.bundle), str(archive), '--source-revision', SYNTHETIC_REVISION,
                                     '--evidence-kind', 'synthetic_test_fixture']), 0)
        pin = json.loads(out.getvalue())['sha256']
        with redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(['verify', str(archive), '--expected-sha256', pin]), 0)
            self.assertEqual(c.main(['unpack', str(archive), str(self.root / 'cli-preview'), '--expected-sha256', pin]), 0)
        with redirect_stderr(io.StringIO()) as out:
            self.assertEqual(c.main(['verify', str(archive), '--expected-sha256', 'f' * 64]), 2)
        self.assertIn('CAPSULE_INVALID', out.getvalue())


    def test_selected_id_budget_is_enforced(self):
        self.bundle = fixture_bundle(self.root / 'too-many', count=21, unavailable=False)
        with self.assertRaisesRegex(c.CapsuleError, '20'):
            self.build()

    def test_unselected_cells_are_not_zero_interest(self):
        self.bundle = fixture_bundle(self.root / 'one', count=1, unavailable=False)
        html = self.contents()['index.html'].decode()
        self.assertIn('Not selected', html)
        self.assertIn('1 / 1', html)

    def test_changed_input_changes_identity_anchors(self):
        first = Links()
        first.feed(self.contents()['index.html'].decode())
        self.bundle = fixture_bundle(self.root / 'next-date', day='2026-10-02')
        second = Links()
        second.feed(self.contents()['index.html'].decode())
        self.assertFalse({i for i in first.ids if i.startswith('identity-')} & second.ids)

    def test_generated_page_must_fit_its_own_verifier_budget(self):
        with patch.object(c, 'render', return_value=b'x' * (c.MAX_MEMBER + 1)):
            with self.assertRaisesRegex(c.CapsuleError, 'generated member'):
                self.build()

    def test_independently_valid_bundle_with_article_payload_is_rejected(self):
        panel_path = self.bundle / 'panel.json'
        report_path = self.bundle / 'collection-report.json'
        panel = json.loads(panel_path.read_text())
        report = json.loads(report_path.read_text())
        row = panel['pages'][0]
        path = self.bundle / 'raw' / (row['page_ref']['project'] + '.' + str(row['page_ref']['page_id']) + '.json')
        original = path.read_bytes()
        body = json.loads(original)
        body['query']['pages'][0]['revisions'] = [{'content': 'Unlicensed text must never enter a capsule.'}]
        changed = canonical_bytes(body)
        path.write_bytes(changed)
        row['source'].update(body_sha256=c.digest(changed), response_bytes=len(changed))
        attempt = report['attempts'][0]
        attempt.update(body_sha256=c.digest(changed), response_bytes=len(changed),
                       wire_sha256=c.digest(changed), wire_bytes=len(changed))
        for field in ('transferred_bytes', 'decoded_bytes', 'retained_bytes'):
            report[field] += len(changed) - len(original)
        panel_path.write_bytes(canonical_bytes(panel))
        report_path.write_bytes(canonical_bytes(report))
        self.refresh_manifest()
        verify_bundle(self.bundle)  # Existing gate checks identities, not content inventory.
        with self.assertRaisesRegex(c.CapsuleError, 'article content'):
            self.build()

    def test_non_one_to_one_mapping_is_visible(self):
        files = c.snapshot_directory(self.bundle)
        panel, report = c.validate_source(files)
        # Explicit synthetic projection control; it does not assert source evidence.
        first = panel['pages'][0]
        panel['coverage']['non_1_to_1_observed_qid_collisions'] = [
            {'project': first['page_ref']['project'], 'qid': first['wikidata']['observed_qid'],
             'local_page_ids': [first['page_ref']['page_id'], 999999999]}]
        receipt = c.receipt_for(files, panel, report, source_revision=SYNTHETIC_REVISION,
                                source_run_url=None, evidence_kind='synthetic_test_fixture')
        self.assertIn('Non-1:1 QID mapping', c.render(panel, report, receipt, files).decode())


    def test_marked_fixture_cannot_be_relabelled_reported_retrieval(self):
        with self.assertRaisesRegex(c.CapsuleError, 'synthetic source'):
            c.build_capsule(self.bundle, source_revision='a' * 40, evidence_kind='reported_retrieval')

    def test_tampered_fixture_kind_is_rejected_during_verification(self):
        files = self.contents()
        receipt = json.loads(files['capsule.json'])
        receipt['evidence_kind'] = 'reported_retrieval'
        files['capsule.json'] = canonical_bytes(receipt)
        self.assert_bad(c.zip_bytes(files), 'synthetic source')



    def test_request_starts_do_not_claim_retrieval_completion(self):
        files, receipt = c.verify_capsule(self.build(), c.digest(self.build()))
        self.assertEqual(receipt['first_request_started_at_utc'], '2026-10-01T12:00:00Z')
        self.assertIsNone(receipt['retrieval_completed_at_utc'])
        self.assertNotIn('retrieval_end_utc', receipt)
        self.assertIn('Retrieval completion time: unavailable', files['index.html'].decode())

    def test_request_times_sort_as_instants_not_strings(self):
        files = c.snapshot_directory(self.bundle)
        panel, report = c.validate_source(files)
        # Fractional formatting must not move .5 seconds before the whole second.
        # This isolated receipt projection is synthetic, not source acceptance.
        report['attempts'] = [{'requested_at': '2026-10-01T12:00:00Z'},
                              {'requested_at': '2026-10-01T12:00:00.5Z'}]
        receipt = c.receipt_for(files, panel, report, source_revision=SYNTHETIC_REVISION,
                               source_run_url=None, evidence_kind='synthetic_test_fixture')
        self.assertEqual(receipt['first_request_started_at_utc'], '2026-10-01T12:00:00Z')
        self.assertEqual(receipt['last_request_started_at_utc'], '2026-10-01T12:00:00.500000Z')

    def test_json_exponent_overflow_is_rejected(self):
        for raw in (b'{"x":1e999}', b'{"x":[-1e999]}', b'{"x":{"y":1e999}}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(c.CapsuleError, 'nonfinite'):
                c.strict_json(raw)
        self.assertEqual(c.strict_json(b'{"x":1e2}')['x'], 100)

    def test_all_frozen_source_members_receive_strict_json_gate(self):
        original = c.snapshot_directory(self.bundle)
        for name in original:
            with self.subTest(name=name):
                changed = dict(original)
                changed[name] = b'{"x":1,"x":2}'
                with patch.object(c, 'verify_bundle') as gate:
                    with self.assertRaisesRegex(c.CapsuleError, 'invalid'):
                        c.validate_source(changed)
                    gate.assert_not_called()

    def test_rehashed_duplicate_panel_is_not_valid_source(self):
        path = self.bundle / 'panel.json'
        raw = path.read_bytes()
        path.write_bytes(b'{"panel_id":"discarded-duplicate",' + raw[1:])
        manifest_path = self.bundle / 'bundle-manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['files']['panel.json'] = {'bytes': path.stat().st_size,
                                          'sha256': c.digest(path.read_bytes())}
        manifest_path.write_bytes(canonical_bytes(manifest))
        with self.assertRaisesRegex(c.CapsuleError, 'invalid'):
            self.build()

    def test_deep_source_json_rejected_before_legacy_validation(self):
        files = c.snapshot_directory(self.bundle)
        files['source/panel.json'] = b'{"x":' + b'[' * 40 + b'0' + b']' * 40 + b'}'
        with patch.object(c, 'verify_bundle') as gate:
            with self.assertRaisesRegex(c.CapsuleError, 'nesting'):
                c.validate_source(files)
            gate.assert_not_called()

    def test_directory_member_scan_is_bounded(self):
        for i in range(20):
            (self.bundle / f'extra-{i}.json').write_text('{}')
        with self.assertRaisesRegex(c.CapsuleError, 'too many bundle'):
            c.snapshot_directory(self.bundle)


if __name__ == '__main__':
    unittest.main()
