"""Real dated source retention regression; not browser or release acceptance."""
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.m1_30_source_capsule import replay, unpack

CAPSULE = Path(__file__).resolve().parents[1] / 'evidence/m1-30-20261124-source.xz.b64'
ORIGINAL_PIN = '1721869d687dd5f1b08b9ba9dcd963f8477299151f7f1c5f24090222c14fc305'
CAPSULE_PIN = '10d7fa4ed4b7c2bdab98d3c7d4c64a70d12b27aa15df5d4fd67f16194b93c543'
CANDIDATE_PIN = 'be8e6faf5f6e85e9508940bdb3547094efae508106551940800c1c33c766f874'
SEED_PIN = 'cc9190bc7eba6c0f4d37dc249c4b8c349749aee0cdc1d9e69885449582e29f6f'


class RetainedSourceTests(unittest.TestCase):
    def test_exact_source_and_offline_replay(self):
        members = unpack(CAPSULE, CAPSULE_PIN, ORIGINAL_PIN)
        self.assertEqual(len(members), 33)
        self.assertEqual(sum(map(len, members.values())), 256360)
        self.assertEqual(sha256(members['candidate.json']).hexdigest(), CANDIDATE_PIN)
        self.assertEqual(sha256(members['seeds.json']).hexdigest(), SEED_PIN)
        candidate = json.loads(members['candidate.json'])
        self.assertEqual(len(candidate['series']), 30)
        self.assertTrue(all(len(row['daily']) == 35 for row in candidate['series']))
        self.assertEqual(sum(len(row['daily']) for row in candidate['series']), 1050)

        with TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a', Path(tmp) / 'b'
            first = replay(CAPSULE, a, CAPSULE_PIN, ORIGINAL_PIN)
            second = replay(CAPSULE, b, CAPSULE_PIN, ORIGINAL_PIN)
            self.assertEqual(first, second)
            manifest = first['preview']
            self.assertEqual(manifest['candidate_sha256'], CANDIDATE_PIN)
            self.assertEqual(manifest['source_seed_sha256'], SEED_PIN)
            self.assertEqual(manifest['dataset_id'], 'run-20261124-152435-cc9190bc7eba')
            self.assertEqual(manifest['observation_end'], '2026-11-21')
            self.assertEqual(manifest['retrieved_at'], '2026-11-24T15:24:35Z')
            self.assertEqual(manifest['series'], 30)
            self.assertEqual(manifest['publication_status'], 'LOCAL_PREVIEW_NOT_PUBLISHED')
            for filename in ('index.html', 'preview-manifest.json'):
                self.assertEqual((a / filename).read_bytes(), (b / filename).read_bytes())
            self.assertEqual(sha256((a / 'index.html').read_bytes()).hexdigest(),
                             manifest['html_sha256'])
            print('Retained 24 Nov replay HTML SHA-256:', manifest['html_sha256'])


if __name__ == '__main__':
    unittest.main()
