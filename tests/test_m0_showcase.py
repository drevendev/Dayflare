"""Keep the public first-screen example tied to retained, measured Chess data."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_M1_REVISION = "4851d6a7e106f02261b6e7a58226295ac94a664d"


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
        self.assertIn('id="latest-atlas" href="https://raw.githubusercontent.com/drevendev/Dayflare/' + ACCEPTED_M1_REVISION + '/m1/index.html"', html)
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
        self.assertIn('<a class="skip" href="#m1-spotlight-title">Skip to accepted M1 evidence</a>', html)
        self.assertIn('<h2 id="m1-spotlight-title" class="spotlight-heading" tabindex="-1">', html)
        self.assertLess(html.index('id="latest-atlas"'),
                        html.index('class="hero-explore hero-compare"'))
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

    def test_books_cross_edition_entry_uses_two_measured_historical_titles(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        source = json.loads((ROOT / "site/m1-curated-20261023.json").read_text(encoding="utf-8"))
        by_id = {(row["project"], row["observed_page_id"]): row for row in source["series"]}
        left = by_id["en.wikipedia", 155311]
        right = by_id["ru.wikipedia", 6269]
        self.assertEqual((left["title"], right["title"]), ("War and Peace", "Война и мир"))
        self.assertEqual((left["computed"]["weekly_totals"][-1],
                          right["computed"]["weekly_totals"][-1]), (14110, 3792))
        self.assertEqual(len(left["daily_views"]), 35)
        self.assertEqual(len(right["daily_views"]), 35)
        self.assertEqual(source["observation_window_utc"]["end"], "2026-10-23")
        self.assertEqual(source["cross_edition_equivalence"], "NOT_ASSUMED")
        self.assertIn('class="m1-pair-compare" href="m1-curated-20261023.html?ds='
                      'm1-curated-20261023-d96477427ece&amp;a=topic-en-155311&amp;'
                      'b=topic-ru-6269#curated-compare"', html)
        self.assertIn("not populations or verified identical identity", html)

    def test_subject_shortcuts_compare_exact_measured_earlier_edition_histories(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        source = json.loads((ROOT / "site/m1-curated-20261023.json").read_text(encoding="utf-8"))
        self.assertEqual(source["observation_window_utc"],
                         {"start": "2026-09-19", "end": "2026-10-23", "days": 35})
        self.assertEqual(source["cross_edition_equivalence"], "NOT_ASSUMED")
        rows = {(row["project"], row["observed_page_id"]): row for row in source["series"]}
        cases = (
            ("Culture", 18839, "Music", 19366, 463, "Музыка", 2104),
            ("Games", 5134, "Chess", 25917, 10646, "Шахматы", 4310),
            ("Science", 4650, "Black hole", 50073, 8474, "Чёрная дыра", 6544),
            ("Sport", 23976719, "Football", 11121, 7963, "Футбол", 3211),
        )
        for subject, en_id, en_title, en_week, ru_id, ru_title, ru_week in cases:
            with self.subTest(subject=subject):
                for project, page_id, title, total in (
                    ("en.wikipedia", en_id, en_title, en_week),
                    ("ru.wikipedia", ru_id, ru_title, ru_week),
                ):
                    row = rows[project, page_id]
                    self.assertEqual(row["title"], title)
                    self.assertEqual(row["computed"]["weekly_totals"][-1], total)
                    self.assertEqual(len(row["daily_views"]), 35)
                link = ('m1-curated-20261023.html?ds=m1-curated-20261023-d96477427ece'
                        f'&amp;a=topic-en-{en_id}&amp;b=topic-ru-{ru_id}#curated-compare')
                slug = subject.lower()
                heading = f'<h4 id="m1-subject-{slug}" tabindex="-1">{subject}</h4>'
                self.assertEqual(html.count(heading), 1)
                block = html.split(heading, 1)[1].split(
                    '<div class="m1-subject-pair">', 1)[0]
                self.assertIn(f'href="{link}"', block)
                self.assertIn("not verified identical entities or populations", block)
        self.assertEqual(html.count('class="m1-pair-compare"'), 5)

    def test_m1_link_resolves_without_pages_or_javascript(self):
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        js = (ROOT / "site/app.js").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        fallback = "https://raw.githubusercontent.com/drevendev/Dayflare/" + ACCEPTED_M1_REVISION + "/m1/index.html"
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
        # Guard the dated public claim independently of the historical M0 source.
        section = readme.split("## Public hosting — verified dated atlas", 1)[1].split(
            "\n## ", 1)[0]
        self.assertIn("[Public Dayflare](https://drevendev.github.io/Dayflare/)", section)
        self.assertIn("native GitHub Pages deployment from `gh-pages`", section)
        self.assertIn("72b225f04e9726a40178ddf866abfdcc47e42a4d", section)
        self.assertIn("https://github.com/drevendev/Dayflare/actions/runs/46070045638", section)
        self.assertIn("anonymous production check on 27 November 2026 UTC", section)
        self.assertIn("reported in the 28 November 00:12 UTC handoff", section)
        self.assertIn("https://github.com/drevendev/Dayflare/issues/12#issuecomment-7235258847", section)
        self.assertIn("not an original HTTP transcript or a fresh reachability test", section)
        self.assertIn("HTTP 200, `text/html`, 329,286 bytes", section)
        self.assertIn("8045f27d478ee096adac09db35d35f767b45699aaf009483a206d4d617ef1d64", section)
        self.assertIn("opposite-direction filter (4/19)", section)
        self.assertIn("English NetHack/OpenTTD comparison", section)
        self.assertIn("not a continuous availability or freshness guarantee", section)
        self.assertIn("not the later anonymous HTTP check", section)
        self.assertIn("successful CI and deployment alone do not establish the bytes served by a public URL", section)
        self.assertIn("local HTTP, not a production screenshot or independent external user study", section)
        self.assertIn("not yet part of these immutable hosted bytes", section)
        self.assertNotIn("**Public atlas URL (activation pending):**", readme)
        self.assertNotIn("GitHub reports `has_pages=false`", readme)
        self.assertIn("**[Download the accepted M1 atlas (11 Nov 2026; pinned HTML)](", readme)
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
        self.assertIn("five exact CSV routes (single-title daily; paired daily, weekly and week-over-week changes; filtered visible-title daily)", readme)
        self.assertIn("35-day zero-origin SVG timelines", readme)
        self.assertIn("Chart heights between different titles are not directly comparable.", readme)
        self.assertIn("### Earlier accepted release example (1 November snapshot; not current)", readme)
        self.assertNotIn("**Latest accepted archive (observed 29 September", readme)


if __name__ == "__main__":
    unittest.main()
