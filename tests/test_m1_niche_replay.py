"""Historical source transport controls and real-source replay regression."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from tools.m1_niche_replay import PARTS, NAMES, ZIP_SHA256, archive_bytes, restore, replay


class NicheReplayTests(unittest.TestCase):
    def test_original_bytes_and_inventory(self):
        raw = archive_bytes()
        self.assertEqual(len(raw), 18402)
        self.assertEqual(sha256(raw).hexdigest(), ZIP_SHA256)
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(len(archive.namelist()), 22)
            self.assertIsNone(archive.testzip())

    def test_restore_exact_and_refuse_overwrite(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'original.zip'
            restore(target)
            self.assertEqual(target.read_bytes(), archive_bytes())
            with self.assertRaises(ValueError):
                restore(target)
            self.assertEqual(target.read_bytes(), archive_bytes())

    def test_tamper_rejected_before_output(self):
        with TemporaryDirectory() as tmp:
            parts = Path(tmp) / 'parts'
            shutil.copytree(PARTS, parts)
            part = parts / NAMES[0]
            raw = part.read_bytes()
            part.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            target = Path(tmp) / 'original.zip'
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                restore(target, parts)
            self.assertFalse(target.exists())

    def test_inventory_and_links_rejected(self):
        with TemporaryDirectory() as tmp:
            parts = Path(tmp) / 'parts'
            shutil.copytree(PARTS, parts)
            extra = parts / 'extra.bin'
            extra.touch()
            with self.assertRaisesRegex(ValueError, 'unexpected archive parts'):
                archive_bytes(parts)
            extra.unlink()
            part = parts / NAMES[0]
            part.unlink()
            with self.assertRaisesRegex(ValueError, 'unexpected archive parts'):
                archive_bytes(parts)
            part.symlink_to(PARTS / NAMES[0])
            with self.assertRaisesRegex(ValueError, 'linked archive part'):
                archive_bytes(parts)

    def test_real_source_replays_deterministically(self):
        with TemporaryDirectory() as tmp:
            first, second = Path(tmp) / 'first', Path(tmp) / 'second'
            a, b = replay(first), replay(second)
            self.assertEqual(a, b)
            self.assertEqual(a['preview']['series'], 19)
            self.assertEqual(a['preview']['observation_end'], '2026-11-23')
            self.assertEqual(a['preview']['retrieved_at'], '2026-11-26T05:24:57Z')
            self.assertEqual(a['preview']['candidate_sha256'],
                             '10f78c6ab626a6ff2845b4db3e2e207144389ed387f88e22d31f4eeeeaaa905e')
            self.assertEqual(a['preview']['source_seed_sha256'],
                             '955fa064c3480ffb1302802d8c822de81f3a7a6476039771560113de254543ef')
            self.assertEqual(a['preview']['publication_status'], 'LOCAL_PREVIEW_NOT_PUBLISHED')
            self.assertEqual((first / 'index.html').read_bytes(), (second / 'index.html').read_bytes())
            self.assertEqual((first / 'preview-manifest.json').read_bytes(),
                             (second / 'preview-manifest.json').read_bytes())
            with self.assertRaises(ValueError):
                replay(first)


if __name__ == '__main__':
    unittest.main()
