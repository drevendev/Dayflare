import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools import m1_additional_replay as replay


class AdditionalReplayTests(unittest.TestCase):
    def test_exact_members_and_daily_values(self):
        raw = replay.members()
        candidate = json.loads(raw['candidate.json'])
        self.assertEqual(len(candidate['series']), 10)
        for row in candidate['series']:
            source = json.loads(raw[f"raw/{row['project']}.{row['page_id']}.json"])
            self.assertEqual(len(row['daily']), 35)
            self.assertEqual([x['views'] for x in row['daily']],
                             [x['views'] for x in source['items']])
        self.assertEqual(len(raw), 13)

    def test_restore_and_refuse_overwrite(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'restored'
            replay.restore(dest)
            self.assertEqual({str(p.relative_to(dest)): p.read_bytes() for p in dest.rglob('*')
                              if p.is_file()}, replay.members())
            with self.assertRaises(ValueError):
                replay.restore(dest)

    def test_corrupt_and_linked_capsule_rejected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'capsule'
            raw = replay.CAPSULE.read_bytes()
            path.write_bytes(b'A' + raw[1:])
            with self.assertRaises(ValueError):
                replay.members(path)
            path.write_bytes(raw + b'\n')
            with self.assertRaises(ValueError):
                replay.members(path)
            linked = Path(tmp) / 'linked'
            linked.symlink_to(replay.CAPSULE)
            with self.assertRaises(ValueError):
                replay.members(linked)

    def test_canonical_renderer_deterministic(self):
        with TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a', Path(tmp) / 'b'
            for dest in (a, b):
                replay.replay(dest)
            self.assertEqual((a / 'index.html').read_bytes(), (b / 'index.html').read_bytes())
            manifest = json.loads((a / 'preview-manifest.json').read_bytes())
            self.assertEqual(manifest['candidate_sha256'], replay.CANDIDATE_SHA)
            self.assertEqual(manifest['series'], 10)
            self.assertEqual(manifest['publication_status'], 'LOCAL_PREVIEW_NOT_PUBLISHED')
