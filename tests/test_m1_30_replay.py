"""Replay integration; all generated source and old browser fixtures are SYNTHETIC."""
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

import test_m1_30_archive as fixtures
from tools.m1_30_archive import ArchiveError, canonical, digest
from tools.m1_30_replay import replay
from tools.rolling_pageview_source import FetchResult, build, endpoint
from tools.rolling_window_gate import stamp


class ReplayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.files = fixtures.PreservationTests().synthetic()
        candidate = json.loads(self.files['m1-30-source/candidate.json'])
        receipt = json.loads(self.files['m1-30-source/source-receipt.json'])
        old_pin = receipt['candidate_sha256']
        seed = {'schema_version': 'dayflare.rolling-pageview-seeds.v1',
                'selected_at': '2026-11-16', 'method_version': 'v0-empirical-35d',
                'provider_lag_days': 2, 'pages': []}
        raw_by_url = {}
        end = date.fromisoformat(candidate['observation_end'])
        start = end - timedelta(days=34)
        for row, meta in zip(candidate['series'], receipt['sources']):
            seed['pages'].append({**{k: row[k] for k in ('project', 'page_id', 'title')},
                                  'subject': meta['subject']})
            raw_by_url[endpoint(row['project'], row['title'], start, end)] = (
                self.files['m1-30-source/' + meta['raw_member']])

        def fetch(url):
            raw = raw_by_url[url]
            return FetchResult(200, raw, len(raw), digest(raw), 'identity')

        candidate, receipt, bodies = build(
            seed, now=lambda: stamp('2026-11-17T08:30:55Z'),
            fetch=fetch, sleep=lambda _: None, injected=True)
        pin = receipt['candidate_sha256']
        for name in tuple(self.files):
            if name.startswith('m1-30-source/') or name.startswith(
                    'm1-30-stage/versions/' + old_pin + '/'):
                del self.files[name]
        candidate_raw, receipt_raw = canonical(candidate), canonical(receipt)
        self.files.update({'m1-30-source/candidate.json': candidate_raw,
                           'm1-30-source/seeds.json': canonical(seed),
                           'm1-30-source/source-receipt.json': receipt_raw,
                           'm1-30-stage/current.json': canonical({'version_sha256': pin}),
                           f'm1-30-stage/versions/{pin}/candidate.json': candidate_raw,
                           f'm1-30-stage/versions/{pin}/source/source-receipt.json': receipt_raw})
        self.files.update({'m1-30-source/raw/' + name: raw for name, raw in bodies.items()})
        for name in ('m1-30-pageview-run.json', 'm1-30-preview/preview-manifest.json'):
            obj = json.loads(self.files[name])
            obj['candidate_sha256'] = pin
            if name.endswith('preview-manifest.json'):
                obj['source_seed_sha256'] = receipt['seed_sha256']
            self.files[name] = canonical(obj)
        self.pin = pin

    def archive(self):
        source = self.root / 'original.zip'
        with ZipFile(source, 'w', ZIP_DEFLATED) as z:
            for name, value in sorted(self.files.items()):
                z.writestr(name, value)
        return source, digest(source.read_bytes())

    def test_rebuild_real_renderer_twice_from_injected_source(self):
        source, pin = self.archive()
        one, two = self.root / 'one', self.root / 'two'
        first = replay(source, one, pin)
        second = replay(source, two, pin)
        self.assertEqual(first, second)
        self.assertEqual(first['preview']['series'], 30)
        self.assertEqual(first['preview']['candidate_sha256'], self.pin)
        self.assertEqual(first['preview']['retrieved_at'], '2026-11-17T08:30:55Z')
        self.assertEqual(first['preview']['publication_status'], 'LOCAL_PREVIEW_NOT_PUBLISHED')
        self.assertEqual(first['preview']['provenance_status'],
                         'synthetic_injected_not_upstream_evidence')
        html = (one / 'index.html').read_bytes()
        self.assertIn(b'SYNTHETIC TEST DATA', html)
        self.assertNotEqual(digest(html), first['source_html_sha256'])
        self.assertEqual(digest(html), first['preview']['html_sha256'])
        self.assertEqual(html, (two / 'index.html').read_bytes())
        self.assertEqual((one / 'preview-manifest.json').read_bytes(),
                         (two / 'preview-manifest.json').read_bytes())
        self.assertEqual(digest(source.read_bytes()), pin)

    def test_wrong_pin_and_existing_output(self):
        source, pin = self.archive()
        dest = self.root / 'new'
        with self.assertRaisesRegex(ArchiveError, 'independent SHA-256'):
            replay(source, dest, '0' * 64)
        self.assertFalse(dest.exists())
        dest.mkdir()
        marker = dest / 'keep'
        marker.write_bytes(b'unchanged')
        with self.assertRaisesRegex(ArchiveError, 'destination'):
            replay(source, dest, pin)
        self.assertEqual(marker.read_bytes(), b'unchanged')

    def test_reject_extra_source_member_even_with_new_zip_pin(self):
        self.files['m1-30-source/unexpected.txt'] = b'not a source member'
        source, pin = self.archive()
        dest = self.root / 'new'
        with self.assertRaisesRegex(ArchiveError, 'inventory'):
            replay(source, dest, pin)
        self.assertFalse(dest.exists())

    def test_reject_tampered_raw_with_new_zip_pin(self):
        key = next(name for name in self.files if name.startswith('m1-30-source/raw/'))
        self.files[key] += b' '
        source, pin = self.archive()
        dest = self.root / 'new'
        with self.assertRaisesRegex(ArchiveError, 'source body corruption'):
            replay(source, dest, pin)
        self.assertFalse(dest.exists())

    def test_reject_linked_destination_ancestor(self):
        source, pin = self.archive()
        real = self.root / 'real'
        real.mkdir()
        (real / 'nested').mkdir()
        link = self.root / 'link'
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ArchiveError, 'destination'):
            replay(source, link / 'nested' / 'new', pin)
        self.assertFalse((real / 'nested' / 'new').exists())
