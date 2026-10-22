"""Synthetic M1 identity visitor preview contract tests; never hit Wikimedia."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.m1_build_preview import DEFAULT_FIXTURE, SITE, digest, expected_outputs


class PreviewTests(unittest.TestCase):
    def test_only_synthetic_and_reproducible(self):
        first = expected_outputs()
        self.assertEqual(first, expected_outputs())
        dataset = json.loads(first['panel.json'])
        self.assertEqual(dataset['selection']['evidence_kind'], 'synthetic')
        self.assertEqual(dataset['coverage']['provenance_verification'], 'synthetic_only')
        self.assertEqual(len(dataset['pages']), 6)
        self.assertEqual(dataset['coverage']['intended_count'], 7)
        manifest = json.loads(first['manifest.json'])
        self.assertTrue(manifest['not_a_public_attention_atlas'])
        self.assertEqual(manifest['content_sha256']['panel.json'], digest(first['panel.json']))
        self.assertIn(digest(first['panel.json']).encode(), first['index.html'])
        self.assertIn(b'SYNTHETIC DEMONSTRATION', first['index.html'])
        self.assertIn(b'id="coverage-breakdown"', first['index.html'])
        for name, data in first.items():
            self.assertEqual((SITE / name).read_bytes(), data)

    def test_rejects_retrieval_label_on_unverified_fixture(self):
        panel = json.loads(DEFAULT_FIXTURE.read_text())
        panel['selection']['evidence_kind'] = 'reported_retrieval'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'forged.json'
            path.write_text(json.dumps(panel))
            with self.assertRaises(ValueError):
                expected_outputs(path)

    def test_app_displays_unknown_and_uses_safe_dom(self):
        app = (SITE / 'app.js').read_text()
        self.assertIn('textContent', app)
        self.assertNotIn('.innerHTML', app)
        self.assertIn('incompatibleView()', app)
        self.assertIn('page_ref.page_id', app)
        self.assertIn('SHA-256', (SITE / 'index.template.html').read_text() + app)

    def test_no_unapproved_network_publish(self):
        src = (SITE / 'app.js').read_text()
        self.assertIn("fetch('panel.json'", src)
        self.assertNotIn('fetch(\'https', src)
        self.assertNotIn('window.location =', src)
        self.assertNotIn('navigator.sendBeacon', src)



class StaticAccessibilityTests(unittest.TestCase):
    def test_exact_references_and_unique_ids(self):
        from lxml import html
        import re
        doc = html.fromstring((SITE / 'index.html').read_text(encoding='utf-8'))
        ids = [node.get('id') for node in doc.xpath('//*[@id]')]
        self.assertEqual(len(ids), len(set(ids)))
        idset = set(ids)
        for node in doc.xpath('//*[@for]'):
            self.assertIn(node.get('for'), idset)
        for node in doc.xpath('//*[@aria-labelledby]'):
            for identifier in node.get('aria-labelledby').split():
                self.assertIn(identifier, idset)
        for node in doc.xpath('//*[@aria-describedby]'):
            for identifier in node.get('aria-describedby').split():
                self.assertIn(identifier, idset)
        for node in doc.xpath('//a[@href]'):
            href = node.get('href')
            if href.startswith('#'):
                self.assertIn(href[1:], idset)
        script = (SITE / 'app.js').read_text()
        used = set(re.findall(r"\$\('([a-z-]+)'\)", script))
        self.assertFalse(used - idset, f'unresolved DOM ID references: {used-idset}')
        self.assertEqual(doc.xpath('string(//html/@lang)'), 'en')
        self.assertTrue(doc.xpath('//*[@class="skip"]'))
        self.assertTrue(doc.xpath('//*[@id="status"][@aria-live="polite"]'))
        self.assertFalse(doc.xpath('//script[@src and contains(@src, "http")]'))
        self.assertFalse(doc.xpath('//link[@href and contains(@href, "http")]'))

    def test_incompatible_share_has_nearby_keyboard_recovery(self):
        from lxml import html
        doc = html.fromstring((SITE / 'index.html').read_text(encoding='utf-8'))
        catalog = doc.xpath('//*[@id="catalog"]')[0]
        children = list(catalog)
        recovery = doc.xpath('//*[@id="compat"]')[0]
        filters = catalog.xpath('.//*[@class="filters"]')[0]
        results = catalog.xpath('.//*[@class="workspace-grid"]')[0]
        self.assertIs(recovery.getparent(), catalog,
                      'Recovery belongs to discovery, not below share and coverage')
        self.assertLess(children.index(recovery), children.index(filters))
        self.assertLess(children.index(recovery), children.index(results))
        self.assertEqual(recovery.get('role'), 'alert')
        self.assertEqual(recovery.xpath('.//button[@id="reset"][@type="button"]')[0].text,
                         'Return to this fixture')

    def test_css_mobile_keyboard_reduced_motion(self):
        import tinycss2
        css=(SITE / 'styles.css').read_text()
        result=tinycss2.parse_stylesheet(css,skip_whitespace=True,skip_comments=True)
        errors=[x for x in result if x.type=='error']
        self.assertFalse(errors, errors)
        self.assertIn('max-width:420px',css)
        self.assertIn('max-width:750px',css)
        self.assertIn('prefers-reduced-motion:reduce',css)
        self.assertIn('focus-visible',css)
        self.assertIn('min-height:45px',css)

if __name__ == '__main__':
    unittest.main()
