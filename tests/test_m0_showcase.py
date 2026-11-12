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
        self.assertIn("ACCEPTED DATED M1 ARCHIVE", html)
        self.assertNotIn("22 Sep – 26 Oct 2026 UTC", html)
        self.assertIn("700 exact daily observations", html)
        self.assertIn("19 September–23 October 2026 UTC", html)  # Historical on-page demo.
        self.assertIn('href="https://github.com/drevendev/Dayflare/blob/gh-pages/m1/release-manifest.json"', html)
        self.assertIn("Its exact observation window, retrieval timestamp, dataset and method", html)
        self.assertIn("not a verified hosted service", html)
        self.assertNotIn("retrieved 29 Oct 2026", html)
        self.assertIn("retrieved 26 October 2026", html)  # Older demo remains dated.
        self.assertIn("Earlier six-series experiment", html)
        # Portable six-series HTML remaps the keyboard shortcut back to M0.
        self.assertIn('<a class="skip" href="#latest-atlas">Skip to latest accepted M1 atlas</a>', html)
        from tools.build_portable import build_html
        offline = build_html().decode('utf-8')
        self.assertIn('<a class="skip" href="#discover">Skip to six-series discovery</a>', offline)
        self.assertNotIn('Skip to latest accepted M1 atlas', offline)
        self.assertNotIn('the Chess six-series and October examples further down', offline)
        self.assertIn("EARLIER SAMPLE / CHESS · EN", html)
        self.assertLess(html.index('aria-label="20 source-bound measured subject histories"'),
                        html.index('aria-label="Earlier six-series sample freshness"'))
        self.assertNotIn("live popularity feed", html.lower())

    def test_first_screen_accepted_window_matches_current_release_facts(self):
        """The visible M1 dates must track independently reviewed README facts.

        This is consistency validation, not source authentication or proof of Pages.
        """
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        section = readme.split("<!-- dayflare:m1-release:start -->", 1)[1].split(
            "<!-- dayflare:m1-release:end -->", 1
        )[0]
        accepted = re.search(
            r"Latest accepted archive \(observed (\d{4}-\d{2}-\d{2})"
            r"–(\d{4}-\d{2}-\d{2}) UTC; retrieved "
            r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) UTC\)",
            section,
        )
        self.assertIsNotNone(accepted)
        start, end, retrieved_day, retrieved_clock = accepted.groups()
        retrieved_iso = f"{retrieved_day}T{retrieved_clock}Z"
        hero = html.split('<p id="accepted-window"', 1)
        self.assertEqual(len(hero), 2, "first-screen accepted-window marker required")
        hero = hero[1].split("</p>", 1)[0]
        self.assertIn(f'data-observed-start="{start}"', hero)
        self.assertIn(f'data-observed-end="{end}"', hero)
        self.assertIn(f'data-retrieved-at="{retrieved_iso}"', hero)
        self.assertIn(f'<time datetime="{start}">', hero)
        self.assertIn(f'<time datetime="{end}">', hero)
        self.assertIn(f'<time datetime="{retrieved_iso}">', hero)
        self.assertIn("Historical title requests, not live attention or unique people", hero)
        self.assertLess(html.index('id="accepted-window"'), html.index('id="latest-atlas"'))

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
        # Pages is a target, not a fake working CTA when GitHub has_pages=false.
        self.assertIn("**Public atlas URL (activation pending):**", readme)
        self.assertIn("`https://drevendev.github.io/Dayflare/`", readme)
        self.assertNotIn("[Open Dayflare](https://drevendev.github.io/Dayflare/)", readme)
        self.assertRegex(readme, r"\*\*Not live-verified \(\d{1,2} [A-Za-z]+ 20\d{2}\):\*\*")
        self.assertIn("a branch commit and successful browser CI do not prove", readme)
        self.assertIn("**Not live-verified (9 November 2026):**", readme)
        self.assertIn("Public HTTP access could not be confirmed from the available reader on 9 November 2026", readme)
        self.assertIn("this is **not evidence of an HTTP response status**", readme)
        self.assertIn("The fresh repository API read on 9 November reports `has_pages=false`", readme)
        self.assertNotIn("GitHub reports `has_pages=false`", readme)
        self.assertIn("**[Download the self-contained M1 atlas (HTML)](", readme)
        self.assertIn("Deploy from a branch → `gh-pages` → `/(root)`", readme)
        self.assertNotIn("Build and deployment → GitHub Actions", readme)


    def test_readme_latest_release_not_confused_with_earlier_archive(self):
        """Check current release facts without locking the test to one dated archive.

        The exact independently pinned manifest and HTML are validated in
        test_m1_readme_sync. This checks the public README scope and distinctions.
        """
        from datetime import date, datetime
        from tools.m1_readme_sync import END, METHOD, SCHEMA, START

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertLess(readme.index("## Try the measured atlas"),
                        readme.index("## Explore the real 4–5 November identity comparison"))
        self.assertEqual(readme.count(START), 1)
        self.assertEqual(readme.count(END), 1)
        self.assertLess(readme.index(START), readme.index(END))
        latest = readme.split(START, 1)[1].split(END, 1)[0].strip()
        self.assertEqual(latest.count("**Latest accepted archive ("), 1)
        match = re.match(
            r"\*\*Latest accepted archive \(observed "
            r"(\d{4}-\d{2}-\d{2})–(\d{4}-\d{2}-\d{2}) UTC; "
            r"retrieved (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) UTC\):\*\* ",
            latest,
        )
        self.assertIsNotNone(match, "M1 release dates must be explicit and ISO formatted")
        start, end, retrieved_day, retrieved_time = match.groups()
        self.assertEqual((date.fromisoformat(end) - date.fromisoformat(start)).days, 34)
        datetime.strptime(retrieved_day + "T" + retrieved_time + "Z",
                          "%Y-%m-%dT%H:%M:%SZ")
        self.assertGreater(date.fromisoformat(retrieved_day), date.fromisoformat(end))
        self.assertIn("20 editor-selected title-scoped EN/RU histories", latest)
        self.assertIn("across books, culture, games, science and sport", latest)
        self.assertIn("five complete UTC weeks / 700 daily request observations", latest)
        self.assertRegex(latest, r"Dataset `run-\d{8}-\d{6}-[0-9a-f]{12}`")
        self.assertIn("method `" + METHOD + "`", latest)
        self.assertIn("schema `" + SCHEMA + "`", latest)
        self.assertIn("[Accepted release manifest](https://github.com/drevendev/Dayflare/blob/gh-pages/m1/release-manifest.json)", latest)
        self.assertRegex(latest, r"downloadable HTML SHA-256 `[0-9a-f]{64}`")
        self.assertIn("The manifest pin must be independently established by native release review", latest)
        self.assertIn("this generated summary alone does not authenticate Wikimedia", latest)
        self.assertIn("Counts are requests, **not** people", latest)
        self.assertIn("This selected, dated sample is **not** a representative ranking, live refresh or verified deployed website.", latest)
        # Historic release evidence lives outside the generated paragraph; a
        # newer release must not inherit those review/CI links as its own.
        provenance = readme.split(END, 1)[1].split(
            "### Earlier accepted release example", 1)[0]
        self.assertIn("Historical acceptance evidence", provenance)
        self.assertRegex(provenance, r"https://github[.]com/drevendev/Dayflare/pull/[0-9]+")
        self.assertRegex(provenance, r"https://github[.]com/drevendev/Dayflare/actions/runs/[0-9]+")
        self.assertRegex(provenance, r"https://github[.]com/drevendev/Dayflare/commit/[0-9a-f]{40}")
        self.assertIn("does **not** establish that the public Pages URL is serving it", provenance)
        self.assertIn("This example is from a **different, earlier dataset** than the current download.", readme)
        self.assertIn("four exact CSV routes (single-title daily, paired daily and weekly, plus filtered visible-title daily downloads)", readme)
        self.assertIn("35-day zero-origin SVG timelines", readme)
        self.assertIn("Chart heights between different titles are not directly comparable.", readme)
        self.assertIn("### Earlier accepted release example (1 November snapshot; not current)", readme)
        self.assertNotIn("**Latest accepted archive (observed 29 September", readme)


if __name__ == "__main__":
    unittest.main()
