"""Offline seed-collision regression; no Wikimedia access or synthetic source claims."""
from __future__ import annotations

from datetime import datetime, timezone
import unittest

from tools.rolling_pageview_source import SourceError, build, check_seed

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def seed(*pages):
    return {
        "schema_version": "dayflare.rolling-pageview-seeds.v1",
        "selected_at": "2026-10-24",
        "method_version": "v0-empirical-35d",
        "provider_lag_days": 2,
        "pages": list(pages),
    }


def row(project, page_id, title):
    return {"project": project, "page_id": page_id, "title": title, "subject": "sport"}


class SeedTitleCollisionTests(unittest.TestCase):
    def test_distinct_ids_with_same_edition_title_are_rejected(self):
        bad = seed(row("en.wikipedia", 100, "Chess"),
                   row("en.wikipedia", 200, "Chess"))
        with self.assertRaisesRegex(SourceError, "duplicate title-based Analytics query"):
            check_seed(bad, now=NOW)

    def test_spaces_and_underscores_target_same_query(self):
        bad = seed(row("en.wikipedia", 100, "Quantum mechanics"),
                   row("en.wikipedia", 200, "Quantum_mechanics"))
        with self.assertRaisesRegex(SourceError, "duplicate title-based Analytics query"):
            check_seed(bad, now=NOW)

    def test_fails_before_any_upstream_request(self):
        bad = seed(row("en.wikipedia", 100, "Chess"),
                   row("en.wikipedia", 200, "Chess"))
        def forbidden_fetch(url):
            self.fail("Provider request made before rejecting ambiguous seed")
        with self.assertRaisesRegex(SourceError, "duplicate title-based Analytics query"):
            build(bad, now=lambda: NOW, fetch=forbidden_fetch,
                  sleep=lambda _: None, injected=True)

    def test_same_title_in_distinct_editions_is_not_collision(self):
        good = seed(row("en.wikipedia", 100, "Chess"),
                    row("ru.wikipedia", 200, "Chess"))
        self.assertEqual(len(check_seed(good, now=NOW)), 2)

    def test_distinct_titles_in_one_edition_are_accepted(self):
        good = seed(row("en.wikipedia", 100, "Chess"),
                    row("en.wikipedia", 200, "Chess boxing"))
        self.assertEqual(len(check_seed(good, now=NOW)), 2)

    def test_existing_stable_id_uniqueness_is_preserved(self):
        bad = seed(row("en.wikipedia", 100, "Chess"),
                   row("en.wikipedia", 100, "Chess boxing"))
        with self.assertRaisesRegex(SourceError, "duplicate stable identity"):
            check_seed(bad, now=NOW)


if __name__ == "__main__":
    unittest.main()
