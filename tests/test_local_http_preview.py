"""Exercise actual localhost HTTP bytes/paths for the candidate static preview.

This is a source/transport smoke, NOT Chromium HTTP navigation or GitHub Pages
verification. It never writes to the repository or requests an external origin.
"""
from __future__ import annotations

from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import urlopen
from zipfile import ZipFile
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
ZIP_SHA = "3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class PreviewHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT))
        )
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/site/index.html"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def fetch(self, path):
        with urlopen(urljoin(self.url, path), timeout=3) as response:
            self.assertEqual(response.status, 200)
            return response.headers, response.read()

    def test_site_html_and_assets_over_actual_http(self):
        headers, html = self.fetch("index.html")
        self.assertIn("text/html", headers.get_content_type())
        self.assertIn(b"<title>Dayflare", html)
        self.assertIn(b'href="styles.css"', html)
        self.assertIn(b'src="app.js"', html)
        headers, css = self.fetch("styles.css")
        self.assertEqual(headers.get_content_type(), "text/css")
        self.assertIn(b".card", css)
        headers, script = self.fetch("app.js")
        self.assertIn(headers.get_content_type(), ("text/javascript", "application/javascript"))
        self.assertIn(b"../evidence/d02-20261018/source.zip", script)

    def test_evidence_relative_url_serves_exact_retained_archive(self):
        headers, archive = self.fetch("../evidence/d02-20261018/source.zip")
        self.assertEqual(headers.get_content_type(), "application/zip")
        self.assertEqual(hashlib.sha256(archive).hexdigest(), ZIP_SHA)
        with ZipFile(BytesIO(archive)) as f:
            self.assertEqual(set(f.namelist()), {"sample.json", "receipt.json"})

    def test_missing_evidence_is_http_404_not_zero_data(self):
        with self.assertRaises(HTTPError) as context:
            urlopen(urljoin(self.url, "../evidence/d02-20261018/absent.zip"), timeout=3)
        self.assertEqual(context.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
