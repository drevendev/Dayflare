"""Offline contract: observed IDs link to a separate versioned title history only."""
from collections import Counter
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
        self.assertEqual(len(links), 11)
        destinations = Counter()
        for url in links:
            link = urlsplit(url.replace('&amp;', '&'))
            self.assertEqual(link.path, 'index.html')
            qs = parse_qs(link.query)
            self.assertEqual([qs[k] for k in ('ds','m','w')],
                             [['d02-20261018-084126'],['v0-empirical-35d'],['20260811-20260914']])
            self.assertEqual(len(qs), 6 if 'c' in qs else 5)
            self.assertEqual(link.fragment, 'comparison' if 'c' in qs else 'detail')
            if 'c' in qs:
                self.assertIn((qs['s'][0], qs['ed'][0], qs['c'][0]),
                              {('2','en.wikipedia.org','5'), ('0','en.wikipedia.org','3'),
                               ('1','en.wikipedia.org','4')})
            else:
                self.assertIn((qs['s'][0],qs['ed'][0]),
                              {('0','en.wikipedia.org'),('1','en.wikipedia.org'),
                               ('2','en.wikipedia.org'),('3','ru.wikipedia.org'),
                               ('4','ru.wikipedia.org'),('5','ru.wikipedia.org')})
            destinations[(qs['s'][0], qs['ed'][0], qs.get('c', [None])[0], link.fragment)] += 1
        self.assertEqual(destinations, Counter({
            ('0','en.wikipedia.org',None,'detail'):1,
            ('3','ru.wikipedia.org',None,'detail'):1,
            ('1','en.wikipedia.org',None,'detail'):1,
            ('4','ru.wikipedia.org',None,'detail'):1,
            ('2','en.wikipedia.org',None,'detail'):2,
            ('5','ru.wikipedia.org',None,'detail'):2,
            ('0','en.wikipedia.org','3','comparison'):1,
            ('1','en.wikipedia.org','4','comparison'):1,
            ('2','en.wikipedia.org','5','comparison'):1,
        }))
        self.assertEqual(headings, [
            'Artificial intelligence · English', 'The Master and Margarita · English',
            'Chess · English', 'Искусственный интеллект · Russian',
            'Мастер и Маргарита · Russian', 'Шахматы · Russian'])
        extra = atlas.split('id="measured-more"', 1)[1].split('</section>', 1)[0]
        for amount in ('125,894', '81,756', '+44,138', '14,595', '8,645', '+5,950',
                       '9,662', '9,993', '−331', '5,222', '5,222.5', '−0.5'):
            self.assertIn(amount, extra)
        self.assertIn('no corresponding observed numeric page IDs in this 20-ID panel', extra)
        self.assertNotIn('id="en-', extra)
        self.assertNotIn('id="ru-', extra)
        for card, pos in [('en-5134','2'),('ru-10646','5')]:
            snippet = atlas.split(f'id="{card}"',1)[1].split('</article>',1)[0]
            self.assertIn(f'&amp;s={pos}&amp;', snippet)
            self.assertIn('Not verified as this page ID', snippet)
        self.assertIn('not verified</strong>', atlas)
        self.assertIn('Without JavaScript, the historical page still offers exact daily tables', atlas)
        self.assertIn('<noscript>', history)

if __name__ == '__main__':
    unittest.main()
