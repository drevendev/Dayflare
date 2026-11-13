"""Bounded real-loopback HTTP checks for exact archived M1 Pages bytes."""
import contextlib
import hashlib
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest

from tools.verify_m1_public_release import VerificationError, check_manifest, verify, verify_archive


DATASET = 'run-20261107-022343-a32c03ef7daa'
END = '2026-11-04'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def release(html=b'<!doctype html><title>Dayflare M1 test fixture</title>'):
    manifest = {
        'candidate_sha256': 'a' * 64,
        'daily_observations': 700,
        'dataset_id': DATASET,
        'html_sha256': digest(html),
        'method_version': 'v0-empirical-35d',
        'observation_end': END,
        'retrieved_at': '2026-11-07T02:23:43Z',
        'schema_version': 'dayflare.m1.static-snapshot.v1',
        'series': 20,
        'source_receipt_sha256': 'b' * 64,
        'source_seed_sha256': 'c' * 64,
        'status': 'DATED_ARCHIVE_NOT_LIVE',
    }
    return html, manifest


@contextlib.contextmanager
def served(html, manifest, *, root_override=None, changed_type=None, redirect=False, missing=False,
           archive=None, archive_root_override=None, archive_redirect=False,
           archive_dir_override=None):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / 'Dayflare' / 'm1'
        root.mkdir(parents=True)
        (root / 'index.html').write_bytes(html)
        if archive is not None:
            archived_html, archived_manifest = archive
            archived_root = root / 'archives' / (archive_dir_override or archived_manifest['candidate_sha256'])
            archived_root.mkdir(parents=True)
            (archived_root / 'index.html').write_bytes(archived_html)
            (archived_root / 'release-manifest.json').write_bytes(
                json.dumps(archived_manifest, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        if not missing:
            (root / 'release-manifest.json').write_bytes(
                json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode() + b'\n')

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=folder, **kwargs)

            def log_message(self, *args):
                pass

            def guess_type(self, path):
                if changed_type and path.endswith('index.html'):
                    return 'application/json'
                return super().guess_type(path)

            def do_GET(self):
                if archive_redirect and '/archives/' in self.path and self.path.endswith('/'):
                    self.send_response(302)
                    self.send_header('Location', '/Dayflare/m1/')
                    self.end_headers()
                    return
                if (archive_root_override is not None and '/archives/' in self.path
                        and self.path.endswith('/')):
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(archive_root_override)))
                    self.end_headers()
                    self.wfile.write(archive_root_override)
                    return
                if redirect and self.path == '/Dayflare/m1/':
                    self.send_response(302)
                    self.send_header('Location', '/Dayflare/m1/index.html')
                    self.end_headers()
                    return
                if self.path == '/Dayflare/m1/' and root_override is not None:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(root_override)))
                    self.end_headers()
                    self.wfile.write(root_override)
                    return
                return super().do_GET()

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            raw = (root / 'release-manifest.json').read_bytes() if not missing else b''
            yield f'http://127.0.0.1:{server.server_port}/Dayflare/m1/', digest(raw)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


