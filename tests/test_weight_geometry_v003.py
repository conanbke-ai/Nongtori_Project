from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.geometry_v003 import (
    _build_sample_weights,
    run_geometry_v003,
)


class GeometryV003Test(unittest.TestCase):
    def _write_split(self, path: Path) -> None:
        rows = [
            {"fruit_id": "0001", "split": "train", "weight_with_calyx_g": "10", "width_mm": "20", "height_mm": "30"},
            {"fruit_id": "0002", "split": "train", "weight_with_calyx_g": "14", "width_mm": "23", "height_mm": "32"},
            {"fruit_id": "0003", "split": "train", "weight_with_calyx_g": "18", "width_mm": "27", "height_mm": "35"},
            {"fruit_id": "0004", "split": "train", "weight_with_calyx_g": "24", "width_mm": "32", "height_mm": "40"},
            {"fruit_id": "0005", "split": "train", "weight_with_calyx_g": "26", "width_mm": "34", "height_mm": "42"},
            {"fruit_id": "0006", "split": "validation", "weight_with_calyx_g": "20", "width_mm": "29", "height_mm": "37"},
            {"fruit_id": "0007", "split": "test", "weight_with_calyx_g": "22", "width_mm": "31", "height_mm": "39"},
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def _write_aux(self, path: Path) -> None:
        rows = [
            {
                "fruit_id": "1001",
                "weight_with_calyx_g": "11",
                "width_mm": "21",
                "height_mm": "31",
                "variety": "A",
                "shape": "x",
                "photo": "NO",
                "source_sheet": "s",
                "role": "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            },
            {
                "fruit_id": "1002",
                "weight_with_calyx_g": "15",
                "width_mm": "24",
                "height_mm": "33",
                "variety": "A",
                "shape": "x",
                "photo": "NO",
                "source_sheet": "s",
                "role": "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            },
            {
                "fruit_id": "1003",
                "weight_with_calyx_g": "19",
                "width_mm": "28",
                "height_mm": "36",
                "variety": "A",
                "shape": "x",
                "photo": "NO",
                "source_sheet": "s",
                "role": "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            },
            {
                "fruit_id": "1004",
                "weight_with_calyx_g": "23",
                "width_mm": "31",
                "height_mm": "39",
                "variety": "A",
                "shape": "x",
                "photo": "NO",
                "source_sheet": "s",
                "role": "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            },
            {
                "fruit_id": "1005",
                "weight_with_calyx_g": "27",
                "width_mm": "35",
                "height_mm": "43",
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

    def test_grade_matched_auxiliary_mass_tracks_strict_distribution(self):
        strict = [
            {"weight_with_calyx_g": 10, "width_mm": 20, "height_mm": 30},
            {"weight_with_calyx_g": 14, "width_mm": 23, "height_mm": 32},
            {"weight_with_calyx_g": 18, "width_mm": 27, "height_mm": 35},
            {"weight_with_calyx_g": 24, "width_mm": 32, "height_mm": 40},
        ]
        aux = [
            {"weight_with_calyx_g": 10, "width_mm": 20, "height_mm": 30},
            {"weight_with_calyx_g": 13, "width_mm": 22, "height_mm": 31},
            {"weight_with_calyx_g": 15, "width_mm": 24, "height_mm": 33},
            {"weight_with_calyx_g": 18, "width_mm": 27, "height_mm": 35},
            {"weight_with_calyx_g": 20, "width_mm": 29, "height_mm": 37},
            {"weight_with_calyx_g": 23, "width_mm": 31, "height_mm": 39},
            {"weight_with_calyx_g": 25, "width_mm": 33, "height_mm": 41},
        ]

        _, _, diagnostics = _build_sample_weights(
            strict,
            aux,
            auxiliary_effective_mass_ratio=0.5,
        )

        self.assertAlmostEqual(
            diagnostics["auxiliary_effective_total_weight"],
            2.0,
            places=9,
        )
        self.assertAlmostEqual(
            sum(diagnostics["auxiliary_effective_grade_mass"].values()),
            2.0,
            places=9,
        )

    def test_selection_is_independent_of_official_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            split = root / "split.csv"
            aux = root / "aux.csv"
            cv = root / "cv.csv"
            self._write_split(split)
            self._write_aux(aux)
            self._write_cv(cv)

            first = run_geometry_v003(split, aux, cv, root / "a")

            rows = list(csv.DictReader(split.open(encoding="utf-8")))
            for row in rows:
                if row["split"] == "validation":
                    row["weight_with_calyx_g"] = "100"
            with split.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            second = run_geometry_v003(split, aux, cv, root / "b")

            self.assertEqual(
                first["selected_candidate"],
                second["selected_candidate"],
            )
            self.assertFalse(
                first["official_validation_confirmation"][
                    "selection_uses_official_validation"
                ]
            )

    def test_test_split_stays_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            split = root / "split.csv"
            aux = root / "aux.csv"
            cv = root / "cv.csv"
            self._write_split(split)
            self._write_aux(aux)
            self._write_cv(cv)

            report = run_geometry_v003(split, aux, cv, root / "out")
            self.assertEqual(report["test_policy"], "LOCKED_NOT_EVALUATED")
            self.assertFalse(report["test_predictions_written"])
            self.assertFalse((root / "out" / "test_predictions.csv").exists())


if __name__ == "__main__":
    unittest.main()
