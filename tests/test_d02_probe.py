import unittest

from tools.d02_probe import weekly_metrics


class WeeklyMetricsTests(unittest.TestCase):
    def test_method_v0_window_order_and_median_baseline(self) -> None:
        totals=[70,140,210,280,350]
        rows=[]
        for week,total in enumerate(totals):
            daily=total//7
            for day in range(7):
                rows.append({"date":f"2026-08-{week*7+day+1:02d}","views":daily})
        result=weekly_metrics(rows)
        self.assertEqual(result["weekly_totals_oldest_to_current"],totals)
        self.assertEqual(result["V"],350)
        self.assertEqual(result["H1"],280)
        self.assertEqual(result["H4"],70)
        self.assertEqual(result["B"],175)
        self.assertEqual(result["delta"],175)
        self.assertEqual(result["relative_lift"],1.0)

    def test_zero_baseline_has_no_relative_lift(self) -> None:
        rows=[{"date":f"d{i:02d}","views":10 if i>=28 else 0} for i in range(35)]
        result=weekly_metrics(rows)
        self.assertEqual(result["B"],0)
        self.assertEqual(result["V"],70)
        self.assertEqual(result["delta"],70)
        self.assertIsNone(result["relative_lift"])

    def test_requires_exactly_35_days(self) -> None:
        with self.assertRaises(ValueError):
            weekly_metrics([{"date":"2026-09-01","views":1}])


if __name__ == "__main__":
    unittest.main()
