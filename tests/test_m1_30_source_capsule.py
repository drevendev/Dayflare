"""Synthetic transport tests; no source or public release acceptance."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from tools.m1_30_source_capsule import PREFIX, digest, pack, unpack


class CapsuleTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / 'original.zip'
        self.capsule = self.root / 'source.xz.b64'
        self.members = {name: b'{}\n' for name in ('candidate.json', 'seeds.json', 'source-receipt.json')}
        self.members.update({f'raw/{edition}.wikipedia.{i}.json':
                             json.dumps({'title': 'Книга', 'i': i}, ensure_ascii=False).encode()
                             for edition in ('en', 'ru') for i in range(1, 16)})

    def archive(self):
        with ZipFile(self.source, 'w') as archive:
            for name, value in self.members.items():
                archive.writestr(PREFIX + name, value)
        return digest(self.source.read_bytes())

    def test_exact_roundtrip_and_determinism(self):
        pin = self.archive()
        data = pack(self.source, pin)
        self.assertEqual(data, pack(self.source, pin))
        self.capsule.write_bytes(data)
        self.assertEqual(unpack(self.capsule, digest(data), pin), self.members)

    def test_independent_pins(self):
        pin = self.archive()
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            pack(self.source, '0' * 64)
        data = pack(self.source, pin)
        self.capsule.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'original ZIP pin'):
            unpack(self.capsule, digest(data), '0' * 64)
        self.capsule.write_bytes(data + b'\n')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            unpack(self.capsule, digest(data), pin)

    def test_unexpected_member(self):
        self.members['raw/../escape.json'] = b'{}'
        pin = self.archive()
        with self.assertRaisesRegex(ValueError, 'inventory'):
            pack(self.source, pin)


if __name__ == '__main__':
    unittest.main()
