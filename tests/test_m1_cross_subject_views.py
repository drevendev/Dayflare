"""Offline controls; synthetic fixtures are NOT Wikimedia retrieval receipts."""
from __future__ import annotations
import io
import json
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import m1_cross_subject_views as p


class Response(io.BytesIO):
    status = 200

    @property
    def headers(self):
        return {'Content-Length': str(len(self.getbuffer()))}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def body(request, *, invalid=False):
    url = request.full_url
    spec = next(s for s in p.REQUESTS if s['project'] in url and
                p.quote(s['article'], safe='') in url)
    records = []
    for i in range(35):
        day = date(2026, 8, 11) + timedelta(days=i)
        records.append({'project': spec['project'].removesuffix('.org'),
                        'article': spec['article'], 'access': 'all-access', 'agent': 'user',
                        'granularity': 'daily', 'timestamp': day.strftime('%Y%m%d') + '00',
                        'views': i + 1})
    if invalid:
        records[4]['project'] = 'unexpected.wikipedia'
    return json.dumps({'items': records}).encode('utf-8')


class CrossSubjectViewsTest(unittest.TestCase):
    def test_exact_four_series_with_provenance_and_no_overwrite(self):
        calls, sleeps = [], []
        def open_ok(req, timeout):
            self.assertEqual(timeout, 20)
            self.assertIn('Dayflare', req.headers['User-agent'])
            calls.append(req.full_url)
            return Response(body(req))
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'observations'
            self.assertEqual(p.collect(out, opener=open_ok, pause=sleeps.append, clock=lambda: 0), 0)
            receipt = json.loads((out / 'receipt.json').read_text())
            sample = json.loads((out / 'sample.json').read_text())
            self.assertEqual(receipt['status'], 'UNPUBLISHED_REVIEW_REQUIRED')
            self.assertEqual((len(calls), len(sleeps), len(sample)), (4, 3, 4))
            self.assertEqual(sleeps, [2, 2, 2])
            self.assertTrue(all(len(x['items']) == 35 for x in sample))
            self.assertTrue(all(x['metrics']['V'] == sum(range(29, 36)) for x in sample))
            for i, r in enumerate(receipt['receipts']):
                original = (out / f'source-{i:02d}.json').read_bytes()
                self.assertEqual(r['source_sha256'], p.sha(original))
            with self.assertRaises(FileExistsError):
                p.collect(out, opener=open_ok, pause=sleeps.append, clock=lambda: 0)

    def test_semantically_invalid_response_is_unavailable_not_zero(self):
        requests = []
        def bad_response(req, timeout):
            requests.append(req.full_url)
            return Response(body(req, invalid=len(requests) == 1))
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'invalid'
            self.assertEqual(p.collect(out, opener=bad_response, pause=lambda _: None, clock=lambda: 0), 2)
            receipt = json.loads((out / 'receipt.json').read_text())
            sample = json.loads((out / 'sample.json').read_text())
            self.assertEqual(receipt['status'], 'INVALID_UNPUBLISHED')
            self.assertFalse(receipt['receipts'][0]['valid'])
            self.assertIsNone(sample[0]['items'])
            self.assertIsNone(sample[0]['metrics'])
            self.assertTrue(all(r['valid'] for r in receipt['receipts'][1:]))

    def test_slow_responses_enforce_longer_pause(self):
        calls = iter([0, 1.3, 1.3, 1.4, 1.4, 1.5, 1.5, 1.6])
        pauses = []
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(p.collect(Path(temp)/'slow', opener=lambda req,timeout: Response(body(req)),
                                       pause=pauses.append, clock=lambda: next(calls)), 0)
        self.assertEqual(pauses, [5, 2, 2])


if __name__ == '__main__':
    unittest.main()
