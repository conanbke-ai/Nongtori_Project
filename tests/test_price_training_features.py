import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from datetime import date, datetime, time
from pathlib import Path
from tempfile import TemporaryDirectory

from ml.price_forecast import features
from ml.price_forecast.baseline import SERIES_FIELDS
from ml.price_forecast.incremental_planner import KST


LABELS_AS_OF = datetime(2026, 1, 10, tzinfo=KST)
CSV_FIELDS = (
    *SERIES_FIELDS, "trade_day", "available_at", "status", "price_krw_per_kg", "trade_volume_kg", "source_sha256"
)
SERIES = {
    "provider": "test",
    "market": "001",
    "corporation": "002",
    "product": "003",
    "origin": "004",
    "cultivar": "005",
    "grade": "006",
    "unit": "kg|2|box",
}


def daily_row(day, *, available=None, status="TRADED", price=10, **series):
    trade_day = date(2026, 1, day)
    return {
        **SERIES,
        **series,
        "trade_day": trade_day.isoformat(),
        "available_at": (available or datetime.combine(trade_day, time(18), KST)).isoformat(),
        "status": status,
        "price_krw_per_kg": price if status == "TRADED" else "",
        "trade_volume_kg": 5 if status == "TRADED" else "",
        "source_sha256": "a" * 64,
    }


class PriceTrainingContractTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.path = self.work / "prices.csv"

    def freeze(self, *rows):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        payload = buffer.getvalue().encode()
        self.path.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()

    def test_training_input_preserves_codes_and_uses_fixed_bytes(self):
        digest = self.freeze(daily_row(2), daily_row(1))
        rows = features.load_training_prices(self.path, digest, LABELS_AS_OF)
        self.assertEqual([row.trade_day.day for row in rows], [1, 2])
        self.assertEqual(rows[0].series.market, "001")
        self.path.write_bytes(self.path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            features.load_training_prices(self.path, digest, LABELS_AS_OF)

    def test_training_rejects_late_and_unavailable_versions(self):
        cases = [
            (daily_row(1, available=datetime(2026, 1, 2, tzinfo=KST)), "KST trade day"),
            (daily_row(10), "open or unavailable"),
            (daily_row(9, available=LABELS_AS_OF), "KST trade day"),
        ]
        for row, error in cases:
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, error):
                features.load_training_prices(self.path, self.freeze(row), LABELS_AS_OF)
        with self.assertRaisesRegex(ValueError, "UTC offset"):
            features.load_training_prices(self.path, self.freeze(daily_row(1)), datetime(2026, 1, 10))

    def test_training_rejects_revisions_and_withdrawals(self):
        revision = daily_row(1, available=datetime(2026, 1, 1, 20, tzinfo=KST), price=30)
        for rows in ((daily_row(1), revision), (daily_row(1, status="WITHDRAWN"),)):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "one non-withdrawn version"):
                features.load_training_prices(self.path, self.freeze(*rows), LABELS_AS_OF)

    def test_untouched_holdout_is_after_selection_validation(self):
        digest = self.freeze(*(daily_row(day) for day in range(1, 9)))
        rows = features.load_training_prices(self.path, digest, LABELS_AS_OF)
        split = features.split_training_prices(rows, validation_days=2, holdout_days=2)
        self.assertEqual((split.train_end.day, split.validation_end.day, split.holdout_end.day), (4, 6, 8))
        self.assertEqual((split.train_rows, split.validation_rows, split.holdout_rows), (4, 2, 2))
        with self.assertRaisesRegex(ValueError, "each have rows"):
            features.split_training_prices(rows, validation_days=7, holdout_days=2)

    def test_tft_requires_actual_target_on_each_date_in_each_series(self):
        digest = self.freeze(daily_row(1), daily_row(3), daily_row(2, origin="999"))
        rows = features.load_training_prices(self.path, digest, LABELS_AS_OF)
        with self.assertRaisesRegex(ValueError, "contiguous trade dates"):
            features.validate_tft_history(rows)
        digest = self.freeze(daily_row(1), daily_row(2), daily_row(6, origin="999"), daily_row(7, origin="999"))
        features.validate_tft_history(features.load_training_prices(self.path, digest, LABELS_AS_OF))

    def test_feature_allowlists_separate_raw_data_calendar_and_past_prices(self):
        raw = {"available_at", "source_sha256", "trade_volume_kg", "temperature_mean_c", "is_holiday", "future_price"}
        self.assertTrue(raw.isdisjoint(features.CATBOOST_FEATURES))
        self.assertTrue(raw.isdisjoint(features.TFT_KNOWN_REALS))
        self.assertNotIn(features.TARGET_COLUMN, features.CATBOOST_FEATURES)
        self.assertNotIn(features.TARGET_COLUMN, features.TFT_KNOWN_REALS)
        self.assertEqual(features.TFT_UNKNOWN_REALS, (features.TARGET_COLUMN,))
        self.assertEqual(features.TFT_KNOWN_REALS, ("time_idx", *features.CALENDAR_FEATURES))
        self.assertEqual(features.CATBOOST_FEATURES[:len(SERIES_FIELDS)], SERIES_FIELDS)

    @unittest.skipUnless(importlib.util.find_spec("pandas"), "pandas feature runtime unavailable")
    def test_catboost_frame_uses_prior_same_series_observations_only(self):
        digest = self.freeze(daily_row(3, price=9000), daily_row(1, price=10), daily_row(2, price=20),
                             daily_row(1, price=1000, origin="999"), daily_row(3, price=2000, origin="999"))
        rows = features.load_training_prices(self.path, digest, LABELS_AS_OF)
        frame = features.add_lag_features(features.training_price_frame(rows))
        score = frame[(frame[features.DATE_COLUMN].dt.day == 3) & (frame["origin"] == "004")].iloc[0]
        self.assertEqual(score["price_lag_1"], 20)
        self.assertEqual(score["price_lag_2"], 10)
        self.assertEqual(score["price_roll_mean_3"], 15)
        self.assertEqual(set(frame) - {features.TARGET_COLUMN, features.DATE_COLUMN}, set(features.CATBOOST_FEATURES))

    @unittest.skipUnless(importlib.util.find_spec("yaml"), "PyYAML config runtime unavailable")
    def test_default_candidate_entrypoints_validate_without_training(self):
        digest = self.freeze(*(daily_row(day) for day in range(1, 7)))
        config = self.work / "config.yaml"
        config.write_text("validation:\n  selection_days: 2\n  holdout_days: 2\n", encoding="utf-8")
        for candidate in ("train_catboost", "train_tft"):
            with self.subTest(candidate=candidate):
                result = subprocess.run(
                    [sys.executable, "-m", f"ml.price_forecast.{candidate}", "--data", str(self.path),
                     "--input-sha256", digest, "--labels-as-of", LABELS_AS_OF.isoformat(),
                     "--config", str(config)],
                    check=True, capture_output=True, text=True,
                )
                evidence = json.loads(result.stdout)
                self.assertEqual(evidence["status"], "INPUT_VALIDATED")
                self.assertEqual(evidence["holdout_rows_excluded"], 2)


if __name__ == "__main__":
    unittest.main()
