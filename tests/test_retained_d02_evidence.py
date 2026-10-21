"""Real retained measurements plus explicitly mutated copies for negative controls."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import warnings
import zipfile

from tools.d01_probe import BASE, REQUESTS
from tools.d02_probe import START, END, weekly_metrics
from tools.verify_d02_artifacts import (
    EvidenceError, MAX_CAPSULE_BYTES, MAX_SAMPLE_BYTES,
    main, read_limited, read_retained, validate_artifacts,
)

FIXTURE = Path(__file__).resolve().parents[1] / 'evidence/d02-20261018'
SAMPLE_SHA = '69b6d5b83e761a0536de7ddd64569a859d75a279c4bb2607ed96e38e3d9423b0'


class RetainedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'fixture'
        shutil.copytree(FIXTURE, self.directory)

    def provenance(self):
        return json.loads((self.directory / 'provenance.json').read_text())

    def save_provenance(self, value):
        (self.directory / 'provenance.json').write_text(json.dumps(value), encoding='utf-8')

    def repack(self, entries):
        path = self.directory / 'source.zip'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in entries:
                    archive.writestr(name, data)
        p = self.provenance()
        p['capsule']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save_provenance(p)

    def test_real_fixture_has_all_210_observations_and_exact_metrics(self):
        sb, rb, p = read_retained(FIXTURE)
        result = validate_artifacts(sb, rb, requests=REQUESTS, start=START, end=END, base_url=BASE)
        self.assertEqual(result['observations'], 210)
        self.assertEqual(result['sample_sha256'], SAMPLE_SHA)
        self.assertEqual(p['source']['run_id'], 39112409117)
        self.assertEqual(p['source']['artifact_id'], 12130838093)
        sample, receipt = json.loads(sb), json.loads(rb)
        for row, recorded in zip(sample, receipt['series_metrics']):
            self.assertEqual(weekly_metrics(row['items']), recorded['metrics'])
        chess = receipt['series_metrics'][2]['metrics']
        self.assertEqual((chess['V'], chess['B'], chess['delta']), (19804, 18369.5, 1434.5))

    def test_cli_is_read_only_and_reports_historical_identity_limits(self):
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        with redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(main(['--retained', str(self.directory)]), 0)
        result = json.loads(stream.getvalue())
        self.assertEqual(result['dataset_id'], 'd02-20261018-084126')
        self.assertEqual(result['raw_http_body_verification'], 'NOT_POSSIBLE_FROM_NORMALIZED_SAMPLE')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir()})

    def test_archive_byte_mutation_is_rejected(self):
        p = self.directory / 'source.zip'
        p.write_bytes(p.read_bytes() + b'changed')
        with self.assertRaisesRegex(EvidenceError, 'capsule checksum'):
            read_retained(self.directory)

    def test_member_mutation_is_rejected_even_after_repacking(self):
        sb, rb, _ = read_retained(FIXTURE)
        self.repack([('sample.json', sb + b'\n'), ('receipt.json', rb)])
        with self.assertRaisesRegex(EvidenceError, 'member checksum/size'):
            read_retained(self.directory)

    def test_duplicate_members_are_rejected(self):
        sb, _, _ = read_retained(FIXTURE)
        self.repack([('sample.json', sb), ('sample.json', sb)])
        with self.assertRaisesRegex(EvidenceError, 'exactly'):
            read_retained(self.directory)

    def test_extra_or_traversal_members_are_rejected_without_extraction(self):
        sb, rb, _ = read_retained(FIXTURE)
        for entries in ([('sample.json', sb), ('receipt.json', rb), ('extra.py', b'pass')],
                        [('../sample.json', sb), ('receipt.json', rb)]):
            with self.subTest(names=[n for n, _ in entries]):
                self.repack(entries)
                with self.assertRaisesRegex(EvidenceError, 'exactly'):
                    read_retained(self.directory)
        self.assertFalse((self.directory.parent / 'sample.json').exists())

    def test_decompressed_member_budget_is_enforced(self):
        _, rb, _ = read_retained(FIXTURE)
        self.repack([('sample.json', b'x' * (MAX_SAMPLE_BYTES + 1)), ('receipt.json', rb)])
        with self.assertRaisesRegex(EvidenceError, 'byte budget'):
            read_retained(self.directory)

    def test_compressed_archive_budget_is_enforced(self):
        (self.directory / 'source.zip').write_bytes(b'x' * (MAX_CAPSULE_BYTES + 1))
        with self.assertRaisesRegex(EvidenceError, 'byte length'):
            read_retained(self.directory)

    def test_invalid_zip_returns_failed_cli_status(self):
        raw = b'not a zip'
        (self.directory / 'source.zip').write_bytes(raw)
        p = self.provenance()
        p['capsule']['sha256'] = hashlib.sha256(raw).hexdigest()
        self.save_provenance(p)
        with redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(['--retained', str(self.directory)]), 2)
        self.assertIn('invalid capsule', error.getvalue())

    def test_normalized_digest_claim_is_checked(self):
        p = self.provenance()
        p['normalized_sample_sha256'] = '0' * 64
        self.save_provenance(p)
        with redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(['--retained', str(self.directory)]), 2)
        self.assertIn('normalized sample checksum', error.getvalue())

    def test_capsule_path_cannot_select_a_different_file(self):
        p = self.provenance()
        p['capsule']['file'] = '../outside.zip'
        self.save_provenance(p)
        with self.assertRaisesRegex(EvidenceError, 'capsule path'):
            read_retained(self.directory)

    def test_explicit_input_modes_cannot_be_mixed(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit:
            main(['--retained', str(self.directory), '--sample', 'sample.json'])
        self.assertEqual(exit.exception.code, 2)

    def test_bounded_direct_file_read_rejects_oversize(self):
        path = self.directory / 'input.json'
        path.write_bytes(b'x' * 17)
        with self.assertRaisesRegex(EvidenceError, 'byte length'):
            read_limited(path, 16)


if __name__ == '__main__':
    unittest.main()
