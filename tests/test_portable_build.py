"""Portable M0 output is a deterministic projection, never a new evidence source."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import build_portable


class PortableBuildTests(unittest.TestCase):
    def test_exact_source_archive_is_preserved(self):
        before=hashlib.sha256(build_portable.ARCHIVE.read_bytes()).hexdigest()
        build_portable.build_html()
        after=hashlib.sha256(build_portable.ARCHIVE.read_bytes()).hexdigest()
        self.assertEqual(before, build_portable.EXPECTED['source.zip'])
        self.assertEqual(before, after)

    def test_output_is_deterministic_and_current(self):
        first=build_portable.build_html()
        second=build_portable.build_html()
        self.assertEqual(first, second)
        # Generated previews are intentionally untracked; test a clean checkout.
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / 'preview.html'
            with patch.object(build_portable, 'DESTINATION', destination), patch('sys.argv', ['build_portable']):
                build_portable.main()
                self.assertEqual(first, destination.read_bytes())
                with patch('sys.argv', ['build_portable', '--check']):
                    build_portable.main()

    def test_embedded_real_measurements_and_method(self):
        html=build_portable.build_html().decode('utf-8')
        self.assertIn('id="dayflare-evidence"',html)
        self.assertIn('"method_version":"v0-empirical-35d"',html)
        self.assertIn('"start":"20260811"',html)
        self.assertIn('"end":"20260914"',html)
        self.assertIn('<noscript>',html)
        self.assertEqual(html.count('<details class="nojs-topic">'),6)
        self.assertEqual(html.count('<tr><th scope="row">2026-'),210)

    def test_not_a_fake_public_page_or_live_source(self):
        html=build_portable.build_html().decode('utf-8')
        self.assertIn('NOT PUBLISHED',html)
        self.assertIn('not live',html)
        self.assertIn('public sharing awaits publication',html)
        self.assertNotIn('<link rel="stylesheet" href="styles.css">',html)
        self.assertNotIn('<script src="app.js" defer></script>',html)
        self.assertIn('Local-only version-bound link copied; not a public URL.',html)

    def test_offline_links_resolve_to_embedded_method_and_provenance(self):
        html=build_portable.build_html().decode('utf-8')
        self.assertIn('id="offline-method"', html)
        self.assertIn('id="offline-provenance"', html)
        self.assertIn('href="#offline-method"', html)
        self.assertIn('href="#offline-provenance"', html)
        self.assertIn('class="brand" href="#discover"', html)
        self.assertNotIn('href="../evidence/d02-20261018/', html)
        self.assertNotIn('class="brand" href="./"', html)
        self.assertIn(build_portable.EXPECTED['source.zip'], html)
        self.assertIn('No claims about causes, approval', html)
        self.assertIn('does <strong>not</strong> include the separate ZIP file', html)

    def test_modified_provenance_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)
            archive_root=path/'evidence/d02-20261018'
            archive_root.mkdir(parents=True)
            (archive_root/'source.zip').write_bytes(build_portable.ARCHIVE.read_bytes())
            raw=(build_portable.ROOT/'evidence/d02-20261018/provenance.json').read_bytes()
            (archive_root/'provenance.json').write_bytes(raw+b' ')
            site_root=path/'site'
            site_root.mkdir()
            for name in ('index.html','styles.css','app.js'):
                (site_root/name).write_bytes((build_portable.ROOT/'site'/name).read_bytes())
            with patch.object(build_portable,'ROOT',path), patch.object(build_portable,'ARCHIVE',archive_root/'source.zip'):
                with self.assertRaisesRegex(ValueError,'provenance document does not match'):
                    build_portable.build_html()

    def test_bad_archive_fails_closed_without_write(self):
        with tempfile.TemporaryDirectory() as td:
            corrupt=Path(td)/'source.zip'
            data=bytearray(build_portable.ARCHIVE.read_bytes())
            data[50]^=0x01
            corrupt.write_bytes(data)
            destination = Path(td) / 'preview.html'
            with patch.object(build_portable, 'DESTINATION', destination), patch('sys.argv', ['build_portable']):
                build_portable.main()
                before = destination.read_bytes()
                with patch.object(build_portable, 'ARCHIVE', corrupt):
                    with self.assertRaisesRegex(ValueError, 'does not match recorded SHA-256'):
                        build_portable.main()
                self.assertEqual(before, destination.read_bytes())


if __name__ == '__main__':
    unittest.main()
