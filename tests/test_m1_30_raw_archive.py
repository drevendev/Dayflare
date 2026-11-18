"""Regression controls for the 2026-11-17 exact raw Pageviews retention."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
import sys
from unittest.mock import patch
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from tools.m1_30_raw_archive import (ARMOR, RECEIPT_ARMOR, RawArchiveError,
                                     read_raw_archive, read_source_receipt, main,
                                     read_pinned_xz, RECEIPT_ARMOR_SIZE,
                                     RECEIPT_XZ_SHA256, RECEIPT_JSON_SIZE,
                                     RECEIPT_JSON_SHA256)
from tools.m1_30_retained_candidate import read_candidate


class RawSourceArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate_raw, cls.candidate = read_candidate()

    def test_exact_30_original_http_bodies(self):
        bodies = read_raw_archive(self.candidate)
        self.assertEqual(len(bodies), 30)
        self.assertEqual(sum(len(v) for v in bodies.values()), 159888)
        for row in self.candidate['series']:
            name = f"{row['project']}.{row['page_id']}.json"
            self.assertEqual(sha256(bodies[name]).hexdigest(), row['source']['body_sha256'])
        self.assertEqual(sum(len(row['daily']) for row in self.candidate['series']), 1050)
        receipt = read_source_receipt(self.candidate, bodies)
        self.assertEqual(receipt['requests_attempted'], 30)
        self.assertEqual(receipt['total_decoded_bytes'], 159888)

    def test_reject_modified_or_truncated_b64(self):
        text = ARMOR.read_text('ascii')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'changed.xz.b64'
            for corrupted in (text[:-2] + 'A\n', text[:-5] + '\n', text[:-1] + 'A\n',
                              text[:-1] + '\n\n'):
                p.write_text(corrupted, encoding='ascii')
                with self.subTest(length=len(corrupted)):
                    with self.assertRaises(RawArchiveError):
                        read_raw_archive(self.candidate, p)

    def test_reject_corrupt_original_source_receipt(self):
        text = RECEIPT_ARMOR.read_text('ascii')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'receipt.xz.b64'
            p.write_text(text[:-5] + 'AAAA\n', encoding='ascii')
            with self.assertRaises(RawArchiveError):
                read_raw_archive(self.candidate, receipt_path=p)

    def test_reject_candidate_checksum_or_count_mismatch(self):
        modified = deepcopy(self.candidate)
        modified['series'][0]['source']['body_sha256'] = '0' * 64
        with self.assertRaisesRegex(RawArchiveError, 'exact-byte mismatch'):
            read_raw_archive(modified)
        modified = deepcopy(self.candidate)
        modified['series'][0]['daily'][0]['views'] += 1
        with self.assertRaisesRegex(RawArchiveError, 'count mismatch'):
            read_raw_archive(modified)

    def test_reject_duplicate_source_identity(self):
        modified = deepcopy(self.candidate)
        modified['series'][0] = modified['series'][1]
        with self.assertRaisesRegex(RawArchiveError, 'identity/coverage mismatch'):
            read_raw_archive(modified)

    def test_reject_symlink_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / 'linked.b64'
            link.symlink_to(ARMOR)
            with self.assertRaisesRegex(RawArchiveError, 'linked'):
                read_raw_archive(self.candidate, link)


    def test_cli_opt_in_restores_exact_original_receipt(self):
        expected = read_pinned_xz(RECEIPT_ARMOR, RECEIPT_ARMOR_SIZE,
                                  RECEIPT_XZ_SHA256, RECEIPT_JSON_SIZE,
                                  RECEIPT_JSON_SHA256)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'restored'
            out = StringIO()
            with patch.object(sys, 'argv', ['archive', '--output', str(target),
                                            '--include-receipt']), redirect_stdout(out):
                main()
            self.assertEqual(len(list(target.iterdir())), 31)
            self.assertEqual((target / 'source-receipt.json').read_bytes(), expected)
            self.assertEqual(sha256(expected).hexdigest(), RECEIPT_JSON_SHA256)
            self.assertTrue(json.loads(out.getvalue())['original_receipt_restored'])
            for row in self.candidate['series']:
                name = f"{row['project']}.{row['page_id']}.json"
                self.assertEqual(sha256((target / name).read_bytes()).hexdigest(),
                                 row['source']['body_sha256'])
            with patch.object(sys, 'argv', ['archive', '--output', str(target),
                                            '--include-receipt']):
                with self.assertRaisesRegex(RawArchiveError, 'destination must be new'):
                    main()

    def test_cli_receipt_flag_requires_output_without_creating_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(sys, 'argv', ['archive', '--include-receipt']):
                with self.assertRaisesRegex(RawArchiveError, 'requires --output'):
                    main()
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_cli_default_output_remains_30_raw_bodies(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'default'
            with patch.object(sys, 'argv', ['archive', '--output', str(target)]):
                with redirect_stdout(StringIO()) as out:
                    main()
            self.assertEqual(len(list(target.iterdir())), 30)
            self.assertFalse((target / 'source-receipt.json').exists())
            self.assertFalse(json.loads(out.getvalue())['original_receipt_restored'])


if __name__ == '__main__':
    unittest.main()
