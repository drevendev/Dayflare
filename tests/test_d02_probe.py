import unittest
from datetime import date, timedelta

from tools.d02_probe import lifecycle_metrics, weekly_metrics


def make_rows(totals: list[int] | None = None) -> list[dict[str, object]]:
    totals=totals or [70,140,210,280,350]
    start=date(2026,8,11)
    rows=[]
    for week,total in enumerate(totals):
        daily=total//7
        for day in range(7):
            rows.append({
                "date":(start+timedelta(days=week*7+day)).isoformat(),
                "views":daily,
            })
    return rows


class WeeklyMetricsTests(unittest.TestCase):
    def test_method_v0_window_order_and_median_baseline(self) -> None:
        result=weekly_metrics(make_rows())
        self.assertEqual(result["weekly_totals_oldest_to_current"],[70,140,210,280,350])
        self.assertEqual(result["V"],350)
        self.assertEqual(result["H1"],280)
        self.assertEqual(result["H4"],70)
        self.assertEqual(result["B"],175)
        self.assertEqual(result["delta"],175)
        self.assertEqual(result["relative_lift"],1.0)

    def test_zero_baseline_has_no_relative_lift(self) -> None:
        result=weekly_metrics(make_rows([0,0,0,0,70]))
        self.assertEqual(result["B"],0)
        self.assertEqual(result["V"],70)
        self.assertEqual(result["delta"],70)
        self.assertIsNone(result["relative_lift"])

    def test_requires_exactly_35_days(self) -> None:
        with self.assertRaises(ValueError):
            weekly_metrics([{"date":"2026-09-01","views":1}])

    def test_rejects_duplicate_dates(self) -> None:
        rows=make_rows()
        rows[1]["date"]=rows[0]["date"]
        with self.assertRaisesRegex(ValueError,"unique"):
            weekly_metrics(rows)

    def test_rejects_gapped_dates(self) -> None:
        rows=make_rows()
        rows[-1]["date"]="2026-09-15"
        with self.assertRaisesRegex(ValueError,"consecutive"):
            weekly_metrics(rows)

    def test_rejects_invalid_calendar_date(self) -> None:
        rows=make_rows()
        rows[0]["date"]="2026-08-32"
        with self.assertRaisesRegex(ValueError,"invalid calendar date"):
            weekly_metrics(rows)

    def test_rejects_noncanonical_date(self) -> None:
        rows=make_rows()
        rows[0]["date"]="2026-8-11"
        with self.assertRaises(ValueError):
            weekly_metrics(rows)

    def test_rejects_non_integer_and_negative_views(self) -> None:
        for bad in (True,"9",1.9,-1):
            with self.subTest(value=bad):
                rows=make_rows()
                rows[0]["views"]=bad
                with self.assertRaisesRegex(ValueError,"non-negative integer"):
                    weekly_metrics(rows)


class LifecycleMetricsTests(unittest.TestCase):
    def test_return_from_quiet_counterexample_is_parameterized(self) -> None:
        result=lifecycle_metrics(
            [1000,1000,1000],
            [100,120,80,90],
            900,
            q_max=0.2,
            r_min=0.8,
            min_current_volume=100,
            min_absolute_change=100,
        )
        self.assertEqual(result["normal_windows"],3)
        self.assertEqual(result["quiet_windows"],4)
        self.assertEqual(result["N"],1000)
        self.assertEqual(result["Q"],95)
        self.assertAlmostEqual(result["quiet_ratio"],0.095)
        self.assertAlmostEqual(result["return_ratio"],0.9)
        self.assertEqual(result["return_delta"],805)
        self.assertTrue(result["eligible"])
        self.assertTrue(result["returning"])

    def test_block_lengths_are_not_hardcoded(self) -> None:
        result=lifecycle_metrics(
            [800,1000,1200,1000,1000],
            [100,100],
            850,
            q_max=0.2,
            r_min=0.8,
        )
        self.assertEqual(result["normal_windows"],5)
        self.assertEqual(result["quiet_windows"],2)
        self.assertTrue(result["returning"])

    def test_zero_normal_level_keeps_ratios_undefined(self) -> None:
        result=lifecycle_metrics(
            [0,0],
            [0,0],
            50,
            q_max=0.2,
            r_min=0.8,
        )
        self.assertIsNone(result["quiet_ratio"])
        self.assertIsNone(result["return_ratio"])
        self.assertFalse(result["returning"])

    def test_eligibility_floors_can_reject_tiny_return(self) -> None:
        result=lifecycle_metrics(
            [10,10],
            [0,0],
            1,
            q_max=0.2,
            r_min=0.1,
            min_current_volume=10,
            min_absolute_change=5,
        )
        self.assertFalse(result["eligible"])
        self.assertFalse(result["returning"])

    def test_requires_explicit_nonempty_blocks(self) -> None:
        with self.assertRaisesRegex(ValueError,"older_normal_totals"):
            lifecycle_metrics([], [1], 1, q_max=0.2, r_min=0.8)
        with self.assertRaisesRegex(ValueError,"recent_quiet_totals"):
            lifecycle_metrics([1], [], 1, q_max=0.2, r_min=0.8)

    def test_rejects_invalid_lifecycle_inputs(self) -> None:
        cases = [
            (([-1], [0], 1), {"q_max":0.2,"r_min":0.8}),
            (([1], [0], -1), {"q_max":0.2,"r_min":0.8}),
            (([1], [0], 1), {"q_max":-0.1,"r_min":0.8}),
            (([1], [0], 1), {"q_max":0.2,"r_min":True}),
        ]
        for args, kwargs in cases:
            with self.subTest(args=args,kwargs=kwargs):
                with self.assertRaisesRegex(ValueError,"non-negative"):
                    lifecycle_metrics(*args,**kwargs)


if __name__ == "__main__":
    unittest.main()
