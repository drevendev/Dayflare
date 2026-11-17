"""Offline consumer regression: synthetic provenance, never public observations."""
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest
from zipfile import ZipFile

from test_m1_30_archive import PreservationTests
from tools.m1_30_archive import ArchiveError, build, canonical, digest
from tools.m1_30_consume import consume


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        original = self.root / 'synthetic-original.zip'
        with ZipFile(original, 'w') as z:
            for name, data in PreservationTests().synthetic().items():
                z.writestr(name, data)
        self.capsule = self.root / 'preserved.zip'
        build(original, self.capsule)

    def pin(self, path=None):
        return digest((path or self.capsule).read_bytes())

    def rewrite(self, change):
        with ZipFile(self.capsule) as z:
            content = {name: z.read(name) for name in z.namelist()}
        change(content)
        path = self.root / 'changed.zip'
        with ZipFile(path, 'w') as z:
            for name, data in content.items():
                z.writestr(name, data)
        return path

    def test_exact_pin_verifies_and_exports_unmodified_html(self):
        dest = self.root / 'atlas.html'
        receipt = consume(self.capsule, self.pin(), dest)
        self.assertEqual((receipt['series'], receipt['daily_observations']), (30, 1050))
        self.assertEqual(dest.read_bytes(),
                         b'<!doctype html><title>SYNTHETIC TEST ONLY</title>')
        self.assertEqual(digest(dest.read_bytes()), receipt['html_sha256'])
        with self.assertRaisesRegex(ArchiveError, 'destination must be new'):
            consume(self.capsule, self.pin(), dest)

    def test_wrong_or_missing_pin_leaves_no_html(self):
        dest = self.root / 'no.html'
        for pin in ('', 'A' * 64, '0' * 64, '0' * 63):
            with self.assertRaises(ArchiveError):
                consume(self.capsule, pin, dest)
        self.assertFalse(dest.exists())

    def test_manifest_member_tamper_rejected_even_with_recomputed_pin(self):
        def corrupt(data):
            data['index.html'] += b' UNSAFE MODIFICATION'
        changed = self.rewrite(corrupt)
        with self.assertRaisesRegex(ArchiveError, 'member SHA-256 mismatch'):
            consume(changed, self.pin(changed), self.root / 'bad.html')
        self.assertFalse((self.root / 'bad.html').exists())

    def test_unindexed_member_rejected_even_with_recomputed_pin(self):
        changed = self.rewrite(lambda data: data.update({'hidden.txt': b'unknown'}))
        with self.assertRaisesRegex(ArchiveError, 'cover every original member'):
            consume(changed, self.pin(changed))

    def test_bad_publication_claim_rejected_even_with_recomputed_pin(self):
        def corrupt(data):
            obj = json.loads(data['archive-manifest.json'])
            obj['status'] = 'LIVE_VERIFIED'
            data['archive-manifest.json'] = canonical(obj)
        changed = self.rewrite(corrupt)
        with self.assertRaisesRegex(ArchiveError, 'publication state'):
            consume(changed, self.pin(changed))

    def test_forged_source_and_recomputed_member_hash_still_rejected(self):
        def corrupt(data):
            path = 'm1-30-source/raw/en.wikipedia.10000.json'
            data[path] = data[path].replace(b'"views":0', b'"views":1', 1)
            obj = json.loads(data['archive-manifest.json'])
            obj['files'][path] = digest(data[path])
            data['archive-manifest.json'] = canonical(obj)
        changed = self.rewrite(corrupt)
        with self.assertRaisesRegex(ArchiveError, 'source body corruption'):
            consume(changed, self.pin(changed))

    def test_missing_manifest_member_rejected(self):
        changed = self.rewrite(lambda data: data.pop('archive-manifest.json'))
        with self.assertRaisesRegex(ArchiveError, 'missing preserved archive manifest'):
            consume(changed, self.pin(changed))

    def test_unsafe_zip_path_rejected(self):
        changed = self.rewrite(lambda data: data.update({'../escape': b'oops'}))
        with self.assertRaisesRegex(ArchiveError, 'unsafe or duplicate ZIP path'):
            consume(changed, self.pin(changed))


if __name__ == '__main__':
    unittest.main()
