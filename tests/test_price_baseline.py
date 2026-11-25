import io
import unittest
from dataclasses import replace
from datetime import date, datetime

from ml.price_forecast.baseline import DailyPrice, evaluate_baselines, load_daily_prices
from ml.price_forecast.incremental_planner import KST, Series


SERIES = Series("synthetic", "01", "00001101", "02", "03", "04", "05", "12:2:box")
HEADER = (
    "provider,market,corporation,product,origin,cultivar,grade,unit,trade_day,"
    "available_at,status,price_krw_per_kg,trade_volume_kg,source_sha256\n"
)
CSV_ROW = (
    "synthetic,01,00001101,02,03,04,05,12:2:box,2026-01-01,2026-01-01T16:00:00+09:00,TRADED,20,70,"
    + "a" * 64
)


def daily(day, price, *, available=None, series=SERIES):
    return DailyPrice(series, date(2026, 1, day), available or datetime(2026, 1, day, 16, tzinfo=KST),
                      price, 70.0, "a" * 64)


def evaluate(rows, *, start=3, end=5, labels_day=7, **kwargs):
    return evaluate_baselines(
        rows, start=date(2026, 1, start), end=date(2026, 1, end),
        labels_as_of=datetime(2026, 1, labels_day, tzinfo=KST), window=2, **kwargs,
    )


