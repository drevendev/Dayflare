"""Regression controls for the 2026-11-17 exact raw Pageviews retention."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from tools.m1_30_raw_archive import ARMOR, RECEIPT_ARMOR, RawArchiveError, read_raw_archive, read_source_receipt
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


if __name__ == '__main__':
    unittest.main()
