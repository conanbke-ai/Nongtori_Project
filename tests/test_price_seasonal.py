"""Targeted seasonal baseline regressions using synthetic versioned prices."""

from dataclasses import replace
from datetime import date, datetime, time
import unittest

from ml.price_forecast.baseline import DailyPrice, evaluate_baselines
from ml.price_forecast.incremental_planner import KST, Series


SERIES = Series("synthetic", "01", "00001101", "02", "03", "04", "05", "12:2:box")


def daily(day, price, *, series=SERIES):
    trade_day = date(2026, 1, day)
    return DailyPrice(series, trade_day, datetime.combine(trade_day, time(16), KST), price, 70.0, "a" * 64)


def evaluate(rows, *, end=8, **options):
    report = evaluate_baselines(
        rows,
        start=date(2026, 1, 8),
        end=date(2026, 1, end),
        labels_as_of=datetime(2026, 1, 10, tzinfo=KST),
        window=2,
        **options,
    )
    series = next(row for row in report["series"] if row["series"]["origin"] == SERIES.origin)
    return report, series, series["seasonal_comparison"]


class PriceSeasonalTests(unittest.TestCase):
    def test_metrics_compare_all_three_on_shared_dates_and_preserve_pair_coverage(self):
        rows = [
            daily(1, 100), daily(2, 990, series=replace(SERIES, origin="99")),
            daily(6, 120), daily(7, 130), daily(8, 160), daily(9, 700),
        ]
        report, paired, seasonal = evaluate(rows, end=9)
        self.assertEqual(report["seasonal_period_days"], 7)
        self.assertEqual(paired["scored_days"], 2)
        self.assertEqual(paired["metrics"]["latest"]["mae_krw_per_kg"], 285)
        self.assertEqual(paired["metrics"]["moving_average"]["mae_krw_per_kg"], 295)
        self.assertEqual((seasonal["scored_days"], seasonal["missing_seasonal_history_days"]), (1, 1))
        self.assertEqual(
            {name: metrics["mae_krw_per_kg"] for name, metrics in seasonal["metrics"].items()},
            {"latest": 30, "moving_average": 35, "seasonal_naive": 60},
        )
        self.assertEqual(
            [(p["trade_day"], p["seasonal_history_trade_day"], p["seasonal_naive_krw_per_kg"])
             for p in seasonal["predictions"]],
            [("2026-01-08", "2026-01-01", 100)],
        )

    def test_correction_and_withdrawal_use_the_exclusive_forecast_cutoff(self):
        original = daily(1, 100)
        rows = [original, daily(6, 120), daily(7, 130), daily(8, 160)]
        at_cutoff = replace(original, available_at=datetime(2026, 1, 8, tzinfo=KST), price_krw_per_kg=900)
        previous_day = replace(at_cutoff, available_at=datetime(2026, 1, 7, 23, 59, 59, tzinfo=KST))
        withdrawal = replace(previous_day, price_krw_per_kg=None, trade_volume_kg=None)

        _, _, seasonal = evaluate([at_cutoff, *rows])
        self.assertEqual(seasonal["predictions"][0]["seasonal_naive_krw_per_kg"], 100)
        _, _, seasonal = evaluate([previous_day, *rows])
        self.assertEqual(seasonal["predictions"][0]["seasonal_naive_krw_per_kg"], 900)
        _, paired, seasonal = evaluate([withdrawal, *rows])
        self.assertEqual(paired["scored_days"], 1)
        self.assertEqual(seasonal["missing_seasonal_history_days"], 1)
        self.assertIsNone(seasonal["metrics"])

    def test_lag_shorter_than_forecast_horizon_is_not_available(self):
        rows = [daily(1, 100), daily(4, 120), daily(5, 130), daily(7, 900), daily(8, 160)]
        report, paired, seasonal = evaluate(rows, horizon_days=2, seasonal_period_days=1)
        self.assertEqual(report["seasonal_period_days"], 1)
        self.assertEqual(paired["scored_days"], 1)
        self.assertEqual(seasonal["missing_seasonal_history_days"], 1)
        self.assertIsNone(seasonal["metrics"])

    def test_zero_price_is_an_available_seasonal_history(self):
        rows = [daily(1, 0), daily(6, 120), daily(7, 130), daily(8, 160)]
        _, _, seasonal = evaluate(rows)
        self.assertEqual(seasonal["scored_days"], 1)
        self.assertEqual(seasonal["predictions"][0]["seasonal_naive_krw_per_kg"], 0)

    def test_invalid_calendar_lag_is_rejected(self):
        for lag in (0, -7, 7.0, True):
            with self.subTest(lag=lag), self.assertRaisesRegex(ValueError, "seasonal_period_days"):
                evaluate([daily(1, 100)], seasonal_period_days=lag)


if __name__ == "__main__":
    unittest.main()
