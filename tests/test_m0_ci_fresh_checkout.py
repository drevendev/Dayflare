"""Cold-checkout CI generates test inputs without committing build artifacts."""
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from tools import run_m0_ci


class FreshCheckoutPreviewTests(TestCase):
    def test_generates_missing_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'generated.html'
            with patch.object(run_m0_ci, 'DESTINATION', target), patch.object(run_m0_ci, 'build_html', return_value=b'valid'):
                run_m0_ci.ensure_portable_preview()
            self.assertEqual(target.read_bytes(), b'valid')

    def test_existing_valid_file_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'generated.html'
            target.write_bytes(b'valid')
            with patch.object(run_m0_ci, 'DESTINATION', target), patch.object(run_m0_ci, 'build_html', return_value=b'valid'):
                run_m0_ci.ensure_portable_preview()
            self.assertEqual(target.read_bytes(), b'valid')

    def test_stale_file_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'generated.html'
            target.write_bytes(b'stale')
            with patch.object(run_m0_ci, 'DESTINATION', target), patch.object(run_m0_ci, 'build_html', return_value=b'valid'):
                with self.assertRaisesRegex(SystemExit, 'Stale generated'):
                    run_m0_ci.ensure_portable_preview()
            self.assertEqual(target.read_bytes(), b'stale')
