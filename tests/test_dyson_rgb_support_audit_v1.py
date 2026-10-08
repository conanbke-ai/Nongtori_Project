from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.dyson_rgb_support_audit_v1 import run_support_audit


class DysonRgbSupportAuditTests(unittest.TestCase):
    def test_support_overlap_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            with (snapshot / "fruit-splits.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["fruit_id","split","weight_with_calyx_g"])
                writer.writeheader()
                writer.writerows([
                    {"fruit_id":"a","split":"train","weight_with_calyx_g":"10"},
                    {"fruit_id":"b","split":"train","weight_with_calyx_g":"20"},
                    {"fruit_id":"c","split":"test","weight_with_calyx_g":"30"},
                ])

            predictions = root / "pred.csv"
            with predictions.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["berry_key","actual_weight_g","predicted_weight_g","view_count"])
                writer.writeheader()
                writer.writerows([
                    {"berry_key":"x","actual_weight_g":"5","predicted_weight_g":"6","view_count":"3"},
                    {"berry_key":"y","actual_weight_g":"15","predicted_weight_g":"12","view_count":"3"},
                    {"berry_key":"z","actual_weight_g":"25","predicted_weight_g":"14","view_count":"2"},
                ])

            report = run_support_audit(
                dryad_snapshot_dir=snapshot,
                dyson_predictions_csv=predictions,
                output_dir=root / "out",
            )

            self.assertEqual(report["status"], "DYSON_RGB_SUPPORT_AUDIT_COMPLETE")
            self.assertEqual(report["dryad_train_support"]["min_g"], 10)
            self.assertEqual(report["dryad_train_support"]["max_g"], 20)
            overlap = report["dyson_support_overlap"]
            self.assertEqual(overlap["below_train_min_count"], 1)
            self.assertEqual(overlap["in_train_support_count"], 1)
            self.assertEqual(overlap["above_train_max_count"], 1)
            self.assertEqual(report["error_by_support"]["above_train_max"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
