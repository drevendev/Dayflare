"""Keep the hosted atlas and separate dated downloads immediately discoverable."""
from pathlib import Path
import re
import hashlib
import unittest

ROOT = Path(__file__).resolve().parents[1]
RAW = "https://raw.githubusercontent.com/drevendev/Dayflare/master/"
HOSTED = "https://drevendev.github.io/Dayflare/"
ONLINE = "## Start here — explore the atlas online"
OFFLINE = "## Offline archives and CSV"
FILES = (
    "downloads/dayflare-30-2026-11-21.html",
    "downloads/dayflare-19-2026-11-23-summary.html",
    "downloads/dayflare-19-2026-11-23-weekly-signals.csv",
)


class VisitorQuickstartTests(unittest.TestCase):
    def test_hosted_entry_precedes_offline_archives_and_reproduction(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for heading in (ONLINE, OFFLINE):
            self.assertEqual(readme.count(heading), 1)
        self.assertEqual(re.findall(r"^## (.+)$", readme, re.M)[:2],
                         [ONLINE[3:], OFFLINE[3:]])
        section = readme.split(ONLINE, 1)[1].split("\n## ", 1)[0]
        self.assertEqual(re.findall(r"\]\((https?://[^)]+)\)", section),
                         [HOSTED, HOSTED + "dayflare-19-2026-11-23-summary.html"])
        self.assertIn("No installation or download required", section)
        self.assertIn("665 daily request counts across 19 selected", section)
        self.assertIn("20 October–23 November 2026 UTC", section)
        self.assertIn("dated snapshot", section)
        self.assertIn("not a live data feed", section)
        self.assertLess(readme.index(OFFLINE), readme.index("**Rebuild without new Wikimedia requests:**"))

    def test_dated_downloads_precede_reproduction_instructions(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(readme.count(OFFLINE), 1)
        section = readme.split(OFFLINE, 1)[1].split("\n## ", 1)[0]
        self.assertEqual(re.findall(r"\]\((https://raw\.githubusercontent\.com/[^)]+)\)", section),
                         [RAW + path for path in FILES])
        for path in FILES:
            self.assertTrue((ROOT / path).is_file(), path)
        self.assertIn("18 October–21 November 2026 UTC", section)
        self.assertIn("20 October–23 November 2026 UTC", section)
        self.assertIn("These links are offline copies", section)
        self.assertIn("separate access route to the same dated bytes", section)
        self.assertIn("do not combine them as one ranking", section)
        self.assertIn("import it as UTF-8", section)

    def test_updated_reader_preserves_historical_download_and_exact_bytes(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        historical = "downloads/dayflare-19-2026-11-23.html"
        self.assertIn(RAW + historical + ")", readme)
        opposite = "downloads/dayflare-19-2026-11-23-opposite.html"
        self.assertIn(RAW + opposite + ")", readme)
        pins = {
            historical: "b7b44b1757933a9b2d788fcddd63980cb64cfcd31f1996c8eb08eded0daf6d64",
            opposite: "aa7dff711511f4ee9239ca0bdc249a03adfa85f571c050ba57937edcc8c026c6",
            FILES[1]: "8045f27d478ee096adac09db35d35f767b45699aaf009483a206d4d617ef1d64",
        }
        for path, digest in pins.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
            self.assertIn(digest, readme)
        self.assertIn("6 gains, 12 drops, 1 unchanged, 4 opposite", readme)
        self.assertIn("Opposite to median change", readme)
        self.assertIn("data and observation/retrieval dates are unchanged", readme)

    def test_quickstart_links_to_existing_detail_headings(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        sections = [readme.split(heading, 1)[1].split("\n## ", 1)[0]
                    for heading in (ONLINE, OFFLINE)]
        online, offline = [re.findall(r"\]\(#([^)]+)\)", section)
                           for section in sections]
        self.assertEqual(online, ["public-hosting--verified-dated-atlas"])
        self.assertEqual(offline, [
            "try-the-expanded-atlas--30-measured-histories-21-nov-2026",
            "explore-a-separate-niche-atlas--19-measured-histories-23-nov-2026",
        ])
        anchors = online + offline
        headings = re.findall(r"^## (.+)$", readme, re.M)
        # These English headings use only ASCII words and punctuation apart
        # from the em dash, which GitHub omits when constructing its anchors.
        slugs = [re.sub(r"[^\w -]", "", h.lower()).replace(" ", "-") for h in headings]
        self.assertEqual(len(anchors), 3)
        self.assertEqual(len(set(anchors)), 3)
        for anchor in anchors:
            self.assertIn(anchor, slugs)


if __name__ == "__main__":
    unittest.main()
