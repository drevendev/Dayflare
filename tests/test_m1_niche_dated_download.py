"""Pin the exact independently browser-accepted niche offline preview."""
from hashlib import sha256
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = "downloads/dayflare-19-2026-11-23.html"
HTML_PIN = "b7b44b1757933a9b2d788fcddd63980cb64cfcd31f1996c8eb08eded0daf6d64"


class NicheDatedDownloadTests(unittest.TestCase):
    def test_exact_historical_bytes(self):
        raw = (ROOT / RELATIVE).read_bytes()
        self.assertEqual(len(raw), 328483)
        self.assertEqual(sha256(raw).hexdigest(), HTML_PIN)

    def test_readme_distinguishes_dated_cohorts(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        section = readme.split("## Explore a separate niche atlas", 1)[1]
        section = section.split("## Explore the newest retained observations", 1)[0]
        self.assertIn("https://raw.githubusercontent.com/drevendev/Dayflare/master/" + RELATIVE, section)
        self.assertIn(HTML_PIN, section)
        self.assertIn("665 exact daily request counts", section)
        self.assertIn("does not replace or combine", section)
        self.assertIn("not a live site", section)
        self.assertIn("downloads/dayflare-30-2026-11-21.html", readme)


if __name__ == "__main__":
    unittest.main()
