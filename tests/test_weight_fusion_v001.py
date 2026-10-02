from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.fusion_v001 import run_fusion


class WeightFusionV001Test(unittest.TestCase):
    def _write_geometry(self, path: Path, rows: list[dict[str, str]]) -> None:
        fieldnames = [
            "fruit_id",
            "split",
            "width_mm",
            "height_mm",
            "actual_weight_g",
            "train_mean_pred_g",
            "linear_width_height_pred_g",
            "linear_width_height_area_pred_g",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _write_rgb(self, path: Path, rows: list[dict[str, str]]) -> None:
        fieldnames = [
            "fruit_id",
            "split",
            "actual_weight_g",
            "predicted_weight_g",
            "view_count",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _fixture(self, root: Path, test_rgb_prediction: str) -> tuple[Path, Path]:
        geometry = root / "geometry.csv"
        rgb = root / "rgb.csv"
        geometry_rows = [
            {
                "fruit_id": "V1", "split": "validation",
                "width_mm": "1", "height_mm": "1", "actual_weight_g": "15.8",
                "train_mean_pred_g": "15.8", "linear_width_height_pred_g": "15.7",
                "linear_width_height_area_pred_g": "15.7",
            },
            {
                "fruit_id": "V2", "split": "validation",
                "width_mm": "1", "height_mm": "1", "actual_weight_g": "16.2",
                "train_mean_pred_g": "16.2", "linear_width_height_pred_g": "16.3",
                "linear_width_height_area_pred_g": "16.4",
            },
            {
                "fruit_id": "T1", "split": "test",
                "width_mm": "1", "height_mm": "1", "actual_weight_g": "20.0",
                "train_mean_pred_g": "20", "linear_width_height_pred_g": "20",
                "linear_width_height_area_pred_g": "20.0",
            },
            {
                "fruit_id": "R1", "split": "train",
                "width_mm": "1", "height_mm": "1", "actual_weight_g": "14.0",
                "train_mean_pred_g": "14", "linear_width_height_pred_g": "14",
                "linear_width_height_area_pred_g": "14.0",
            },
        ]
        rgb_rows = [
            {
                "fruit_id": "V1", "split": "validation",
                "actual_weight_g": "15.800000190734863",
                "predicted_weight_g": "15.9", "view_count": "22",
            },
            {
                "fruit_id": "V2", "split": "validation",
                "actual_weight_g": "16.200000762939453",
                "predicted_weight_g": "16.1", "view_count": "22",
            },
            {
                "fruit_id": "T1", "split": "test",
                "actual_weight_g": "20.0",
                "predicted_weight_g": test_rgb_prediction, "view_count": "22",
            },
            {
                "fruit_id": "R1", "split": "train",
                "actual_weight_g": "14.0",
                "predicted_weight_g": "14.0", "view_count": "22",
            },
        ]
        self._write_geometry(geometry, geometry_rows)
        self._write_rgb(rgb, rgb_rows)
        return geometry, rgb

    def test_selects_alpha_from_validation_and_reports_all_splits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry, rgb = self._fixture(root, "25.0")
            report = run_fusion(geometry, rgb, root / "fusion")
            self.assertEqual(report["status"], "WEIGHT_FUSION_V001_COMPLETE")
            self.assertEqual(report["selection_split"], "validation")
            self.assertIn(report["selected_alpha_rgb"], [i / 10 for i in range(11)])
            self.assertEqual(len(report["validation_candidates"]), 11)
            self.assertIn("train", report["metrics"])
            self.assertIn("validation", report["metrics"])
            self.assertIn("test", report["metrics"])

    def test_test_predictions_cannot_change_selected_alpha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry_a, rgb_a = self._fixture(root, "5.0")
            report_a = run_fusion(geometry_a, rgb_a, root / "fusion-a")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry_b, rgb_b = self._fixture(root, "50.0")
            report_b = run_fusion(geometry_b, rgb_b, root / "fusion-b")

        self.assertEqual(
            report_a["selected_alpha_rgb"],
            report_b["selected_alpha_rgb"],
        )
        self.assertEqual(
            report_a["validation_candidates"],
            report_b["validation_candidates"],
        )

    def test_existing_result_is_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry, rgb = self._fixture(root, "20.0")
            output = root / "fusion"
            run_fusion(geometry, rgb, output)
            with self.assertRaisesRegex(FileExistsError, "immutable fusion result"):
                run_fusion(geometry, rgb, output)


if __name__ == "__main__":
    unittest.main()
