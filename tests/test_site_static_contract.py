"""Standard-library structural checks for the historical read-only web atlas."""
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import re
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'

class Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=set()
        self.duplicates=set()
        self.tags=[]
        self.controls=[]
        self.label_count=0
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        self.tags.append((tag,d))
        if 'id' in d:
            if d['id'] in self.ids:self.duplicates.add(d['id'])
            self.ids.add(d['id'])
        if tag=='label':self.label_count+=1
        if tag in ('button','input','select'):self.controls.append((tag,d))

class StaticContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(SITE/'index.html').read_text(encoding='utf-8')
        cls.js=(SITE/'app.js').read_text(encoding='utf-8')
        cls.css=(SITE/'styles.css').read_text(encoding='utf-8')
        cls.doc=Scan();cls.doc.feed(cls.html)

    def test_single_semantic_landmarks_and_all_javascript_targets(self):
        self.assertFalse(self.doc.duplicates)
        for tag in ('main','header','footer','noscript'):
            self.assertTrue(any(t==tag for t,a in self.doc.tags),tag)
        for ident in ('discover','cards','status','empty','clear','retry','edition','subject','query','detail','history','spark','comparison','compare-select','copy','share-state'):
            self.assertIn(ident,self.doc.ids)
        used=set(re.findall(r"\$\('([a-z][a-z0-9-]*)'\)",self.js))
        self.assertFalse(used-self.doc.ids,used-self.doc.ids)

    def test_accessibility_and_mobile(self):
        self.assertIn('href="#discover"',self.html)
        self.assertIn('aria-live="polite"',self.html)
        self.assertIn('prefers-reduced-motion:reduce',self.css)
        self.assertIn('@media(max-width:580px)',self.css)
        self.assertIn(':focus-visible',self.css)
        self.assertIn('role="img"',self.html)
        self.assertIn('<caption>',self.html)
        self.assertGreaterEqual(self.doc.label_count,4)
        self.assertIn('<noscript>',self.html)

    def test_external_fetch_and_libraries_are_not_added(self):
        self.assertIn("const ZIP_URL = '../evidence/d02-20261018/source.zip';",self.js)
        self.assertNotIn('http://',self.js.replace('http://www.w3.org/2000/svg',''))
        self.assertNotIn('fetch("https://',self.js)
        self.assertNotIn("document.cookie",self.js)
        self.assertNotIn('localStorage',self.js)
        self.assertNotIn('<iframe',self.html)
        self.assertEqual([d.get('src') for t,d in self.doc.tags if t=='script'],['app.js'])

    def test_expected_real_capsule_has_exact_archive_and_members(self):
        p=ROOT/'evidence/d02-20261018/source.zip'
        raw=p.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631')
        with zipfile.ZipFile(p) as z:
            self.assertEqual(z.namelist(),['sample.json','receipt.json'])
            sample=json.loads(z.read('sample.json'))
            receipt=json.loads(z.read('receipt.json'))
        self.assertTrue(receipt['success'])
        self.assertEqual(receipt['method_version'],'v0-empirical-35d')
        self.assertEqual(len(sample),6)
        self.assertEqual(sum(len(s['items']) for s in sample),210)

    def test_share_is_version_bound_and_no_title_stitching(self):
        for token in ("u.searchParams.set('ds',DATASET)","u.searchParams.set('m',METHOD)","u.searchParams.set('s',String(selected))","u.searchParams.set('c',String(compared))"):
            self.assertIn(token,self.js)
        self.assertIn("u.searchParams.set('ed',series[selected].edition)",self.js)
        self.assertIn("u.searchParams.set('w','20260811-20260914')",self.js)
        self.assertIn('no cross-edition identity equivalence is assumed',self.js.lower())
        self.assertIn('No measured data is displayed.',self.js)

if __name__=='__main__': unittest.main()
