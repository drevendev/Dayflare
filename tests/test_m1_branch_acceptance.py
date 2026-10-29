"""Hermetic failure cases for read-only acceptance of M1 publication bytes."""
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest

from tools.m1_branch_acceptance import ReleaseError, verify

START = date(2026, 9, 22)
END = date(2026, 10, 26)
RETRIEVED = "2026-10-29T04:21:16Z"
CANDIDATE = "a" * 64


def fixture():
    cards = "".join(
        f'<div class="card" data-series="detail-{i}" data-edition="{("en.wikipedia" if i<10 else "ru.wikipedia")}" '
        f'data-subject="{("books", "culture", "games", "science", "sport")[i%5]}"><a href="#detail-{i}">Open</a></div>'
        for i in range(20)
    )
    headings = "".join(
        f'<th data-week-start="{START + timedelta(days=7*i)}" '
        f'data-week-end="{START + timedelta(days=7*i+6)}">week</th>' for i in range(5)
    )
    compare = ('<table id="compare-table"><thead><tr>' + headings + '</tr></thead><tbody>' +
               "".join(f'<tr data-series="detail-{i}"><td>1</td></tr>' for i in range(20)) +
               '</tbody></table>')
    details = "".join(
        f'<article id="detail-{i}"><table><tbody>' + '<tr><td>123</td></tr>'*35 +
        '</tbody></table></article>' for i in range(20)
    )
    required = ('main overview atlas-filters atlas-query atlas-edition atlas-subject atlas-empty '
                'compare-empty compare-csv compare-csv-status atlas-filter-warning').split()
    nodes = "".join(f'<div id="{key}"></div>' for key in required)
    share = f'<section id="share-restore" data-dataset="{CANDIDATE}" data-method="v0-empirical-35d" data-end="{END}"></section>'
    html = ('<!doctype html><html><body>DATED SOURCE EVIDENCE '
            'This archived snapshot is <strong>not</strong> a live feed '
            f'{END} {RETRIEVED}' + nodes + share + cards + compare + details + '</body></html>').encode()
    manifest = {
        'schema_version': 'dayflare.m1.static-snapshot.v1',
        'dataset_id': 'run-20261029-042116-' + 'b'*12,
        'method_version': 'v0-empirical-35d', 'observation_end': str(END),
        'retrieved_at': RETRIEVED, 'candidate_sha256': CANDIDATE,
        'html_sha256': sha256(html).hexdigest(), 'source_receipt_sha256': 'c'*64,
        'source_seed_sha256': 'd'*64, 'series': 20, 'daily_observations': 700,
        'status': 'DATED_ARCHIVE_NOT_LIVE',
    }
    return html, manifest


def pack(root: Path, html: bytes, manifest: dict):
    dest = root / 'm1'
    dest.mkdir(exist_ok=True)
    (dest / 'index.html').write_bytes(html)
    payload = (json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n').encode()
    (dest / 'release-manifest.json').write_bytes(payload)
    return sha256(payload).hexdigest()


class BranchAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.html, self.manifest = fixture()
        self.pin = pack(self.root, self.html, self.manifest)

    def test_release_is_structurally_complete_not_claimed_deployed(self):
        result = verify(self.root, self.pin)
        self.assertEqual(result['status'], 'BRANCH_BYTES_VERIFIED_NOT_DEPLOYED')
        self.assertEqual((result['cards'], result['daily_rows'], result['comparison_rows']), (20,700,20))

    def test_missing_accepted_pin_fails_closed(self):
        with self.assertRaisesRegex(ReleaseError, 'independently accepted'):
            verify(self.root, '0'*64)

    def test_html_tamper_rejected(self):
        (self.root / 'm1/index.html').write_bytes(self.html.replace(b'123', b'999', 1))
        with self.assertRaisesRegex(ReleaseError, 'HTML bytes'):
            verify(self.root, self.pin)

    def test_manifest_unexpected_status_rejected_even_if_rehashed(self):
        self.manifest['status'] = 'LIVE'
        pin = pack(self.root, self.html, self.manifest)
        with self.assertRaisesRegex(ReleaseError, 'status'):
            verify(self.root, pin)

    def test_missing_daily_row_rejected(self):
        html = self.html.replace(b'<tr><td>123</td></tr>', b'', 1)
        self.manifest['html_sha256'] = sha256(html).hexdigest()
        pin = pack(self.root, html, self.manifest)
        with self.assertRaisesRegex(ReleaseError, '700 exact daily rows'):
            verify(self.root, pin)

    def test_duplicate_series_rejected(self):
        html = self.html.replace(b'data-series="detail-1"', b'data-series="detail-0"', 1)
        self.manifest['html_sha256'] = sha256(html).hexdigest()
        pin = pack(self.root, html, self.manifest)
        with self.assertRaisesRegex(ReleaseError, 'duplicate entries'):
            verify(self.root, pin)

    def test_nonconsecutive_windows_rejected(self):
        html = self.html.replace(b'data-week-start="2026-09-29"', b'data-week-start="2026-09-28"', 1)
        self.manifest['html_sha256'] = sha256(html).hexdigest()
        pin = pack(self.root, html, self.manifest)
        with self.assertRaisesRegex(ReleaseError, 'nonconsecutive'):
            verify(self.root, pin)

    def test_share_version_mismatch_rejected(self):
        html = self.html.replace(b'data-dataset="' + CANDIDATE.encode(), b'data-dataset="' + b'e'*64)
        self.manifest['html_sha256'] = sha256(html).hexdigest()
        pin = pack(self.root, html, self.manifest)
        with self.assertRaisesRegex(ReleaseError, 'share restoration'):
            verify(self.root, pin)


if __name__ == '__main__':
    unittest.main()
