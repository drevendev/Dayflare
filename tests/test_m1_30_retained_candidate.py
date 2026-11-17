"""Regression tests for byte-pinned retained real EN/RU normalized evidence."""
import base64
import json
import lzma
from pathlib import Path
import tempfile
import unittest

from tools.m1_30_retained_candidate import (
    ARMOR_PATH, CANDIDATE_SHA256, CANDIDATE_SIZE, CandidateError,
    read_candidate,
)
from hashlib import sha256


class RetainedCandidateTests(unittest.TestCase):
    def test_exact_candidate_and_complete_dates(self):
        original, candidate = read_candidate()
        self.assertEqual(len(original), CANDIDATE_SIZE)
        self.assertEqual(sha256(original).hexdigest(), CANDIDATE_SHA256)
        self.assertEqual(len(candidate['series']), 30)
        self.assertEqual(sum(len(s['daily']) for s in candidate['series']), 1050)
        self.assertEqual({s['project'] for s in candidate['series']},
                         {'en.wikipedia', 'ru.wikipedia'})
        self.assertTrue(all(s['daily'][0]['date'] == '2026-10-11'
                            and s['daily'][-1]['date'] == '2026-11-14'
                            for s in candidate['series']))

    def test_deterministic_exact_original_bytes(self):
        self.assertEqual(read_candidate()[0], read_candidate()[0])
        self.assertEqual(read_candidate()[0], json.dumps(
            read_candidate()[1], sort_keys=True, ensure_ascii=False,
            separators=(',', ':')).encode() + b'\n')

    def test_missing_truncated_modified_trailing_and_unapproved_are_rejected(self):
        armor = ARMOR_PATH.read_text('ascii')
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'candidate.xz.b64'
            for bad in ('', armor[:-10] + '\n', 'A' + armor[1:],
                        armor[:-1] + '====\n', '  ' + armor,
                        armor[:-1] + '\n\n', armor + '!',
                        base64.b64encode(lzma.compress(b'{}')).decode() + '\n'):
                with self.subTest(corrupt=bad[:25]):
                    p.write_text(bad)
                    with self.assertRaises(CandidateError):
                        read_candidate(p)
            with self.assertRaises(CandidateError):
                read_candidate(Path(td) / 'missing')

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'linked'
            p.symlink_to(ARMOR_PATH)
            with self.assertRaises(CandidateError):
                read_candidate(p)


if __name__ == '__main__':
    unittest.main()
