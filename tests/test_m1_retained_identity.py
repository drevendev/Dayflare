"""Actual retained metadata plus clearly mutated negative controls; no network."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from tools import m1_retained_identity as m


class RetainedIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        shutil.copytree(m.DEFAULT, self.source)
        self.members = m.archive_members((self.source / 'source.zip').read_bytes())
        self.provenance = m.strict_json((self.source / 'provenance.json').read_bytes())

    def archive(self, entries, mode=None):
        out = BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
                for name, data in entries:
                    info = ZipInfo(name)
                    info.compress_type = ZIP_DEFLATED
                    if mode is not None:
                        info.create_system = 3
                        info.external_attr = mode << 16
                    archive.writestr(info, data)
        return out.getvalue()

    def test_real_retained_baseline_verifies_all_twenty_sources(self):
        panel, proof, p, files = m.load_retained(self.source)
        self.assertEqual(proof['verified_pages'], 20)
        self.assertEqual(proof['observed_bytes'], 5966)
        self.assertEqual(len(files), 24)
        self.assertEqual(sum(map(len, files.values())), 45118)
        self.assertEqual(p['source']['run_id'], 41814628479)
        self.assertEqual(p['source']['artifact_id'], 13314391318)
        self.assertEqual(panel['coverage']['by_edition'], {'en.wikipedia': 10, 'ru.wikipedia': 10})
        self.assertEqual(panel['coverage']['by_subject'], {subject: 4 for subject in m.SUBJECTS})
        self.assertEqual(panel['coverage']['provenance_verification'], 'reported_not_upstream_verified')

    def test_observation_is_november_not_october_selection_date(self):
        panel, _, p, _ = m.load_retained(self.source)
        self.assertEqual(panel['selection']['selected_at'], '2026-10-24')
        self.assertEqual({r['titles'][-1]['date'] for r in panel['pages']}, {'2026-11-04'})
        self.assertEqual(p['retrieval_start_utc'], '2026-11-04T10:31:14Z')
        html = m.render(panel, p).decode()
        self.assertIn('Historical metadata snapshot · 2026-11-04 UTC', html)
        self.assertNotIn('snapshot · 2026-10-24', html)
        self.assertIn('not a live refresh', html)
        self.assertIn('not a live refresh or a popularity chart', html)
        self.assertIn('separately collected later date is still required', html)

    def test_original_panel_bytes_are_exported_not_normalized_replacement(self):
        files = m.output_files(self.source)
        self.assertEqual(files['source/panel.json'], self.members['panel.json'])
        panel = json.loads(files['source/panel.json'])
        self.assertEqual(set(panel), {'pages', 'panel_id', 'schema_version', 'selection'})
        for name, body in self.members.items():
            self.assertEqual(files['source/' + name], body)

    def test_all_exact_source_links_and_versioned_anchors_are_present(self):
        panel, _, p, members = m.load_retained(self.source)
        html = m.render(panel, p).decode()
        for row in panel['pages']:
            ref = row['page_ref']
            self.assertIn('id="' + m.page_anchor(row) + '"', html)
            self.assertIn(f'source/raw/{ref["project"]}.{ref["page_id"]}.json', html)
            self.assertIn(row['source']['body_sha256'], html)
            self.assertIn(row['source']['requested_at'], html)
        self.assertEqual(html.count('<article '), 20)
        self.assertEqual(html.count('<details>'), 20)
        self.assertIn('Observed page counts in this panel, not pageviews or people.', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('<iframe', html)

    def test_deterministic_build_and_manifest(self):
        first = m.build(self.root / 'a', self.source)
        second = m.build(self.root / 'b', self.source)
        self.assertEqual(first, second)
        self.assertEqual(first, m.build(self.root / 'a', self.source, check=True))
        manifest = json.loads(first['manifest.json'])
        self.assertEqual(set(first) - {'manifest.json'}, set(manifest['files_sha256']))
        for name, expected in manifest['files_sha256'].items():
            self.assertEqual(sha256(first[name]).hexdigest(), expected)
        self.assertEqual(manifest['status'], 'BUILT_NOT_DEPLOYED')

    def test_existing_destination_is_never_overwritten(self):
        target = self.root / 'existing'
        m.build(target, self.source)
        (target / 'sentinel').write_bytes(b'last valid')
        with self.assertRaises(FileExistsError):
            m.build(target, self.source)
        self.assertEqual((target / 'sentinel').read_bytes(), b'last valid')

    def test_concurrent_builds_have_exactly_one_winner(self):
        target = self.root / 'concurrent'
        def run():
            try:
                m.build(target, self.source)
                return 'built'
            except FileExistsError:
                return 'exists'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _: run(), range(2))), ['built', 'exists'])
        m.build(target, self.source, check=True)

    def test_source_tampering_rejected_before_creating_output(self):
        source = self.source / 'source.zip'
        source.write_bytes(source.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'Unreviewed retained source archive'):
            m.build(self.root / 'bad', self.source)
        self.assertFalse((self.root / 'bad').exists())

    def test_schema_valid_provenance_mutation_rejected(self):
        p = self.source / 'provenance.json'
        value = json.loads(p.read_bytes())
        value['observation_date_utc'] = '2026-10-24'
        p.write_bytes(m.canonical_bytes(value))
        with self.assertRaisesRegex(ValueError, 'Unreviewed retained provenance'):
            m.load_retained(self.source)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'[]', b'\xff', b'{']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                m.strict_json(raw)

    def test_malformed_and_oversized_archive_rejected(self):
        for raw in [b'bad', b'', b'0' * (m.MAX_ARCHIVE + 1)]:
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                m.archive_members(raw)

    def test_traversal_and_unlisted_paths_rejected_without_extraction(self):
        for name in ['../escape.json', '/absolute.json', 'raw/../escape.json', 'raw\\escape.json',
                     'raw/fr.wikipedia.1.json', 'extra.json', 'raw/en.wikipedia.01.json']:
            raw = self.archive(list(self.members.items()) + [(name, b'{}')])
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unexpected ZIP path'):
                m.archive_members(raw)
        self.assertFalse((self.root / 'escape.json').exists())

    def test_duplicate_zip_member_rejected(self):
        entries = list(self.members.items()) + [('panel.json', b'{}')]
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            m.archive_members(self.archive(entries))

    def test_symlink_zip_member_rejected(self):
        raw = self.archive(self.members.items(), stat.S_IFLNK | 0o777)
        with self.assertRaisesRegex(ValueError, 'Non-regular'):
            m.archive_members(raw)

    def test_decompression_budgets_are_enforced(self):
        files = dict(self.members)
        files['panel.json'] = b'x' * (m.MAX_MEMBER + 1)
        with self.assertRaisesRegex(ValueError, 'member size limit'):
            m.archive_members(self.archive(files.items()))
        files = {f'raw/en.wikipedia.{i}.json': b'x' * m.MAX_MEMBER for i in range(1, 6)}
        files.update({k: b'{}' for k in m.ROOT_FILES})
        with self.assertRaisesRegex(ValueError, 'total size limit'):
            m.archive_members(self.archive(files.items()))

    def test_excess_members_rejected(self):
        entries = [(f'raw/en.wikipedia.{i}.json', b'{}') for i in range(1, m.MAX_MEMBERS + 2)]
        with self.assertRaisesRegex(ValueError, 'member count'):
            m.archive_members(self.archive(entries))

    def test_missing_root_member_rejected(self):
        entries = [(k, v) for k, v in self.members.items() if k != 'panel.json']
        with self.assertRaisesRegex(ValueError, 'Missing required'):
            m.archive_members(self.archive(entries))

    def test_missing_raw_body_rejected_by_existing_bundle_verifier(self):
        del self.members['raw/en.wikipedia.5134.json']
        with self.assertRaises(ValueError):
            m.verify_members(self.members, self.provenance)

    def test_changed_raw_body_rejected_by_existing_bundle_verifier(self):
        self.members['raw/en.wikipedia.5134.json'] += b' '
        with self.assertRaisesRegex(ValueError, 'manifest hash'):
            m.verify_members(self.members, self.provenance)

    def test_source_semantics_rechecked_even_with_matching_manifest(self):
        panel = json.loads(self.members['panel.json'])
        panel['pages'][0]['titles'][-1]['title'] = 'Not the retained source title'
        self.members['panel.json'] = m.canonical_bytes(panel)
        manifest = json.loads(self.members['bundle-manifest.json'])
        manifest['files']['panel.json'] = {'bytes': len(self.members['panel.json']),
                                         'sha256': sha256(self.members['panel.json']).hexdigest()}
        self.members['bundle-manifest.json'] = m.canonical_bytes(manifest)
        with self.assertRaisesRegex(ValueError, 'current title disagrees'):
            m.verify_members(self.members, self.provenance)

    def test_provenance_dates_and_counts_bind_to_actual_sources(self):
        for key, value in [('observation_date_utc', '2026-10-24'), ('retrieval_start_utc', '2026-11-04T00:00:00Z'),
                           ('obtained_count', 19), ('source_manifest_sha256', '0' * 64)]:
            altered = dict(self.provenance, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.verify_members(self.members, altered)

    def test_symlink_source_and_output_rejected(self):
        link = self.root / 'linked-source'
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            m.load_retained(link)
        target = self.root / 'preview'
        m.build(target, self.source)
        (target / 'provenance.json').unlink()
        (target / 'provenance.json').symlink_to(self.source / 'provenance.json')
        with self.assertRaisesRegex(ValueError, 'Linked preview member'):
            m.build(target, self.source, check=True)

    def test_check_rejects_altered_and_extra_output_without_repairing(self):
        target = self.root / 'preview'
        m.build(target, self.source)
        p = target / 'index.html'
        p.write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError, 'Preview bytes differ'):
            m.build(target, self.source, check=True)
        self.assertEqual(p.read_bytes(), b'altered')
        (target / 'extra').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'Preview inventory mismatch'):
            m.build(target, self.source, check=True)

    def test_partial_write_does_not_produce_manifest(self):
        target = self.root / 'partial'
        original = Path.open
        def opened(path, *args, **kwargs):
            if path == target / 'provenance.json' and args == ('xb',):
                raise OSError('simulated disk failure')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', opened), self.assertRaises(OSError):
            m.build(target, self.source)
        self.assertFalse((target / 'manifest.json').exists())

    def test_html_escapes_untrusted_titles(self):
        panel, _, p, _ = m.load_retained(self.source)
        panel['pages'][0]['titles'][-1]['title'] = '<script>alert("x")</script>'
        html = m.render(panel, p).decode()
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)

    def test_cli_verify_build_check_and_invalid_exit(self):
        target = self.root / 'cli'
        with redirect_stdout(StringIO()):
            self.assertEqual(m.main(['--source', str(self.source)]), 0)
            self.assertEqual(m.main([str(target), '--source', str(self.source)]), 0)
            self.assertEqual(m.main([str(target), '--check', '--source', str(self.source)]), 0)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            m.main(['--source', str(self.root / 'missing')])
        self.assertEqual(raised.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
