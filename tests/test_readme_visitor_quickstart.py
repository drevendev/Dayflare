"""Keep the public README's three dated downloads immediately discoverable."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RAW = "https://raw.githubusercontent.com/drevendev/Dayflare/master/"
FILES = (
    "downloads/dayflare-30-2026-11-21.html",
    "downloads/dayflare-19-2026-11-23.html",
    "downloads/dayflare-19-2026-11-23-weekly-signals.csv",
)


class VisitorQuickstartTests(unittest.TestCase):
    def test_dated_downloads_precede_reproduction_instructions(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        heading = "## Start here — choose a dated offline atlas"
        self.assertEqual(readme.count(heading), 1)
        self.assertEqual(re.findall(r"^## (.+)$", readme, re.M)[0],
                         heading[3:])
        section = readme.split(heading, 1)[1].split("\n## ", 1)[0]
        self.assertEqual(re.findall(r"\]\((https://raw\.githubusercontent\.com/[^)]+)\)", section),
                         [RAW + path for path in FILES])
        for path in FILES:
            self.assertTrue((ROOT / path).is_file(), path)
        self.assertIn("18 October–21 November 2026 UTC", section)
        self.assertIn("20 October–23 November 2026 UTC", section)
        self.assertIn("not a live website", section)
        self.assertIn("do not combine them as one ranking", section)
        self.assertIn("import it as UTF-8", section)

    def test_quickstart_links_to_existing_detail_headings(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        section = readme.split("## Start here — choose a dated offline atlas", 1)[1].split("\n## ", 1)[0]
        anchors = re.findall(r"\]\(#([^)]+)\)", section)
        headings = re.findall(r"^## (.+)$", readme, re.M)
        # These English headings use only ASCII words and punctuation apart
        # from the em dash, which GitHub omits when constructing its anchors.
        slugs = [re.sub(r"[^\w -]", "", h.lower()).replace(" ", "-") for h in headings]
        self.assertEqual(len(anchors), 2)
        self.assertEqual(len(set(anchors)), 2)
        for anchor in anchors:
            self.assertIn(anchor, slugs)


if __name__ == "__main__":
    unittest.main()
