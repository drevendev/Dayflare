"""Serve the exact candidate over real localhost HTTP; exercise verifier failure controls."""
import contextlib
import http.server
from pathlib import Path
import tempfile
import threading
import unittest

from tools.build_static_release import bundle_files, digest
from tools.verify_public_release import VerificationError, verify, origin


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def served(files, *, modified_type=None, redirected=False, root_override=None, root_redirected=False):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / 'Dayflare'
        root.mkdir()
        for name, data in files.items():
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

        class Custom(QuietHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=temp, **kwargs)
            def guess_type(self, path):
                if modified_type and path.endswith(modified_type[0]):
                    return modified_type[1]
                return super().guess_type(path)
            def do_GET(self):
                if self.path == '/Dayflare/' and root_override is not None:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(root_override)))
                    self.end_headers()
                    self.wfile.write(root_override)
                    return
                if self.path == '/Dayflare/' and root_redirected:
                    self.send_response(302)
                    self.send_header('Location', '/Dayflare/index.html')
                    self.end_headers()
                    return
                if redirected and self.path.endswith('index.html'):
                    self.send_response(302)
                    self.send_header('Location', 'https://untrusted.example.net/redirect')
                    self.end_headers()
                else:
                    return super().do_GET()

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Custom)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}/Dayflare/'
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


class PublicReleaseVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = bundle_files()
        cls.pin = digest(cls.files['release-manifest.json'])

    def check_failure(self, files, message, **kwargs):
        with served(files, **kwargs) as url:
            with self.assertRaisesRegex(VerificationError, message):
                verify(url, self.pin, allow_loopback_http=True)

    def test_exact_candidate_and_subdirectory(self):
        with served(self.files) as url:
            outcome = verify(url, self.pin, allow_loopback_http=True)
        self.assertEqual(outcome.verified_assets, 9)
        self.assertEqual(outcome.dataset_id, 'd02-20261018-084126')
        self.assertEqual(outcome.status, 'HTTP_BYTES_VERIFIED_NOT_BROWSER_VERIFIED')
        self.assertEqual(outcome.transport, 'local-loopback-http')

    def test_visitor_root_must_match_explicit_index(self):
        # A host can serve the exact approved /index.html while the actual
        # user-facing project root points to stale, unreviewed HTML.
        with served(self.files, root_override=b'<!doctype html><title>Stale landing</title>') as url:
            with self.assertRaisesRegex(VerificationError, 'Visitor root HTML differs'):
                verify(url, self.pin, allow_loopback_http=True)

    def test_visitor_root_redirect_is_not_proof_of_served_bytes(self):
        with served(self.files, root_redirected=True) as url:
            with self.assertRaisesRegex(VerificationError, 'Redirect not accepted'):
                verify(url, self.pin, allow_loopback_http=True)

    def test_wrong_or_stale_manifest_pin(self):
        with served(self.files) as url:
            with self.assertRaisesRegex(VerificationError, 'Served manifest differs'):
                verify(url, '0' * 64, allow_loopback_http=True)

    def test_tampered_javascript_does_not_pass(self):
        altered = dict(self.files)
        altered['app.js'] += b'// changed after build\n'
        self.check_failure(altered, 'app.js: served bytes differ')

    def test_identity_source_tampering_is_not_a_valid_release(self):
        altered=dict(self.files)
        altered['identities-m1-20261024.json']+=b' '
        self.check_failure(altered,'identities-m1-20261024.json: served bytes differ')
        altered=dict(self.files)
        del altered['identities-m1-20261024.html']
        self.check_failure(altered,'identities-m1-20261024.html: HTTP request failed')

    def test_missing_history_is_not_zero_or_success(self):
        altered = dict(self.files)
        del altered['evidence/d02-20261018/source.zip']
        self.check_failure(altered, 'source.zip: HTTP request failed')

    def test_wrong_content_type(self):
        self.check_failure(self.files, 'Incorrect Content-Type',
                           modified_type=('.js','text/html'))

    def test_external_redirect_not_followed(self):
        self.check_failure(self.files, 'Redirect not accepted', redirected=True)

    def test_public_http_and_ambiguous_roots_rejected(self):
        with self.assertRaisesRegex(VerificationError, 'HTTPS required'):
            origin('http://example.org/Dayflare/', allow_loopback_http=True)
        with self.assertRaisesRegex(VerificationError, 'HTTPS required'):
            origin('http://localhost/Dayflare/', allow_loopback_http=True)
        with self.assertRaisesRegex(VerificationError, 'trailing-slash'):
            origin('https://example.org/Dayflare/../other/')
        with self.assertRaisesRegex(VerificationError, 'credentials'):
            origin('https://alice:secret@example.org/Dayflare/')


if __name__ == '__main__':
    unittest.main()
