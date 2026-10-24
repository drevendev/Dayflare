"""Fail-closed Chromium deadlines, including every observed 45s expiry."""
import unittest
from unittest.mock import patch

from tools import run_m0_ci


class BrowserBudgetTests(unittest.TestCase):
    def test_only_observed_four_suites_get_extended_deadlines(self):
        observed = {
            "browser_compare_daily.py",
            "browser_clipboard_race.py",
            "browser_discovery_order.py",
            "browser_nojs.py",
        }
        self.assertEqual(run_m0_ci.EXTENDED_BROWSER_BUDGETS, observed)
        self.assertTrue(observed.issubset(run_m0_ci.BROWSERS))
        for name in run_m0_ci.BROWSERS:
            with self.subTest(name=name):
                expected = 90 if name in observed else 45
                self.assertEqual(run_m0_ci.browser_suite_timeout(name), expected)

    def test_every_extended_timeout_is_still_a_failure(self):
        for suite in sorted(run_m0_ci.EXTENDED_BROWSER_BUDGETS):
            with self.subTest(suite=suite):
                with patch.object(run_m0_ci, "bounded_browser_command",
                                  return_value=(124, "started", "blocked", True)) as invoke:
                    name, code, stdout, stderr, elapsed = run_m0_ci.run_browser_suite(suite)
                self.assertEqual(name, suite)
                self.assertEqual(code, 124)
                self.assertEqual(stdout, "started")
                self.assertIn("blocked", stderr)
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
