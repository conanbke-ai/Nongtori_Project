from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.geometry_v002 import (
    REGIME_STRICT_ONLY,
    REGIME_STRICT_PLUS_AUX,
    run_geometry_v002,
)


class GeometryV002Test(unittest.TestCase):
    def _write_split(self, path: Path) -> None:
        rows = [
            {"fruit_id": "0001", "split": "train", "weight_with_calyx_g": "10", "width_mm": "20", "height_mm": "30"},
            {"fruit_id": "0002", "split": "train", "weight_with_calyx_g": "12", "width_mm": "22", "height_mm": "31"},
            {"fruit_id": "0003", "split": "train", "weight_with_calyx_g": "16", "width_mm": "25", "height_mm": "34"},
            {"fruit_id": "0004", "split": "train", "weight_with_calyx_g": "20", "width_mm": "28", "height_mm": "36"},
            {"fruit_id": "0005", "split": "train", "weight_with_calyx_g": "24", "width_mm": "31", "height_mm": "39"},
            {"fruit_id": "0006", "split": "validation", "weight_with_calyx_g": "18", "width_mm": "27", "height_mm": "35"},
            {"fruit_id": "0007", "split": "test", "weight_with_calyx_g": "22", "width_mm": "30", "height_mm": "38"},
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def _write_aux(self, path: Path) -> None:
        rows = [
            {
                "fruit_id": "1001",
                "weight_with_calyx_g": "14",
                "width_mm": "23",
                "height_mm": "32",
                "variety": "A",
                "shape": "x",
                "photo": "NO",
                "source_sheet": "s",
                "role": "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            },
            {
                "fruit_id": "1002",
                "weight_with_calyx_g": "26",
                "width_mm": "33",
                "height_mm": "40",
                "variety": "A",
                "shape": "x",
                "photo": "NO",
                "source_sheet": "s",
                "role": "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            },
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def _write_cv(self, path: Path) -> None:
        rows = [
            {"fruit_id": "0001", "official_split": "train", "cv_fold": "0"},
            {"fruit_id": "0002", "official_split": "train", "cv_fold": "1"},
            {"fruit_id": "0003", "official_split": "train", "cv_fold": "2"},
            {"fruit_id": "0004", "official_split": "train", "cv_fold": "3"},
            {"fruit_id": "0005", "official_split": "train", "cv_fold": "4"},
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def test_runs_two_regimes_and_keeps_test_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            split = root / "split.csv"
            aux = root / "aux.csv"
            cv = root / "cv.csv"
            self._write_split(split)
            self._write_aux(aux)
            self._write_cv(cv)

            report = run_geometry_v002(split, aux, cv, root / "out")

            self.assertEqual(
                [item["regime"] for item in report["regime_candidates"]],
                [REGIME_STRICT_ONLY, REGIME_STRICT_PLUS_AUX],
            )
            self.assertEqual(report["official_counts"]["test_locked"], 1)
            self.assertEqual(report["test_policy"], "LOCKED_NOT_EVALUATED")
            self.assertFalse(report["test_predictions_written"])
            self.assertFalse((root / "out" / "test_predictions.csv").exists())

    def test_selection_does_not_use_official_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            split = root / "split.csv"
            aux = root / "aux.csv"
            cv = root / "cv.csv"
            self._write_split(split)
            self._write_aux(aux)
            self._write_cv(cv)

            first = run_geometry_v002(split, aux, cv, root / "a")

            rows = list(csv.DictReader(split.open(encoding="utf-8")))
            for row in rows:
                if row["split"] == "validation":
                    row["weight_with_calyx_g"] = "100"
            with split.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            second = run_geometry_v002(split, aux, cv, root / "b")

            self.assertEqual(first["selected_regime"], second["selected_regime"])
            self.assertFalse(
                first["official_validation_confirmation"][
                    "selection_uses_official_validation"
                ]
            )

    def test_auxiliary_overlap_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            split = root / "split.csv"
            aux = root / "aux.csv"
            cv = root / "cv.csv"
            self._write_split(split)
            self._write_aux(aux)
            self._write_cv(cv)

            rows = list(csv.DictReader(aux.open(encoding="utf-8")))
            rows[0]["fruit_id"] = "0001"
            with aux.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaises(ValueError):
                run_geometry_v002(split, aux, cv, root / "out")


if __name__ == "__main__":
    unittest.main()
