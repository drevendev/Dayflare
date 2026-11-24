"""A newer Git-retained observation must not replace the accepted homepage release."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.append(dict(attrs).get("href"))


class RetainedPreviewPathTests(unittest.TestCase):
    def test_secondary_source_path_is_dated_and_works_without_js(self):
        page = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(page.count('id="retained-preview"'), 1)
        start = page.index('<p class="retained-preview" id="retained-preview">')
        note = page[start:page.index("</p>", start) + 4]
        self.assertLess(start, page.index('class="m1-subject-shortcuts"'))
        for text in ("15 Oct–18 Nov 2026", "20 selected title histories, 700 daily requests",
                     "retrieved 21 Nov", "not an accepted release",
                     "does not replace the independently accepted atlas above", "Neither link is a live Pages deployment"):
            self.assertIn(text, note)
        reader = _Links()
        reader.feed(note)
        self.assertEqual(reader.hrefs, [
            "https://github.com/drevendev/Dayflare/blob/master/README.md#explore-the-newest-retained-observations-18-nov-2026-local-only",
            "https://github.com/drevendev/Dayflare/tree/master/evidence/m1-20-20261121",
        ])
        self.assertIn('data-observed-end="2026-11-11"', page)
        self.assertIn("4851d6a7e106f02261b6e7a58226295ac94a664d/m1/index.html", page)


if __name__ == "__main__":
    unittest.main()
