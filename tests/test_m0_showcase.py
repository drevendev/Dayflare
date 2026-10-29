"""Keep the public first-screen example tied to retained, measured Chess data."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


class TestM0Showcase(unittest.TestCase):
    def test_chess_spotlight_matches_retained_weekly_source(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        with ZipFile(ROOT / "evidence/d02-20261018/source.zip") as z:
            sample = json.loads(z.read("sample.json"))
            receipt = json.loads(z.read("receipt.json"))
        self.assertEqual(receipt["series_metrics"][2]["request"]["article"], "Chess")
        daily = sample[2]["items"]
        self.assertEqual(len(daily), 35)
        weekly = [sum(day["views"] for day in daily[i:i+7])
                  for i in range(0, 35, 7)]
        labels = re.findall(r'<li data-week="([1-5])" data-views="([0-9]+)">', html)
        self.assertEqual([int(i) for i, _ in labels], [1, 2, 3, 4, 5])
        self.assertEqual([int(value) for _, value in labels], weekly)
        self.assertEqual(weekly, [17094, 18328, 18460, 18411, 19804])
        self.assertEqual((weekly[1] + weekly[3]) / 2, 18369.5)
        self.assertIn("19,804", html)
        self.assertIn("18,369.5", html)
        self.assertIn('href="#discover">Discover all six measured histories', html)

    def test_home_prioritizes_accepted_20_title_atlas_without_erasing_m0(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        source = json.loads((ROOT / "site/m1-curated-20261023.json").read_text(encoding="utf-8"))
        self.assertEqual(source["coverage"]["measured"], 20)
        self.assertEqual(source["coverage"]["daily_observations"], 700)
        self.assertEqual(source["observation_window_utc"],
                         {"start": "2026-09-19", "end": "2026-10-23", "days": 35})
        self.assertIn('id="latest-atlas" href="https://raw.githubusercontent.com/drevendev/Dayflare/gh-pages/m1/index.html"', html)
        self.assertIn('id="latest-atlas-label">Download latest M1 atlas HTML', html)
        self.assertIn("22 Sep – 26 Oct 2026 UTC", html)
        self.assertIn("19 Sep – 23 Oct 2026", html)
        self.assertIn("retrieved 29 Oct 2026", html)
        self.assertIn("retrieved 26 October 2026", html)  # Older demo remains dated.
        self.assertIn("Earlier six-series experiment", html)
        self.assertIn("EARLIER SAMPLE / CHESS · EN", html)
        self.assertLess(html.index('aria-label="20 source-bound measured subject histories"'),
                        html.index('aria-label="Earlier six-series sample freshness"'))
        self.assertNotIn("live popularity feed", html.lower())

    def test_m1_link_resolves_without_pages_or_javascript(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        js = (ROOT / "site/app.js").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        fallback = "https://raw.githubusercontent.com/drevendev/Dayflare/gh-pages/m1/index.html"
        self.assertIn(f'href="{fallback}"', html)
        self.assertIn(fallback, readme)  # README and homepage agree on current artifact.
        self.assertNotIn('href="m1/"', html)  # Local source preview has no m1/ tree.
        self.assertIn("location.hostname === 'drevendev.github.io'", js)
        self.assertIn(r"/^\/Dayflare\/(?:index\.html)?$/", js)
        self.assertIn("latestAtlas.setAttribute('href', 'm1/')", js)
        self.assertIn("label.textContent = 'Explore latest M1 atlas'", js)
        self.assertIn('href="m1-curated-20261023.html"', html)
        self.assertIn("Earlier 19 Sep – 23 Oct atlas", html)
        self.assertIn("historical, not live", html)

    def test_accessible_static_story_and_honest_publication_text(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        css = (ROOT / "site/styles.css").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('aria-labelledby="spotlight-title"', html)
        self.assertIn('aria-label="Chess English Wikipedia: five exact weekly pageview totals"', html)
        self.assertIn("Requests ≠ people", html)
        self.assertIn("@media(max-width:580px)", css)
        # The target URL may be linked before activation, but it must never
        # be presented as a verified live site without served-byte acceptance.
        self.assertIn("**Public atlas URL (activation pending):**", readme)
        self.assertIn("[Open Dayflare](https://drevendev.github.io/Dayflare/)", readme)
        self.assertIn("**Not yet live-verified", readme)
        self.assertIn("not a claim that the website currently serves", readme)
        self.assertIn("Deploy from a branch → `gh-pages` → `/(root)`", readme)
        self.assertNotIn("Build and deployment → GitHub Actions", readme)


if __name__ == "__main__":
    unittest.main()
