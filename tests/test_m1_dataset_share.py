"""Offline synthetic regression for exact-dataset M1 topic sharing; no live claim."""
from __future__ import annotations

from datetime import date, timedelta
from html import unescape
from pathlib import Path
import re
import unittest
from urllib.parse import parse_qs, urlsplit

from tools.rolling_snapshot_preview import render_html


class DatasetShareMarkupTests(unittest.TestCase):
    def test_exact_dataset_and_edition_are_encoded_in_all_links(self):
        start = date(2026, 9, 21)
        rows = []
        seeds = []
        for project, page_id, title, subject in (
            ("en.wikipedia", 1234, "Games & <img src=x onerror=alert(1)>", "games"),
            ("ru.wikipedia", 5678, "Шахматы", "culture"),
        ):
            rows.append({
                "project": project, "page_id": page_id, "title": title,
                "daily": [{"date": (start + timedelta(days=i)).isoformat(),
                           "views": i + 1, "value_state": "observed"}
                          for i in range(35)],
                "source": {
                    "endpoint": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/example",
                    "requested_at": "2026-10-28T12:00:00Z",
                    "http_status": 200, "body_sha256": "b" * 64,
                },
            })
            seeds.append({"project": project, "page_id": page_id,
                          "title": title, "subject": subject})
        candidate = {
            "dataset_id": "synthetic-fixture-only", "method_version": "v0-empirical-35d",
            "observation_end": "2026-10-25", "retrieved_at": "2026-10-28T12:00:00Z",
            "series": rows,
        }
        seed = {"pages": seeds}
        proof = {"candidate_sha256": "a" * 64,
                 "provenance_status": "synthetic_injected_not_upstream_evidence"}
        output = render_html(candidate, seed, proof).decode("utf-8")
        self.assertEqual(output, render_html(candidate, seed, proof).decode("utf-8"))
        self.assertIn("SYNTHETIC TEST DATA", output)
        self.assertEqual(output.count("Share this exact history"), 2)
        self.assertIn('id="share-restore"', output)
        self.assertIn('data-dataset="' + "a" * 64 + '"', output)
        self.assertIn('data-method="v0-empirical-35d"', output)
        self.assertIn('data-end="2026-10-25"', output)
        self.assertIn('aria-live="polite"', output)
        self.assertIn("requires JavaScript to restore", output)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", output)
        self.assertNotIn("<img src=x onerror", output)
        links = re.findall(r'href="(\?[^"]+#share-restore)"', output)
        self.assertEqual(len(links), 2)
        found = set()
        for raw in links:
            link = urlsplit(unescape(raw))
            self.assertEqual(link.fragment, "share-restore")
            params = parse_qs(link.query, strict_parsing=True)
            self.assertEqual(set(params), {
                "df_dataset", "df_method", "df_end", "df_edition", "df_page",
            })
            self.assertEqual(params["df_dataset"], ["a" * 64])
            self.assertEqual(params["df_method"], ["v0-empirical-35d"])
            self.assertEqual(params["df_end"], ["2026-10-25"])
            found.add((params["df_edition"][0], params["df_page"][0]))
        self.assertEqual(found, {("en.wikipedia", "1234"), ("ru.wikipedia", "5678")})
        script = Path(__file__).resolve().parents[1] / "tools/m1_dataset_share.js"
        self.assertIn("<script>" + script.read_text(encoding="utf-8") + "</script>", output)
        self.assertNotIn('<script src=', output)
        self.assertNotIn("fetch(", script.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
