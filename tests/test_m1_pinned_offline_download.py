"""Exact pinned GitHub raw download behavior on local HTTP, with no provider calls."""
import contextlib
import hashlib
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest

from tools.m1_pinned_offline_download import download, release_root
from tools.verify_public_release import VerificationError

COMMIT = 'c30b253e96a29cde1f14cc59fd08878b74997323'
DATASET = 'run-20261113-032300-a32c03ef7daa'
END = '2026-11-10'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture(html=b'<!doctype html><title>Offline fixture</title>'):
    doc = {'candidate_sha256': 'a' * 64, 'daily_observations': 700,
           'dataset_id': DATASET, 'html_sha256': digest(html),
           'method_version': 'v0-empirical-35d', 'observation_end': END,
           'retrieved_at': '2026-11-13T03:23:00Z',
           'schema_version': 'dayflare.m1.static-snapshot.v1',
           'series': 20, 'source_receipt_sha256': 'b' * 64,
           'source_seed_sha256': 'c' * 64,
           'status': 'DATED_ARCHIVE_NOT_LIVE'}
    return html, json.dumps(doc, sort_keys=True, separators=(',', ':')).encode() + b'\n'


@contextlib.contextmanager
def serve(html, manifest, *, altered_html=None, redirect=False, bad_type=False):
    folder = tempfile.TemporaryDirectory()
    root = Path(folder.name) / 'drevendev' / 'Dayflare' / COMMIT / 'm1'
    root.mkdir(parents=True)
    (root / 'index.html').write_bytes(altered_html if altered_html is not None else html)
    (root / 'release-manifest.json').write_bytes(manifest)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=folder.name, **kwargs)
        def log_message(self, *args):
            pass
        def guess_type(self, path):
            if bad_type and path.endswith('index.html'):
                return 'image/png'
            return 'text/plain' if path.endswith('index.html') else super().guess_type(path)
        def do_GET(self):
            if redirect and self.path.endswith('release-manifest.json'):
                self.send_response(302)
                self.send_header('Location', '/different')
                self.end_headers()
                return
            return super().do_GET()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/drevendev/Dayflare/{COMMIT}/m1/'
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
        folder.cleanup()


class PinnedOfflineDownloadTests(unittest.TestCase):
    def attempt(self, html, manifest, *, expected_pin=None, **kwargs):
        with tempfile.TemporaryDirectory() as tmp, serve(html, manifest, **kwargs) as url:
            output = Path(tmp) / 'atlas.html'
            result = download(COMMIT, expected_pin or digest(manifest), DATASET, END,
                              output, base_url=url, allow_loopback_http=True)
            self.assertEqual(output.read_bytes(), html)
            return result

    def test_pinned_release_downloads_exact_html(self):
        html, manifest = fixture()
        result = self.attempt(html, manifest)
        self.assertEqual(result['status'], 'OFFLINE_BYTES_VERIFIED_NOT_DEPLOYED')
        self.assertEqual(result['html_sha256'], digest(html))
        self.assertEqual(result['source_commit'], COMMIT)
        self.assertEqual(result['dataset_id'], DATASET)

    def test_base_is_immutable_commit_not_mutable_branch(self):
        self.assertEqual(release_root(COMMIT),
                         f'https://raw.githubusercontent.com/drevendev/Dayflare/{COMMIT}/m1/')
        for wrong in ('gh-pages', 'A' * 40, COMMIT[:-1], '../foo', 'x' * 40):
            with self.subTest(wrong=wrong), self.assertRaises(VerificationError):
                release_root(wrong)

    def test_wrong_manifest_pin_cannot_create_output(self):
        html, manifest = fixture()
        with tempfile.TemporaryDirectory() as tmp, serve(html, manifest) as url:
            path = Path(tmp) / 'result.html'
            with self.assertRaisesRegex(VerificationError, 'independently accepted'):
                download(COMMIT, '0' * 64, DATASET, END, path,
                         base_url=url, allow_loopback_http=True)
            self.assertFalse(path.exists())

    def test_corrupt_html_rejected_without_writing(self):
        html, manifest = fixture()
        with tempfile.TemporaryDirectory() as tmp, serve(html, manifest, altered_html=html+b'tampered') as url:
            path = Path(tmp) / 'result.html'
            with self.assertRaisesRegex(VerificationError, 'HTML differs'):
                download(COMMIT, digest(manifest), DATASET, END, path,
                         base_url=url, allow_loopback_http=True)
            self.assertFalse(path.exists())

    def test_existing_destination_is_never_overwritten(self):
        html, manifest = fixture()
        with tempfile.TemporaryDirectory() as tmp, serve(html, manifest) as url:
            path = Path(tmp) / 'result.html'
            path.write_bytes(b'last valid accepted release')
            with self.assertRaisesRegex(VerificationError, 'Destination exists'):
                download(COMMIT, digest(manifest), DATASET, END, path,
                         base_url=url, allow_loopback_http=True)
            self.assertEqual(path.read_bytes(), b'last valid accepted release')

    def test_redirect_and_wrong_type_fail_closed(self):
        html, manifest = fixture()
        for condition in ({'redirect': True}, {'bad_type': True}):
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as tmp, serve(html, manifest, **condition) as url:
                path = Path(tmp) / 'result.html'
                with self.assertRaises(VerificationError):
                    download(COMMIT, digest(manifest), DATASET, END, path,
                             base_url=url, allow_loopback_http=True)
                self.assertFalse(path.exists())

    def test_wrong_dataset_and_window_fail_closed(self):
        html, manifest = fixture()
        with tempfile.TemporaryDirectory() as tmp, serve(html, manifest) as url:
            path = Path(tmp) / 'result.html'
            for dataset, end in [('run-20261114-032300-a32c03ef7daa', END),
                                 (DATASET, '2026-11-09')]:
                with self.subTest(dataset=dataset, end=end), self.assertRaises(VerificationError):
                    download(COMMIT, digest(manifest), dataset, end, path,
                             base_url=url, allow_loopback_http=True)
                self.assertFalse(path.exists())

    def test_custom_origin_requires_numeric_loopback_test_mode(self):
        html, manifest = fixture()
        with tempfile.TemporaryDirectory() as tmp, serve(html, manifest) as url:
            path = Path(tmp) / 'result.html'
            with self.assertRaisesRegex(VerificationError, 'only in explicit loopback tests'):
                download(COMMIT, digest(manifest), DATASET, END, path, base_url=url)
            with self.assertRaisesRegex(VerificationError, 'HTTPS required'):
                download(COMMIT, digest(manifest), DATASET, END, path,
                         base_url=url.replace('127.0.0.1', 'localhost'),
                         allow_loopback_http=True)
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
