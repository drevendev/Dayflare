"""Exercise the self-contained Pages artifact via real localhost HTTP requests.

This is a server/API test, not proof of actual GitHub Pages deployment.
"""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

from tools.build_static_release import build_zip, bundle_files


class ReleaseHTTPTests(unittest.TestCase):
    def test_project_subpath_resolves_all_assets_inside_the_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'Dayflare'
            project.mkdir()
            payload=build_zip(bundle_files())
            with ZipFile(__import__('io').BytesIO(payload)) as z:
                z.extractall(project)
            class Quiet(SimpleHTTPRequestHandler):
                def log_message(self, *_):
                    pass
            server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=tmp))
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                base=f'http://127.0.0.1:{server.server_address[1]}/Dayflare/'
                for url in ['','index.html','evidence.html','identities-m1-20261024.html','identities-m1-20261024.json','m1-cross-subject-20261025.html','m1-cross-subject-20261025.json','m1-curated-20261023.html','m1-curated-20261023.json','app.js','styles.css','evidence/d02-20261018/source.zip','evidence/d02-20261018/provenance.json','evidence/d02-20261018/README.md','release-manifest.json']:
                    with urlopen(base+url,timeout=5) as response:
                        data=response.read()
                        self.assertEqual(response.status,200)
                        self.assertEqual(data, (project/(url or 'index.html')).read_bytes())
                with self.assertRaises(HTTPError) as c:
                    urlopen(base+'evidence/d02-20261018/missing.zip',timeout=5)
                self.assertEqual(c.exception.code,404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__=='__main__':
    unittest.main()