class PriceBaselineTests(unittest.TestCase):
    def test_prerevision_history_and_fixed_labels(self):
        original = daily(2, 30)
        correction = daily(2, 50, available=datetime(2026, 1, 3, 18, tzinfo=KST))
        late_label_correction = daily(3, 300, available=datetime(2026, 1, 8, tzinfo=KST))
        report = evaluate([late_label_correction, daily(5, 60), original, daily(3, 40), correction, daily(1, 10)])
        result = report["series"][0]
        self.assertEqual((result["scored_days"], result["no_actual_days"], result["insufficient_history_days"]), (2, 1, 0))
        self.assertEqual(report["after_labels_as_of_rows"], 1)
        self.assertEqual(report["admitted_versions"], 5)
        self.assertEqual(
            [(p["trade_day"], p["actual_krw_per_kg"], p["latest_krw_per_kg"], p["moving_average_krw_per_kg"])
             for p in result["predictions"]],
            [("2026-01-03", 40, 30, 20), ("2026-01-05", 60, 40, 45)],
        )
        self.assertEqual(result["metrics"]["latest"]["mae_krw_per_kg"], 15)
        self.assertAlmostEqual(result["metrics"]["latest"]["rmse_krw_per_kg"], 250 ** 0.5)
        self.assertAlmostEqual(result["metrics"]["latest"]["wape_percent"], 30)
        self.assertAlmostEqual(result["metrics"]["latest"]["smape_percent"], (20 / 70 + 40 / 100) * 50)
        self.assertEqual(result["metrics"]["moving_average"]["mae_krw_per_kg"], 17.5)

    def test_trade_day_and_exact_cutoff_cannot_confer_availability(self):
        delayed = daily(2, 900, available=datetime.fromisoformat("2026-01-02T15:00:00+00:00"))
        same_target = daily(3, 1000, available=datetime(2026, 1, 3, tzinfo=KST))
        rows = [daily(1, 10), delayed, same_target, daily(4, 90)]
        result = evaluate(rows, end=4)["series"][0]
        self.assertEqual(result["insufficient_history_days"], 1)
        self.assertEqual(result["predictions"][0]["latest_krw_per_kg"], 1000)
        self.assertEqual(result["predictions"][0]["history_cutoff_exclusive"], "2026-01-04T00:00:00+09:00")
        longer = evaluate(rows, start=4, end=4, horizon_days=2)["series"][0]
        self.assertEqual(longer["insufficient_history_days"], 1)
        self.assertIsNone(longer["metrics"])

    def test_price_series_do_not_share_dimensions_or_raw_units(self):
        for field, value in (("provider", "other"), ("market", "02"), ("corporation", "101"),
                             ("product", "99"), ("origin", "99"), ("cultivar", "99"),
                             ("grade", "jam"), ("unit", "12:1:box")):
            with self.subTest(field=field):
                other = replace(SERIES, **{field: value})
                report = evaluate([daily(1, 20), daily(2, 90, series=other), daily(3, 25)], end=3)
                self.assertEqual(sorted(row["scored_days"] for row in report["series"]), [0, 0])
                self.assertEqual(sum(row["insufficient_history_days"] for row in report["series"]), 1)
                self.assertEqual(sum(row["no_actual_days"] for row in report["series"]), 1)

    def test_duplicates_and_conflicting_revisions_use_utc_identity(self):
        original = daily(1, 10)
        duplicate = replace(original, available_at=datetime.fromisoformat("2026-01-01T07:00:00+00:00"),
                            source_sha256="b" * 64)
        report = evaluate([original, duplicate, daily(2, 30), daily(3, 40)], end=3)
        self.assertEqual((report["input_rows"], report["duplicate_rows"], report["admitted_versions"]), (4, 1, 3))
        for changed in (replace(duplicate, price_krw_per_kg=90), replace(duplicate, trade_volume_kg=1)):
            with self.assertRaisesRegex(ValueError, "Conflicting price versions"):
                evaluate([original, changed])

    def test_label_revisions_are_scored_only_as_of_label_cutoff(self):
        corrected = daily(3, 80, available=datetime(2026, 1, 7, tzinfo=KST))
        report = evaluate([daily(1, 10), daily(2, 20), daily(3, 40), corrected], end=3)
        self.assertEqual(report["series"][0]["predictions"][0]["actual_krw_per_kg"], 80)

    def test_withdrawal_changes_history_only_after_availability_and_removes_label(self):
        withdrawn = replace(
            daily(3, 35), available_at=datetime(2026, 1, 5, tzinfo=KST),
            price_krw_per_kg=None, trade_volume_kg=None,
        )
        rows = [daily(1, 10), daily(2, 20), daily(3, 35), daily(4, 40), daily(5, 50), daily(6, 60), withdrawn]
        result = evaluate(rows, end=6)["series"][0]
        self.assertEqual((result["scored_days"], result["withdrawn_actual_days"]), (3, 1))
        self.assertEqual([p["moving_average_krw_per_kg"] for p in result["predictions"]], [27.5, 37.5, 45])
        restored = daily(3, 60, available=datetime(2026, 1, 5, 18, tzinfo=KST))
        report = evaluate([daily(1, 10), daily(2, 20), withdrawn, restored, daily(6, 80)], start=6, end=6)
        self.assertEqual(report["series"][0]["predictions"][0]["latest_krw_per_kg"], 60)

    def test_zero_total_actual_has_no_wape(self):
        report = evaluate([daily(1, 0), daily(2, 0), daily(3, 0)], end=3)
        metrics = report["series"][0]["metrics"]["latest"]
        self.assertEqual(metrics["smape_percent"], 0)
        self.assertIsNone(metrics["wape_percent"])

    def test_csv_preserves_exact_codes_and_requires_normalized_fields(self):
        row, = load_daily_prices(io.StringIO(HEADER + CSV_ROW + "\n"))
        self.assertEqual(row.series, SERIES)
        self.assertEqual((row.price_krw_per_kg, row.trade_volume_kg), (20.0, 70.0))
        withdrawn, = load_daily_prices(io.StringIO(HEADER + CSV_ROW.replace("TRADED,20,70,", "WITHDRAWN,,,")))
        self.assertIsNone(withdrawn.price_krw_per_kg)
        for header in (HEADER.replace("price_krw_per_kg", "price_per_box"), HEADER.replace("origin,", "")):
            with self.assertRaisesRegex(ValueError, "CSV fields"):
                load_daily_prices(io.StringIO(header + CSV_ROW))

    def test_csv_rejects_invalid_values_with_line_number(self):
        for row in (
            CSV_ROW.replace("+09:00", ""),
            CSV_ROW.replace("2026-01-01T", "2025-12-31T"),
            CSV_ROW.replace(",2026-01-01,", ",20260101,"),
            CSV_ROW.replace(",20,70,", ",NaN,70,"),
            CSV_ROW.replace(",20,70,", ",-20,70,"),
            CSV_ROW.replace(",20,70,", ",20,0,"),
            CSV_ROW.replace("TRADED,20,70,", "TRADED,,,"),
            CSV_ROW.replace("TRADED,20,70,", "WITHDRAWN,20,70,"),
            CSV_ROW.replace(",04,", ",,"),
            CSV_ROW[:-1],
            CSV_ROW + ",extra",
        ):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, "CSV line 2"):
                load_daily_prices(io.StringIO(HEADER + row))

    def test_holdout_must_finish_before_label_cutoff(self):
        with self.assertRaisesRegex(ValueError, "follow the full holdout"):
            evaluate([], labels_day=5)


if __name__ == "__main__":
    unittest.main()
