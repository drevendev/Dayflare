import copy
import unittest

from tools.d01_probe import analyze_items, expected_dates

SPEC = {
    "project": "en.wikipedia.org",
    "article": "Artificial_intelligence",
    "subject": "science/technology",
}
EXPECTED = expected_dates("20260901", "20260914")


def valid_item(date: str, views: int = 10) -> dict[str, object]:
    return {
        "project": "en.wikipedia",
        "article": "Artificial_intelligence",
        "access": "all-access",
        "agent": "user",
        "granularity": "daily",
        "timestamp": date.replace("-", "") + "00",
        "views": views,
    }


class AnalyzeItemsTests(unittest.TestCase):
    def test_complete_valid_payload_passes_without_zero_fill(self) -> None:
        result = analyze_items([valid_item(day) for day in EXPECTED], SPEC, EXPECTED)
        self.assertTrue(result["semantic_valid"])
        self.assertEqual(result["omitted_zero_days"], [])
        self.assertEqual(result["unresolved_days"], [])
        self.assertTrue(result["normalized_complete"])

    def test_one_omitted_day_is_documented_zero_only_after_semantic_validation(self) -> None:
        missing = EXPECTED[5]
        result = analyze_items(
            [valid_item(day) for day in EXPECTED if day != missing],
            SPEC,
            EXPECTED,
        )
        self.assertTrue(result["semantic_valid"])
        self.assertEqual(result["omitted_zero_days"], [missing])
        self.assertEqual(result["unresolved_days"], [])
        filled = [item for item in result["normalized_items"] if item["date"] == missing]
        self.assertEqual(filled[0]["views"], 0)
        self.assertEqual(filled[0]["value_state"], "documented_omitted_zero")

    def test_semantic_mismatches_fail_whole_series_closed(self) -> None:
        cases = {}

        payload = [valid_item(day) for day in EXPECTED]
        payload[0]["project"] = "ru.wikipedia"
        cases["project"] = payload

        payload = [valid_item(day) for day in EXPECTED]
        payload[0]["access"] = "desktop"
        cases["access"] = payload

        payload = [valid_item(day) for day in EXPECTED]
        payload[0]["agent"] = "spider"
        cases["agent"] = payload

        payload = [valid_item(day) for day in EXPECTED]
        payload[0]["granularity"] = "monthly"
        cases["granularity"] = payload

        payload = [valid_item(day) for day in EXPECTED]
        payload[0]["views"] = True
        cases["views_bool"] = payload

        payload = [valid_item(day) for day in EXPECTED]
        payload[0]["views"] = -1
        cases["views_negative"] = payload

        payload = [valid_item(day) for day in EXPECTED]
        payload[0]["views"] = 1.5
        cases["views_float"] = payload

        payload = [valid_item(day) for day in EXPECTED]
        payload.append(copy.deepcopy(payload[0]))
        cases["duplicate_timestamp"] = payload

        payload = [valid_item(day) for day in EXPECTED]
        payload[-1]["timestamp"] = "2026083100"
        cases["out_of_window"] = payload

        for name, items in cases.items():
            with self.subTest(name=name):
                result = analyze_items(items, SPEC, EXPECTED)
                self.assertFalse(result["semantic_valid"])
                self.assertTrue(result["semantic_errors"])
                self.assertEqual(result["omitted_zero_days"], [])
                self.assertEqual(result["unresolved_days"], EXPECTED)
                self.assertEqual(result["normalized_items"], [])
                self.assertFalse(result["normalized_complete"])


if __name__ == "__main__":
    unittest.main()
