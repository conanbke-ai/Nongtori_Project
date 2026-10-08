from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.dyson_rgb_domain_shift_audit_v1 import run_domain_shift_audit


class DysonRgbDomainShiftAuditTests(unittest.TestCase):
    def test_distribution_and_band_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            with (snapshot / "fruit-splits.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["fruit_id","split","weight_with_calyx_g"])
                writer.writeheader()
                writer.writerows([
                    {"fruit_id":"a","split":"test","weight_with_calyx_g":"10"},
                    {"fruit_id":"b","split":"test","weight_with_calyx_g":"14"},
                    {"fruit_id":"c","split":"test","weight_with_calyx_g":"18"},
                    {"fruit_id":"d","split":"test","weight_with_calyx_g":"24"},
                ])

            predictions = root / "pred.csv"
            with predictions.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["berry_key","actual_weight_g","predicted_weight_g","view_count"])
                writer.writeheader()
                writer.writerows([
                    {"berry_key":"x","actual_weight_g":"8","predicted_weight_g":"6","view_count":"3"},
                    {"berry_key":"y","actual_weight_g":"20","predicted_weight_g":"15","view_count":"3"},
                    {"berry_key":"z","actual_weight_g":"30","predicted_weight_g":"20","view_count":"2"},
                ])

            report = run_domain_shift_audit(
                dryad_snapshot_dir=snapshot,
                dyson_predictions_csv=predictions,
                output_dir=root / "out",
            )

            self.assertEqual(report["status"], "DYSON_RGB_DOMAIN_SHIFT_AUDIT_COMPLETE")
            self.assertEqual(report["dryad_test_distribution"]["count"], 4)
            self.assertEqual(report["dyson_distribution"]["count"], 3)
            self.assertGreaterEqual(report["distribution_shift"]["grade_total_variation"], 0.0)
            self.assertEqual(report["dyson_model_metrics"]["count"], 3)
            bands = {row["band"]: row for row in report["dyson_actual_weight_bands"]}
            self.assertEqual(bands["LT_12G"]["count"], 1)
            self.assertEqual(bands["16_TO_LT_22G"]["count"], 1)
            self.assertEqual(bands["GE_22G"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
