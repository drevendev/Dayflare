"""Regression tests: Pages static-root layout and last-good candidate safety."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from tools.build_static_release import ROOT, REQUIRED, DOC_GIT_BLOBS, HISTORY_TITLE_LINKS, build_zip, bundle_files, create_release, git_blob_sha, verify_release_links


class StaticReleaseTests(unittest.TestCase):
    def test_root_has_all_runtime_assets_with_no_parent_data_dependency(self):
        files=bundle_files()
        self.assertEqual(set(files), REQUIRED)
        js=files['app.js'].decode()
        self.assertIn("const ZIP_URL = './evidence/d02-20261018/source.zip';",js)
        self.assertNotIn("const ZIP_URL = '../evidence",js)
        self.assertIn('href="styles.css"',files['index.html'].decode())
        self.assertEqual(files['index.html'].count(b'href="evidence.html#provenance"'),2)
        self.assertIn(b'href="evidence.html"', files['index.html'])
        self.assertNotIn(b'../evidence/', files['index.html'])
        self.assertIn(b'11 August\xe2\x80\x9314 September 2026', files['evidence.html'])
        self.assertIn(b'href="evidence/d02-20261018/provenance.json"', files['evidence.html'])
        self.assertIn(b'href="index.html#discover"', files['evidence.html'])
        self.assertEqual(git_blob_sha(files['evidence/d02-20261018/README.md']), DOC_GIT_BLOBS['evidence/d02-20261018/README.md'])
        self.assertEqual(git_blob_sha(files['evidence/d02-20261018/provenance.json']), DOC_GIT_BLOBS['evidence/d02-20261018/provenance.json'])
        self.assertIn('src="app.js"',files['index.html'].decode())
        self.assertIn(b'src="curated-explorer.js"',files['m1-curated-20261023.html'])
        self.assertIn(b'function parseState(search)', files['curated-explorer.js'])
        self.assertEqual(files['.nojekyll'],b'')
        m=json.loads(files['release-manifest.json'])
        self.assertEqual(m['daily_observations'],210)
        self.assertEqual(m['auxiliary_cross_subject_dataset']['daily_observations'],140)
        self.assertEqual(m['auxiliary_curated_title_dataset']['daily_observations'],700)
        for name,expected in m['files_sha256'].items():
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(),expected)

    def test_zip_is_byte_for_byte_deterministic(self):
        files=bundle_files()
        a=build_zip(files)
        self.assertEqual(a,build_zip(copy.copy(files)))
        with tempfile.TemporaryDirectory() as t:
            archive=Path(t)/'candidate.zip'
            self.assertEqual(create_release(archive),a)
            self.assertEqual(create_release(archive,check=True),a)
            with ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()), REQUIRED)
                self.assertEqual(z.read('app.js'),files['app.js'])
                self.assertEqual(z.read('curated-explorer.js'),files['curated-explorer.js'])
                self.assertEqual(z.read('evidence/d02-20261018/source.zip'),files['evidence/d02-20261018/source.zip'])

    def test_corrupt_input_does_not_replace_existing_release(self):
        with tempfile.TemporaryDirectory() as t:
            home=Path(t)
            candidate=home/'last-good.zip'
            expected=create_release(candidate)
            source=home/'source'
            (source/'site').mkdir(parents=True)
            (source/'evidence/d02-20261018').mkdir(parents=True)
            for filename in ('index.html','styles.css','app.js','evidence.html','identities-m1-20261024.html','identities-m1-20261024.json','identity-explorer.js','curated-explorer.js','m1-cross-subject-20261025.json','m1-cross-subject-20261025.html','m1-curated-20261023.json','m1-curated-20261023.html'):
                (source/'site'/filename).write_bytes((ROOT/'site'/filename).read_bytes())
            for name in DOC_GIT_BLOBS:
                (source/name).write_bytes((ROOT/name).read_bytes())
            (source/'evidence/d02-20261018/source.zip').write_bytes(b'corrupt')
            with self.assertRaises(Exception):
                create_release(candidate,source=source)
            self.assertEqual(candidate.read_bytes(),expected)
            # A syntactically valid but changed JS input also cannot silently
            # overwrite an already accepted publication artifact.
            (source/'evidence/d02-20261018/source.zip').write_bytes((ROOT/'evidence/d02-20261018/source.zip').read_bytes())
            (source/'site/app.js').write_text((ROOT/'site/app.js').read_text()+'\n// source revision changed\n')
            with self.assertRaisesRegex(ValueError,'refusing to overwrite'):
                create_release(candidate,source=source)
            self.assertEqual(candidate.read_bytes(),expected)
            # Altering the cited source record, even without changing the ZIP,
            # is not a harmless documentation update: the candidate stays intact.
            source_doc=source/'evidence/d02-20261018/provenance.json'
            source_doc.write_bytes(source_doc.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'Unverified or changed evidence document'):
                create_release(candidate,source=source)
            self.assertEqual(candidate.read_bytes(),expected)

    def test_orphaned_links_and_parent_paths_are_build_errors(self):
        files=bundle_files()
        for broken in (b'href="../secrets.json"',b'href="missing.html"',b'href="evidence.html#unknown"'):
            changed=dict(files)
            changed['index.html']=files['index.html'].replace(b'href="evidence.html"',broken)
            with self.assertRaisesRegex(ValueError,'release URL|release fragment'):
                verify_release_links(changed)

    def test_exact_historical_deep_links_are_safe_but_malformed_queries_are_rejected(self):
        files = bundle_files()  # All nine unique reviewed links survive the normal Pages build.
        page = 'identities-m1-20261024.html'
        html = files[page]
        self.assertEqual(len(HISTORY_TITLE_LINKS), 9)
        for ref in HISTORY_TITLE_LINKS:
            self.assertIn(('href="' + ref.replace('&', '&amp;') + '"').encode(), html)
        self.assertEqual(sum(html.count(('href="' + value.replace('&', '&amp;') + '"').encode())
                             for value in HISTORY_TITLE_LINKS), 11)
        ref = next(r for r in HISTORY_TITLE_LINKS if '&s=2&ed=en.wikipedia.org#detail' in r)
        original = ('href="' + ref.replace('&', '&amp;') + '"').encode()
        for bad in [
            ref.replace('ds=d02-20261018-084126', 'ds=different'),
            ref.replace('m=v0-empirical-35d', 'm=v1'),
            ref.replace('&s=2', '&s=5').replace('&s=5', '&s=6'),
            ref.replace('index.html?', 'missing.html?'),
            ref.replace('#detail', '#unknown').replace('#comparison', '#unknown'),
            ref.replace('&ed=', '&ed=fr&ed='),
        ]:
            self.assertNotEqual(ref, bad)
            changed = dict(files)
            changed[page] = html.replace(original, ('href="' + bad.replace('&', '&amp;') + '"').encode())
            self.assertNotEqual(changed[page], html)
            with self.subTest(url=bad), self.assertRaisesRegex(ValueError, 'Unsupported release URL'):
                verify_release_links(changed)

    def test_source_document_hashes_reject_modification(self):
        files=bundle_files()
        provenance=json.loads(files['evidence/d02-20261018/provenance.json'])
        self.assertEqual(provenance['dataset_id'],'d02-20261018-084126')
        self.assertEqual(provenance['capsule']['sha256'],hashlib.sha256(files['evidence/d02-20261018/source.zip']).hexdigest())
        self.assertEqual(provenance['data_rights']['license'],'CC0-1.0')


if __name__ == '__main__':
    unittest.main()
