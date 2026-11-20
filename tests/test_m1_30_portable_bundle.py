"""End-to-end real and adversarial tests for Git-retained 30-title portable ZIP."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from tools.m1_30_portable_bundle import (
    BundleError, README, STATUS, build, digest, encode_zip, read_members, verify,
)


class PortableBundleTests(unittest.TestCase):
    def test_real_rebuild_is_byte_identical_and_verifiable_after_original_artifact_expiry(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / 'a.zip'
            second = root / 'b.zip'
            a = build(first)
            b = build(second)
            self.assertEqual(a['zip_sha256'], b['zip_sha256'])
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(a['selected_histories'], 30)
            self.assertEqual(a['daily_observations'], 1050)
            self.assertEqual(a['status'], STATUS)
            self.assertEqual(a['observation_end'], '2026-11-14')
            self.assertEqual(a['source_scope'], 'decoded_HTTP_bodies_and_receipt_only')
            members = read_members(first)
            self.assertEqual(len(members), 35)
            self.assertEqual(members['README.txt'], README)
            self.assertEqual(sum(p.startswith('source/raw/') for p in members), 30)
            self.assertIn(b'<!DOCTYPE html', members['index.html'].upper().replace(b'<!DOCTYPE HTML', b'<!DOCTYPE html'))
            html = root / 'reader.html'
            checked = verify(first, a['zip_sha256'], html)
            self.assertEqual(checked['html_sha256'], digest(html.read_bytes()))
            self.assertEqual(html.read_bytes(), members['index.html'])
            with self.assertRaisesRegex(BundleError, 'destination must be new'):
                build(first)
            with self.assertRaisesRegex(BundleError, 'destination must be new'):
                verify(first, a['zip_sha256'], html)

    def test_tampered_missing_extra_and_misleading_manifest_are_rejected_even_with_new_pin(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / 'original.zip'
            receipt = build(original)
            files = read_members(original)
            raw_name = next(n for n in files if n.startswith('source/raw/'))
            for name, changed in (
                ('raw-mutated', {raw_name: files[raw_name] + b' '}),
                ('candidate-mutated', {'source/candidate.json': files['source/candidate.json'] + b' '}),
                ('html-mutated', {'index.html': b'<html>FORGED</html>'}),
                ('manifest-mutated', {'manifest.json': b'{"status":"PUBLISHED"}'}),
                ('readme-mutated', {'README.txt': b'PUBLISHED'}),
                ('unknown-extra', {'source/extra.json': b'{}'}),
            ):
                with self.subTest(name=name):
                    altered = dict(files)
                    altered.update(changed)
                    bad = root / (name + '.zip')
                    bad.write_bytes(encode_zip(altered))
                    with self.assertRaises(BundleError):
                        verify(bad, digest(bad.read_bytes()))
            missing = dict(files)
            del missing[raw_name]
            path = root / 'missing.zip'
            path.write_bytes(encode_zip(missing))
            with self.assertRaisesRegex(BundleError, 'missing or unrecognized'):
                verify(path, digest(path.read_bytes()))
            self.assertEqual(verify(original, receipt['zip_sha256'])['selected_histories'], 30)

    def test_independent_pin_and_path_safety_fail_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = root / 'valid.zip'
            record = build(valid)
            for pin in ('', '0' * 64, 'F' * 64, 'xyz'):
                with self.subTest(pin=pin):
                    with self.assertRaises(BundleError):
                        verify(valid, pin)
            # Even a repinned malicious ZIP must reject paths outside the archive.
            malformed = root / 'traversal.zip'
            malformed.write_bytes(encode_zip({'../outside.txt': b'unsafe', **read_members(valid)}))
            with self.assertRaisesRegex(BundleError, 'unsafe'):
                verify(malformed, digest(malformed.read_bytes()))
            self.assertEqual(verify(valid, record['zip_sha256'])['status'], STATUS)


if __name__ == '__main__':
    unittest.main()
