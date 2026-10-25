"""Offline contract: observed IDs link to a separate versioned title history only."""
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import unittest

ROOT = Path(__file__).resolve().parents[1]

class HistoryCompanionTests(unittest.TestCase):
    def test_exact_historical_title_links_and_no_identity_stitching(self):
        atlas = (ROOT / "site/identities-m1-20261024.html").read_text(encoding="utf-8")
        history = (ROOT / "site/index.html").read_text(encoding="utf-8")
        app = (ROOT / "site/app.js").read_text(encoding="utf-8")
        self.assertEqual(atlas.count('<article class="card" id='), 20)
        self.assertEqual(atlas.count('id="measured-chess"'), 1)
        self.assertIn('id="measured-chess-title"', atlas)
        self.assertIn("const DATASET = 'd02-20261018-084126'", app)
        self.assertIn("const METHOD = 'v0-empirical-35d'", app)
        headings = re.findall(r'<summary><strong>([^<]+)</strong> <span>8–14 Sep:', history)
        self.assertEqual(len(headings), 6)
        self.assertEqual([headings[2], headings[5]], ['Chess · English', 'Шахматы · Russian'])
        links = re.findall(r'href="(index\.html\?ds=[^"]+)"', atlas)
        self.assertEqual(len(links), 5)
        for url in links:
            link = urlsplit(url.replace('&amp;', '&'))
            self.assertEqual(link.path, 'index.html')
            qs = parse_qs(link.query)
            self.assertEqual([qs[k] for k in ('ds','m','w')],
                             [['d02-20261018-084126'],['v0-empirical-35d'],['20260811-20260914']])
            self.assertEqual(len(qs), 6 if 'c' in qs else 5)
            self.assertEqual(link.fragment, 'comparison' if 'c' in qs else 'detail')
            if 'c' in qs:
                self.assertEqual([qs['s'],qs['ed'],qs['c']], [['2'],['en.wikipedia.org'],['5']])
            else:
                self.assertIn((qs['s'][0],qs['ed'][0]), {('2','en.wikipedia.org'),('5','ru.wikipedia.org')})
        self.assertEqual(sum('c=5' in url for url in links), 1)
        for card, pos in [('en-5134','2'),('ru-10646','5')]:
            snippet = atlas.split(f'id="{card}"',1)[1].split('</article>',1)[0]
            self.assertIn(f'&amp;s={pos}&amp;', snippet)
            self.assertIn('Not verified as this page ID', snippet)
        self.assertIn('not verified</strong>', atlas)
        self.assertIn('Without JavaScript, the historical page still offers exact daily tables', atlas)
        self.assertIn('<noscript>', history)

if __name__ == '__main__':
    unittest.main()
