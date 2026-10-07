from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.selective_grade_v001 import evaluate_selective_auto_grade


class SelectiveAutoGradeV001Test(unittest.TestCase):
    def _write(self, path: Path, rows: list[dict[str, str]]) -> None:
        fieldnames = [
            "fruit_id",
            "split",
            "actual_weight_g",
            "geometry_pred_g",
            "rgb_pred_g",
            "fusion_pred_g",
            "fusion_error_g",
            "fusion_abs_error_g",
            "actual_grade",
            "fusion_grade",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _rows(self, *, test_prediction: str = "50.0") -> list[dict[str, str]]:
        return [
            {
                "fruit_id": "V1", "split": "validation",
                "actual_weight_g": "14.0", "geometry_pred_g": "14",
                "rgb_pred_g": "14", "fusion_pred_g": "14.1",
                "fusion_error_g": "0.1", "fusion_abs_error_g": "0.1",
                "actual_grade": "MD_WEIGHT", "fusion_grade": "MD_WEIGHT",
            },
            {
                "fruit_id": "V2", "split": "validation",
                "actual_weight_g": "18.0", "geometry_pred_g": "18",
                "rgb_pred_g": "18", "fusion_pred_g": "18.2",
                "fusion_error_g": "0.2", "fusion_abs_error_g": "0.2",
                "actual_grade": "HI_WEIGHT", "fusion_grade": "HI_WEIGHT",
            },
            {
                "fruit_id": "V3", "split": "validation",
                "actual_weight_g": "21.9", "geometry_pred_g": "21.9",
                "rgb_pred_g": "22.1", "fusion_pred_g": "22.05",
                "fusion_error_g": "0.15", "fusion_abs_error_g": "0.15",
                "actual_grade": "HI_WEIGHT", "fusion_grade": "SP_WEIGHT",
            },
            {
                "fruit_id": "V4", "split": "validation",
                "actual_weight_g": "25.0", "geometry_pred_g": "25",
                "rgb_pred_g": "25", "fusion_pred_g": "25.1",
                "fusion_error_g": "0.1", "fusion_abs_error_g": "0.1",
                "actual_grade": "SP_WEIGHT", "fusion_grade": "SP_WEIGHT",
            },
            {
                "fruit_id": "T1", "split": "test",
                "actual_weight_g": "20.0", "geometry_pred_g": "20",
                "rgb_pred_g": test_prediction, "fusion_pred_g": test_prediction,
                "fusion_error_g": "0", "fusion_abs_error_g": "0",
                "actual_grade": "HI_WEIGHT", "fusion_grade": "HI_WEIGHT",
            },
        ]

    def test_selects_from_validation_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "fusion.csv"
            self._write(path, self._rows(test_prediction="1.0"))
            report_a = evaluate_selective_auto_grade(
                path,
                root / "a.json",
                target_observed_precision=1.0,
                minimum_auto_count=2,
                margins_g=(0.0, 0.5, 1.0),
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "fusion.csv"
            self._write(path, self._rows(test_prediction="100.0"))
            report_b = evaluate_selective_auto_grade(
                path,
                root / "b.json",
                target_observed_precision=1.0,
                minimum_auto_count=2,
                margins_g=(0.0, 0.5, 1.0),
            )

        self.assertEqual(report_a["selected_policy"], report_b["selected_policy"])
        self.assertEqual(report_a["test_policy"], "LOCKED_NOT_EVALUATED_FOR_SUCCESSOR_POLICY")
        self.assertEqual(report_a["test_rows_present_but_not_evaluated"], 1)

    def test_does_not_force_policy_when_precision_target_is_not_met(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "fusion.csv"
            rows = self._rows()
            for row in rows:
                if row["split"] == "validation":
                    row["fusion_pred_g"] = "16.1"
            self._write(path, rows)
            report = evaluate_selective_auto_grade(
                path,
                root / "out.json",
                target_observed_precision=1.0,
                minimum_auto_count=3,
                margins_g=(0.0, 0.5, 1.0),
            )
            self.assertEqual(report["status"], "SELECTIVE_AUTO_GRADE_TARGET_NOT_MET")
            self.assertIsNone(report["selected_policy"])

    def test_reports_precision_coverage_and_wilson_lower_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "fusion.csv"
            self._write(path, self._rows())
            report = evaluate_selective_auto_grade(
                path,
                root / "out.json",
                target_observed_precision=1.0,
                minimum_auto_count=2,
                margins_g=(0.0, 0.5, 1.0),
            )
            candidates = report["validation_candidates"]
            self.assertEqual(len(candidates), 3)
            for candidate in candidates:
                self.assertIn("coverage", candidate)
                self.assertIn("fallback_rate", candidate)
                self.assertIn("observed_precision", candidate)
                self.assertIn("precision_wilson_95_lower", candidate)


if __name__ == "__main__":
    unittest.main()
