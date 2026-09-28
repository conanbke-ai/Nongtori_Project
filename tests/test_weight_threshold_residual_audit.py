from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.audit_thresholds_v001 import audit_threshold_residuals


class WeightThresholdResidualAuditTest(unittest.TestCase):
    def test_detects_grade_boundary_crossings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            predictions = root / "geometry_predictions.csv"
            rows = [
                {
                    "fruit_id": "A",
                    "split": "validation",
                    "width_mm": "1",
                    "height_mm": "1",
                    "actual_weight_g": "11.8",
                    "train_mean_pred_g": "12.5",
                    "linear_width_height_pred_g": "12.4",
                    "linear_width_height_area_pred_g": "12.6",
                },
                {
                    "fruit_id": "B",
                    "split": "validation",
                    "width_mm": "1",
                    "height_mm": "1",
                    "actual_weight_g": "16.2",
                    "train_mean_pred_g": "15.9",
                    "linear_width_height_pred_g": "15.8",
                    "linear_width_height_area_pred_g": "15.5",
                },
                {
                    "fruit_id": "C",
                    "split": "test",
                    "width_mm": "1",
                    "height_mm": "1",
                    "actual_weight_g": "23.0",
                    "train_mean_pred_g": "23.1",
                    "linear_width_height_pred_g": "23.2",
                    "linear_width_height_area_pred_g": "23.4",
                },
                {
                    "fruit_id": "D",
                    "split": "train",
                    "width_mm": "1",
                    "height_mm": "1",
                    "actual_weight_g": "14.0",
                    "train_mean_pred_g": "14.1",
                    "linear_width_height_pred_g": "14.2",
                    "linear_width_height_area_pred_g": "14.3",
                },
            ]
            with predictions.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

            output = root / "audit.json"
            report = audit_threshold_residuals(predictions, output)
            self.assertEqual(report["status"], "WEIGHT_THRESHOLD_RESIDUAL_AUDIT_COMPLETE")
            self.assertEqual(report["splits"]["validation"]["grade_error_count"], 2)
            self.assertEqual(report["splits"]["validation"]["threshold_crossing_counts"]["12"], 1)
            self.assertEqual(report["splits"]["validation"]["threshold_crossing_counts"]["16"], 1)
            self.assertEqual(report["splits"]["test"]["grade_error_count"], 0)
            self.assertTrue(output.exists())
            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(persisted["policy"], "ANALYZE_ONLY_NO_THRESHOLD_TUNING")

    def test_blocks_missing_prediction_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            predictions = root / "geometry_predictions.csv"
            with predictions.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["fruit_id", "split", "actual_weight_g"])
                writer.writeheader()
                writer.writerow({"fruit_id": "A", "split": "test", "actual_weight_g": "12"})
            with self.assertRaisesRegex(ValueError, "prediction column missing"):
                audit_threshold_residuals(predictions, root / "out.json")


if __name__ == "__main__":
    unittest.main()
