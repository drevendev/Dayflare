"""Pin the accepted, dated offline HTML; not a live Pages release."""
from hashlib import sha256
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = "downloads/dayflare-30-2026-11-21.html"
HTML_PIN = "91b9f7921dfb371747f19327d7f71a00e0f19900a3422310f1c68416abeee8f4"


class DatedDownloadTests(unittest.TestCase):
    def test_accepted_historical_bytes(self):
        # This immutable archive pins the independently reviewed historical
        # output, not all future renderer versions.
        raw = (ROOT / RELATIVE).read_bytes()
        self.assertEqual(len(raw), 464272)
        self.assertEqual(sha256(raw).hexdigest(), HTML_PIN)

    def test_readme_prioritizes_dated_download(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        first = readme.split("## Explore the newest retained observations", 1)[0]
        url = "https://raw.githubusercontent.com/drevendev/Dayflare/master/" + RELATIVE
        self.assertIn(url, first)
        self.assertIn(HTML_PIN, first)
        self.assertIn("no sign-in or build required", first)
        self.assertIn("not a new public release or live site", first)
        self.assertLess(first.index(url), first.index("/artifacts/14979370888"))


if __name__ == "__main__":
    unittest.main()