class M1PublicReleaseTests(unittest.TestCase):
    def check(self, html, manifest, **kwargs):
        with served(html, manifest, **kwargs) as (url, pin):
            return verify(url, pin, DATASET, END, allow_loopback_http=True)

    def test_verified_exact_bytes_report_only_http_status(self):
        html, manifest = release()
        found = self.check(html, manifest)
        self.assertEqual(found['status'], 'HTTP_BYTES_VERIFIED_NOT_BROWSER_VERIFIED')
        self.assertEqual(found['transport'], 'local-loopback-http')
        self.assertEqual(found['daily_observations'], 700)
        self.assertEqual(found['observation_end'], END)

    def test_independent_manifest_pin_rejects_wrong_release(self):
        html, manifest = release()
        with served(html, manifest) as (url, pin):
            with self.assertRaisesRegex(VerificationError, 'independent release pin'):
                verify(url, '0' * 64, DATASET, END, allow_loopback_http=True)

    def test_changed_html_even_with_same_served_manifest_is_rejected(self):
        html, manifest = release()
        with self.assertRaisesRegex(VerificationError, 'HTML differs'):
            self.check(html + b'<!-- unreviewed -->', manifest)

    def test_visitor_route_must_not_serve_stale_root(self):
        html, manifest = release()
        with self.assertRaisesRegex(VerificationError, 'Visitor M1 root differs'):
            self.check(html, manifest, root_override=b'<h1>Stale</h1>')

    def test_visitor_redirect_is_not_http_byte_proof(self):
        html, manifest = release()
        with self.assertRaisesRegex(VerificationError, 'Redirect not accepted'):
            self.check(html, manifest, redirect=True)

    def test_missing_or_wrong_content_type_fails(self):
        html, manifest = release()
        with self.assertRaisesRegex(VerificationError, 'HTTP request failed'):
            self.check(html, manifest, missing=True)
        with self.assertRaisesRegex(VerificationError, 'Incorrect Content-Type'):
            self.check(html, manifest, changed_type=True)

    def test_scope_and_identity_require_exact_explicit_pins(self):
        html, manifest = release()
        with served(html, manifest) as (url, pin):
            with self.assertRaisesRegex(VerificationError, 'exact Dayflare'):
                verify(url.replace('/Dayflare/m1/', '/other/m1/'), pin, DATASET, END,
                       allow_loopback_http=True)
            with self.assertRaisesRegex(VerificationError, 'dataset, method'):
                verify(url, pin, DATASET.replace('-a32c', '-b32c'), END,
                       allow_loopback_http=True)
            with self.assertRaisesRegex(VerificationError, 'HTTPS required'):
                verify(url.replace('127.0.0.1', 'localhost'), pin, DATASET, END,
                       allow_loopback_http=True)

    def test_wrong_method_coverage_and_status_are_not_accepted(self):
        html, manifest = release()
        for field, value in [('method_version', 'experimental'), ('series', 19),
                             ('daily_observations', 699), ('status', 'LIVE')]:
            with self.subTest(field=field):
                altered = dict(manifest, **{field: value})
                with self.assertRaisesRegex(VerificationError, 'dataset, method'):
                    self.check(html, altered)

    def test_malformed_or_incomplete_times_rejected(self):
        html, manifest = release()
        for bad in ('2026-11-04T02:23:43Z', '2026-11-05T02:23:43+00:00',
                    '2026-11-35T02:23:43Z'):
            with self.subTest(retrieved_at=bad):
                altered = dict(manifest, retrieved_at=bad)
                with self.assertRaises(VerificationError):
                    self.check(html, altered)

    def test_first_second_of_next_utc_day_is_valid(self):
        _, manifest = release()
        manifest['retrieved_at'] = '2026-11-05T00:00:00Z'
        checked = check_manifest(
            json.dumps(manifest).encode(),
            expected_dataset_id=DATASET, expected_observation_end=END)
        self.assertEqual(checked['retrieved_at'], '2026-11-05T00:00:00Z')

    def test_maximum_year_boundary_fails_closed_without_overflow(self):
        _, manifest = release()
        latest = dict(manifest, observation_end='9999-12-31',
                      retrieved_at='9999-12-31T23:59:59Z')
        # A pinned, otherwise well-formed manifest cannot claim a complete
        # day that has no representable following UTC retrieval date.
        with self.assertRaisesRegex(VerificationError, 'predates complete observation window'):
            check_manifest(
                json.dumps(latest).encode(),
                expected_dataset_id=DATASET, expected_observation_end='9999-12-31')

        prior = dict(manifest, observation_end='9999-12-30',
                     retrieved_at='9999-12-31T00:00:00Z')
        checked = check_manifest(
            json.dumps(prior).encode(),
            expected_dataset_id=DATASET, expected_observation_end='9999-12-30')
        self.assertEqual(checked['observation_end'], '9999-12-30')

    def test_invalid_manifest_fields_rejected(self):
        html, manifest = release()
        with self.assertRaisesRegex(VerificationError, 'Unexpected M1 release'):
            check_manifest(json.dumps(dict(manifest, injected='true')).encode(),
                           expected_dataset_id=DATASET, expected_observation_end=END)
        with self.assertRaisesRegex(VerificationError, 'Invalid html_sha256'):
            check_manifest(json.dumps(dict(manifest, html_sha256='zzz')).encode(),
                           expected_dataset_id=DATASET, expected_observation_end=END)


    def test_old_share_target_survives_new_current_release_with_independent_pins(self):
        old_html, old_manifest = release(b'<h1>Prior accepted M1 history</h1>')
        new_html = b'<h1>New accepted M1 history</h1>'
        new_dataset = 'run-20261108-022343-a32c03ef7daa'
        new_end = '2026-11-05'
        new_manifest = dict(old_manifest, dataset_id=new_dataset,
                            observation_end=new_end, retrieved_at='2026-11-08T02:23:43Z',
                            html_sha256=digest(new_html), candidate_sha256='d' * 64)
        old_pin = digest(json.dumps(old_manifest, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        with served(new_html, new_manifest, archive=(old_html, old_manifest)) as (url, new_pin):
            current = verify(url, new_pin, new_dataset, new_end,
                             allow_loopback_http=True)
            archived = verify_archive(url, old_pin, DATASET, END, 'a' * 64,
                                      allow_loopback_http=True)
            self.assertEqual(current['html_sha256'], digest(new_html))
            self.assertEqual(archived['html_sha256'], digest(old_html))
            self.assertEqual(archived['status'],
                             'HTTP_ARCHIVE_BYTES_VERIFIED_NOT_BROWSER_VERIFIED')
            self.assertEqual(archived['url'], url + 'archives/' + 'a' * 64 + '/')
            self.assertNotEqual(archived['url'], current['url'])
            with self.assertRaisesRegex(VerificationError, 'independent release pin'):
                verify_archive(url, new_pin, DATASET, END, 'a' * 64,
                               allow_loopback_http=True)

    def test_archived_share_fails_closed_on_missing_corrupt_or_wrong_identity(self):
        old_html, old_manifest = release(b'<h1>Accepted archived M1</h1>')
        pin = digest(json.dumps(old_manifest, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        with served(*release(), archive=(old_html + b'changed', old_manifest)) as (url, _):
            with self.assertRaisesRegex(VerificationError, 'HTML differs'):
                verify_archive(url, pin, DATASET, END, 'a' * 64,
                               allow_loopback_http=True)
        with served(*release(), archive=(old_html, old_manifest)) as (url, _):
            with self.assertRaisesRegex(VerificationError, 'request failed'):
                verify_archive(url, pin, DATASET, END, 'f' * 64,
                               allow_loopback_http=True)
            for bad in ('A' * 64, '../bad', ''):
                with self.subTest(candidate=bad), self.assertRaisesRegex(
                    VerificationError, 'archive candidate'):
                    verify_archive(url, pin, DATASET, END, bad,
                                   allow_loopback_http=True)
        wrong_dir_manifest = dict(old_manifest, candidate_sha256='f' * 64)
        wrong_dir_pin = digest(json.dumps(wrong_dir_manifest, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        with served(*release(), archive=(old_html, wrong_dir_manifest),
                    archive_dir_override='a' * 64) as (url, _):
            with self.assertRaisesRegex(VerificationError, 'Archive directory'):
                verify_archive(url, wrong_dir_pin, DATASET, END, 'a' * 64,
                               allow_loopback_http=True)
        with served(*release(), archive=(old_html, wrong_dir_manifest)) as (url, _):
            # An independently pinned different historical digest cannot be
            # substituted even when the directory and served manifest agree.
            with self.assertRaisesRegex(VerificationError, 'independent release pin'):
                verify_archive(url, pin, DATASET, END, 'f' * 64,
                               allow_loopback_http=True)

    def test_archived_visitor_route_rejects_alias_substitution_and_redirect(self):
        old_html, old_manifest = release(b'<h1>Prior accepted page</h1>')
        pin = digest(json.dumps(old_manifest, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        for kwargs, expected in [
            ({'archive_root_override': b'<h1>Current instead</h1>'}, 'Visitor M1 root differs'),
            ({'archive_redirect': True}, 'Redirect not accepted'),
        ]:
            with self.subTest(expected=expected):
                with served(*release(), archive=(old_html, old_manifest), **kwargs) as (url, _):
                    with self.assertRaisesRegex(VerificationError, expected):
                        verify_archive(url, pin, DATASET, END, 'a' * 64,
                                       allow_loopback_http=True)


if __name__ == '__main__':
    unittest.main()
