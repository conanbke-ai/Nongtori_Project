from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.compare_v001 import compare_weight_predictions


class WeightPairedResidualAuditTest(unittest.TestCase):
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

    def test_paired_audit_reports_complementarity_and_boundary_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry = root / "geometry.csv"
            rgb = root / "rgb.csv"

            self._write_geometry(
                geometry,
                [
                    {
                        "fruit_id": "A",
                        "split": "test",
                        "width_mm": "30",
                        "height_mm": "30",
                        "actual_weight_g": "11.8",
                        "train_mean_pred_g": "12.0",
                        "linear_width_height_pred_g": "12.2",
                        "linear_width_height_area_pred_g": "12.5",
                    },
                    {
                        "fruit_id": "B",
                        "split": "test",
                        "width_mm": "31",
                        "height_mm": "31",
                        "actual_weight_g": "16.2",
                        "train_mean_pred_g": "16.0",
                        "linear_width_height_pred_g": "16.1",
                        "linear_width_height_area_pred_g": "16.4",
                    },
                    {
                        "fruit_id": "C",
                        "split": "validation",
                        "width_mm": "32",
                        "height_mm": "32",
                        "actual_weight_g": "21.9",
                        "train_mean_pred_g": "21.8",
                        "linear_width_height_pred_g": "21.7",
                        "linear_width_height_area_pred_g": "21.5",
                    },
                ],
            )
            self._write_rgb(
                rgb,
                [
                    {
                        "fruit_id": "A",
                        "split": "test",
                        "actual_weight_g": "11.8",
                        "predicted_weight_g": "11.7",
                        "view_count": "22",
                    },
                    {
                        "fruit_id": "B",
                        "split": "test",
                        "actual_weight_g": "16.2",
                        "predicted_weight_g": "15.8",
                        "view_count": "22",
                    },
                    {
                        "fruit_id": "C",
                        "split": "validation",
                        "actual_weight_g": "21.9",
                        "predicted_weight_g": "22.2",
                        "view_count": "22",
                    },
                ],
            )

            out_json = root / "paired.json"
            out_csv = root / "paired.csv"
            report = compare_weight_predictions(
                geometry,
                rgb,
                out_json,
                out_csv,
            )

            test_report = report["splits"]["test"]
            self.assertEqual(
                test_report["paired"]["rgb_resolved_geometry_grade_error_count"],
                1,
            )
            self.assertEqual(
                test_report["paired"]["rgb_introduced_grade_error_count"],
                1,
            )
            self.assertEqual(
                test_report["paired"]["geometry_crossings_resolved_by_rgb"],
                1,
            )
            self.assertEqual(
                test_report["paired"]["rgb_crossings_introduced_vs_geometry"],
                1,
            )
            self.assertEqual(
                test_report["paired"]["rgb_better_abs_error_count"],
                1,
            )
            self.assertEqual(
                test_report["paired"]["geometry_better_abs_error_count"],
                1,
            )
            self.assertTrue(out_json.exists())
            self.assertTrue(out_csv.exists())

    def test_blocks_mismatched_fruit_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry = root / "geometry.csv"
            rgb = root / "rgb.csv"
            self._write_geometry(
                geometry,
                [{
                    "fruit_id": "A",
                    "split": "test",
                    "width_mm": "1",
                    "height_mm": "1",
                    "actual_weight_g": "12",
                    "train_mean_pred_g": "12",
                    "linear_width_height_pred_g": "12",
                    "linear_width_height_area_pred_g": "12",
                }],
            )
            self._write_rgb(
                rgb,
                [{
                    "fruit_id": "B",
                    "split": "test",
                    "actual_weight_g": "12",
                    "predicted_weight_g": "12",
                    "view_count": "22",
                }],
            )
            with self.assertRaisesRegex(ValueError, "fruit_id sets differ"):
                compare_weight_predictions(
                    geometry,
                    rgb,
                    root / "out.json",
                    root / "out.csv",
                )

    def test_allows_float32_roundtrip_target_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry = root / "geometry.csv"
            rgb = root / "rgb.csv"
            self._write_geometry(
                geometry,
                [{
                    "fruit_id": "A",
                    "split": "test",
                    "width_mm": "1",
                    "height_mm": "1",
                    "actual_weight_g": "21.28",
                    "train_mean_pred_g": "21",
                    "linear_width_height_pred_g": "21",
                    "linear_width_height_area_pred_g": "21",
                }],
            )
            self._write_rgb(
                rgb,
                [{
                    "fruit_id": "A",
                    "split": "test",
                    "actual_weight_g": "21.280000686645508",
                    "predicted_weight_g": "21.1",
                    "view_count": "22",
                }],
            )
            report = compare_weight_predictions(
                geometry,
                rgb,
                root / "out.json",
                root / "out.csv",
            )
            self.assertEqual(report["status"], "WEIGHT_PAIRED_RESIDUAL_AUDIT_COMPLETE")
            self.assertEqual(
                report["target_alignment_policy"],
                "GEOMETRY_SNAPSHOT_GT_CANONICAL_RGB_FLOAT32_ROUNDTRIP_TOLERATED",
            )

    def test_blocks_actual_weight_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry = root / "geometry.csv"
            rgb = root / "rgb.csv"
            self._write_geometry(
                geometry,
                [{
                    "fruit_id": "A",
                    "split": "test",
                    "width_mm": "1",
                    "height_mm": "1",
                    "actual_weight_g": "12.0",
                    "train_mean_pred_g": "12",
                    "linear_width_height_pred_g": "12",
                    "linear_width_height_area_pred_g": "12",
                }],
            )
            self._write_rgb(
                rgb,
                [{
                    "fruit_id": "A",
                    "split": "test",
                    "actual_weight_g": "12.1",
                    "predicted_weight_g": "12",
                    "view_count": "22",
                }],
            )
            with self.assertRaisesRegex(ValueError, "actual_weight_g mismatch"):
                compare_weight_predictions(
                    geometry,
                    rgb,
                    root / "out.json",
                    root / "out.csv",
                )


if __name__ == "__main__":
    unittest.main()
