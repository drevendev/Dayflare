"""Fail-closed Chrome process deadlines, including the cold-start comparison case."""
import unittest
from unittest.mock import patch

from tools import run_m0_ci


class BrowserBudgetTests(unittest.TestCase):
    def test_only_daily_comparison_has_extended_deadline(self):
        self.assertIn("browser_compare_daily.py", run_m0_ci.BROWSERS)
        self.assertEqual(run_m0_ci.browser_suite_timeout("browser_compare_daily.py"), 90)
        for name in run_m0_ci.BROWSERS:
            if name != "browser_compare_daily.py":
                with self.subTest(name=name):
                    self.assertEqual(run_m0_ci.browser_suite_timeout(name), 45)

    def test_comparison_timeout_is_still_a_failure(self):
        with patch.object(run_m0_ci, "bounded_browser_command",
                          return_value=(124, "started", "blocked startup", True)) as invoke:
            name, code, stdout, stderr, elapsed = run_m0_ci.run_browser_suite(
                "browser_compare_daily.py")
        self.assertEqual(name, "browser_compare_daily.py")
        self.assertEqual(code, 124)
        self.assertEqual(stdout, "started")
        self.assertIn("blocked startup", stderr)
        self.assertIn("TIMEOUT after 90s", stderr)
        self.assertGreaterEqual(elapsed, 0)
        self.assertEqual(invoke.call_args.kwargs["timeout"], 90)

    def test_other_browser_deadline_remains_unchanged(self):
        with patch.object(run_m0_ci, "bounded_browser_command",
                          return_value=(124, "", "", True)) as invoke:
            _, code, _, stderr, _ = run_m0_ci.run_browser_suite(
                "browser_history_disclosure.py")
        self.assertEqual(code, 124)
        self.assertIn("TIMEOUT after 45s", stderr)
        self.assertEqual(invoke.call_args.kwargs["timeout"], 45)


if __name__ == "__main__":
    unittest.main()
