from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.geometry_v001 import PRIMARY_MODEL, run_geometry_baseline


class GeometryWeightBaselineTest(unittest.TestCase):
    def _snapshot(self, root: Path, *, status: str = "WEIGHT_SNAPSHOT_FROZEN") -> Path:
        snapshot = root / "WEIGHT-DRYAD-V001"
        snapshot.mkdir()
        rows = [
            {"fruit_id": "T1", "split": "train", "weight_with_calyx_g": "10", "weight_without_calyx_g": "9", "width_mm": "20", "height_mm": "30", "variety": "x", "shape": "a"},
            {"fruit_id": "T2", "split": "train", "weight_with_calyx_g": "14", "weight_without_calyx_g": "13", "width_mm": "24", "height_mm": "32", "variety": "x", "shape": "a"},
            {"fruit_id": "T3", "split": "train", "weight_with_calyx_g": "18", "weight_without_calyx_g": "17", "width_mm": "28", "height_mm": "34", "variety": "x", "shape": "a"},
            {"fruit_id": "T4", "split": "train", "weight_with_calyx_g": "22", "weight_without_calyx_g": "21", "width_mm": "32", "height_mm": "36", "variety": "x", "shape": "a"},
            {"fruit_id": "V1", "split": "validation", "weight_with_calyx_g": "16", "weight_without_calyx_g": "15", "width_mm": "26", "height_mm": "33", "variety": "x", "shape": "a"},
            {"fruit_id": "E1", "split": "test", "weight_with_calyx_g": "20", "weight_without_calyx_g": "19", "width_mm": "30", "height_mm": "35", "variety": "x", "shape": "a"},
        ]
        with (snapshot / "fruit-splits.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        descriptor = {
            "snapshot_id": "WEIGHT-DRYAD-V001",
            "status": status,
            "split_group": "FRUIT_ID",
            "primary_target": "weight_with_calyx_g",
            "fruit_count": len(rows),
        }
        (snapshot / "WEIGHT_SNAPSHOT.json").write_text(
            json.dumps(descriptor),
            encoding="utf-8",
        )
        return snapshot

    def test_runs_fixed_geometry_models_without_test_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._snapshot(root)
            report = run_geometry_baseline(snapshot, root / "out")
            self.assertEqual(report["status"], "GEOMETRY_BASELINE_COMPLETE")
            self.assertEqual(report["primary_model"], PRIMARY_MODEL)
            self.assertEqual(
                report["selection_policy"],
                "PRIMARY_MODEL_PREDECLARED_NO_VALIDATION_SELECTION",
            )
            self.assertEqual(report["split_counts"], {"train": 4, "validation": 1, "test": 1})
            self.assertEqual(
                set(report["models"]),
                {"TRAIN_MEAN", "LINEAR_WIDTH_HEIGHT", "LINEAR_WIDTH_HEIGHT_AREA"},
            )
            self.assertTrue((root / "out" / "geometry_predictions.csv").exists())
            self.assertTrue((root / "out" / "geometry_baseline.json").exists())
            self.assertLess(
                report["models"][PRIMARY_MODEL]["metrics"]["train"]["mae_g"],
                report["models"]["TRAIN_MEAN"]["metrics"]["train"]["mae_g"],
            )

    def test_blocks_unfrozen_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._snapshot(root, status="PARTIAL")
            with self.assertRaisesRegex(ValueError, "not frozen"):
                run_geometry_baseline(snapshot, root / "out")

    def test_blocks_nonpositive_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._snapshot(root)
            split_path = snapshot / "fruit-splits.csv"
            with split_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["width_mm"] = "0"
            with split_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "geometry must be positive"):
                run_geometry_baseline(snapshot, root / "out")


if __name__ == "__main__":
    unittest.main()
