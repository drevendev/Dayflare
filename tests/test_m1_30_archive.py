"""Strict offline preservation controls; fixtures are synthetic, never public data."""
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from tools.m1_30_archive import ArchiveError, build, canonical, digest, verify


class PreservationTests(unittest.TestCase):
    def synthetic(self):
        files = {}
        dates = [(date(2026, 10, 11) + timedelta(days=n)).isoformat()
                 for n in range(35)]
        candidate = {'dataset_id': 'SYNTHETIC-TEST-ONLY', 'observation_end': dates[-1],
                     'retrieved_at': '2026-11-17T08:30:55Z', 'series': []}
        receipt = {'observation_start': dates[0], 'observation_end': dates[-1],
                   'retrieved_at': candidate['retrieved_at'],
                   'publication_status': 'LOCAL_EVIDENCE_ONLY_NOT_PUBLISHED',
                   'requests_attempted': 30, 'sources': []}
        for edition in ('en.wikipedia', 'ru.wikipedia'):
            for subject in ('culture', 'books', 'games', 'science', 'sport'):
                for n in range(3):
                    pid = 10000 + len(candidate['series'])
                    title = f'{subject} Article {n}'
                    items = [{'timestamp': d.replace('-', '') + '00',
                              'project': edition, 'article': title.replace(' ', '_'),
                              'agent': 'user', 'access': 'all-access', 'granularity': 'daily',
                              'views': n + i} for i, d in enumerate(dates)]
                    raw = canonical({'items': items})
                    name = f'raw/{edition}.{pid}.json'
                    files['m1-30-source/' + name] = raw
                    receipt['sources'].append({'project': edition, 'page_id': pid,
                                               'subject': subject, 'http_status': 200,
                                               'raw_member': name, 'body_sha256': digest(raw),
                                               'response_bytes': len(raw)})
                    candidate['series'].append({'project': edition, 'page_id': pid,
                                                'title': title, 'access': 'all-access',
                                                'agent': 'user',
                                                'source': {'body_sha256': digest(raw)},
                                                'daily': [{'date': d, 'views': n + i,
                                                           'value_state': 'observed'}
                                                          for i, d in enumerate(dates)]})
        raw_candidate = canonical(candidate)
        files['m1-30-source/candidate.json'] = raw_candidate
        files['m1-identity/bundle-manifest.json'] = b'{"synthetic":true}\n'
        prefix = 'm1-30-stage/versions/' + digest(raw_candidate) + '/'
        files[prefix + 'candidate.json'] = raw_candidate
        files['m1-30-stage/current.json'] = canonical({'version_sha256': digest(raw_candidate)})
        files['m1-30-source/seeds.json'] = b'{"synthetic":true}\n'
        cand_sha = digest(raw_candidate)
        receipt.update({'candidate_sha256': cand_sha,
                        'seed_sha256': digest(files['m1-30-source/seeds.json'])})
        files['m1-30-source/source-receipt.json'] = canonical(receipt)
        files[prefix + 'source/source-receipt.json'] = canonical(receipt)
        html = b'<!doctype html><title>SYNTHETIC TEST ONLY</title>'
        files['index.html'] = files['m1-30-preview/index.html'] = html
        files['m1-30-preview/preview-manifest.json'] = canonical({
            'candidate_sha256': cand_sha, 'html_sha256': digest(html),
            'series': 30, 'source_seed_sha256': receipt['seed_sha256'],
            'publication_status': 'LOCAL_PREVIEW_NOT_PUBLISHED'})
        files['m1-30-pageview-run.json'] = canonical({
            'candidate_sha256': cand_sha, 'html_sha256': digest(html),
            'source_commit': 'a' * 40,
            'identity_manifest_sha256': digest(files['m1-identity/bundle-manifest.json']),
            'selected_titles': 30,
            'daily_observations': 1050, 'status': 'UNPUBLISHED_SOURCE_REVIEW_REQUIRED'})
        shots = []
        for width in (320, 390, 1280):
            name = f'{width}.png'
            files['m1-30-browser/' + name] = b'SYNTHETIC SCREENSHOT' + str(width).encode()
            shots.append({'width': width, 'document_width': width,
                          'screenshot': name,
                          'sha256': digest(files['m1-30-browser/' + name])})
        files['m1-30-browser/receipt.json'] = canonical({
            'mode': 'LOCAL_HTTP_NOT_PUBLIC',
            'status': 'NOT_PUBLISHED_NOT_LIVE_VERIFIED',
            'html_sha256': digest(html), 'screenshots': shots})
        return files

    def test_exact_30_35_with_synthetic_positive(self):
        facts = verify(self.synthetic())
        self.assertEqual((facts['series'], facts['daily_observations']), (30, 1050))

    def test_reject_missing_raw_even_when_summary_exists(self):
        files = self.synthetic()
        del files['m1-30-source/raw/en.wikipedia.10000.json']
        with self.assertRaisesRegex(ArchiveError, 'source body corruption'):
            verify(files)

    def test_reject_tampered_raw_even_when_summary_exists(self):
        files = self.synthetic()
        key = 'm1-30-source/raw/en.wikipedia.10000.json'
        files[key] += b' '
        with self.assertRaisesRegex(ArchiveError, 'source body corruption'):
            verify(files)

    def test_reject_modified_history_even_when_candidate_pin_updated(self):
        files = self.synthetic()
        key = 'm1-30-source/raw/en.wikipedia.10000.json'
        changed = files[key].replace(b'"views":0', b'"views":9', 1)
        record = __import__('json').loads(files['m1-30-source/source-receipt.json'])
        record['sources'][0]['body_sha256'] = digest(changed)
        record['sources'][0]['response_bytes'] = len(changed)
        files[key] = changed
        files['m1-30-source/source-receipt.json'] = canonical(record)
        csha = digest(files['m1-30-source/candidate.json'])
        files[f'm1-30-stage/versions/{csha}/source/source-receipt.json'] = canonical(record)
        with self.assertRaisesRegex(ArchiveError, 'candidate differs from retained raw day'):
            verify(files)

    def test_reject_screenshot_corruption(self):
        files = self.synthetic()
        files['m1-30-browser/320.png'] = b'FAKE'
        with self.assertRaisesRegex(ArchiveError, 'browser screenshot/width mismatch'):
            verify(files)

    def test_deterministic_archive_and_no_overwrite(self):
        files = self.synthetic()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            src = root / 'synthetic.zip'
            with ZipFile(src, 'w') as z:
                for k, v in files.items():
                    z.writestr(k, v)
            a = build(src, root / 'one.zip')
            b = build(src, root / 'two.zip')
            self.assertEqual(a['archive_sha256'], b['archive_sha256'])
            with ZipFile(root / 'one.zip') as z:
                self.assertIn('archive-manifest.json', z.namelist())
                self.assertIn('m1-30-browser/1280.png', z.namelist())
            with self.assertRaisesRegex(ArchiveError, 'destination already exists'):
                build(src, root / 'one.zip')


if __name__ == '__main__':
    unittest.main()