from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.geometry_cohort_compatibility_audit_v1 import (
    _integrity_check_auxiliary,
    audit_geometry_cohort_compatibility,
)


class GeometryCohortCompatibilityAuditV1Test(unittest.TestCase):
    def _write_official(self, path: Path) -> None:
        rows = [
            {"fruit_id": "0001", "split": "train"},
            {"fruit_id": "0002", "split": "train"},
            {"fruit_id": "0003", "split": "validation"},
            {"fruit_id": "0004", "split": "test"},
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def _write_aux(self, path: Path, *, mutate_weight: bool = False) -> None:
        rows = [
            {
                "fruit_id": "1001",
                "weight_with_calyx_g": "24.0" if not mutate_weight else "23.0",
                "width_mm": "34.0",
                "height_mm": "44.0",
                "variety": "A",
                "source_sheet": "S1",
                "photo": "NO",
                "role": "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            },
            {
                "fruit_id": "1002",
                "weight_with_calyx_g": "16.0",
                "width_mm": "28.0",
                "height_mm": "36.0",
                "variety": "B",
                "source_sheet": "S2",
                "photo": "NO",
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
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def _records(self):
        return {
            "0001": {
                "fruit_id": "0001",
                "weight_with_calyx_g": 12.0,
                "width_mm": 22.0,
                "height_mm": 31.0,
                "variety": "A",
                "source_sheet": "S1",
                "photo": "YES",
            },
            "0002": {
                "fruit_id": "0002",
                "weight_with_calyx_g": 20.0,
                "width_mm": 30.0,
                "height_mm": 39.0,
                "variety": "B",
                "source_sheet": "S2",
                "photo": "YES",
            },
            "0003": {
                "fruit_id": "0003",
                "weight_with_calyx_g": 18.0,
                "width_mm": 28.0,
                "height_mm": 37.0,
                "variety": "A",
                "source_sheet": "S1",
                "photo": "YES",
            },
            "0004": {
                "fruit_id": "0004",
                "weight_with_calyx_g": 22.0,
                "width_mm": 31.0,
                "height_mm": 40.0,
                "variety": "B",
                "source_sheet": "S2",
                "photo": "YES",
            },
            "1001": {
                "fruit_id": "1001",
                "weight_with_calyx_g": 24.0,
                "width_mm": 34.0,
                "height_mm": 44.0,
                "variety": "A",
                "source_sheet": "S1",
                "photo": "NO",
            },
            "1002": {
                "fruit_id": "1002",
                "weight_with_calyx_g": 16.0,
                "width_mm": 28.0,
                "height_mm": 36.0,
                "variety": "B",
                "source_sheet": "S2",
                "photo": "NO",
            },
        }

    def test_auxiliary_integrity_rejects_modified_source_weight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            aux = root / "aux.csv"
            self._write_aux(aux, mutate_weight=True)
            rows = list(csv.DictReader(aux.open(encoding="utf-8")))

            with self.assertRaises(ValueError):
                _integrity_check_auxiliary(
                    rows,
                    self._records(),
                    {"0001", "0002", "0003", "0004"},
                )

    def test_validation_and_test_are_locked_from_statistics(self):
        import ml.weight_baseline.geometry_cohort_compatibility_audit_v1 as mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            official = root / "official.csv"
            aux = root / "aux.csv"
            cv = root / "cv.csv"
            self._write_official(official)
            self._write_aux(aux)
            self._write_cv(cv)

            original_loader = mod.primary_weight_records_from_datasheet
            try:
                mod.primary_weight_records_from_datasheet = lambda _: self._records()
                report = audit_geometry_cohort_compatibility(
                    root / "unused.xlsx",
                    official,
                    aux,
                    cv,
                    root / "out.json",
                )
            finally:
                mod.primary_weight_records_from_datasheet = original_loader

            self.assertEqual(
                report["official_counts"]["train_used_for_compatibility"], 2
            )
            self.assertEqual(report["official_counts"]["validation_locked"], 1)
            self.assertEqual(report["official_counts"]["test_locked"], 1)
            self.assertFalse(
                report["leakage_guards"][
                    "official_validation_used_for_statistics"
                ]
            )
            self.assertFalse(
                report["leakage_guards"]["official_test_used_for_statistics"]
            )
            self.assertFalse(
                report["leakage_guards"]["source_weight_values_modified"]
            )
            self.assertEqual(
                report["decision_gate"]["geometry_v003_policy"],
                "HOLD_PENDING_MANUAL_COMPATIBILITY_REVIEW",
            )

    def test_overlap_is_rejected(self):
        records = self._records()
        aux_rows = [
            {
                "fruit_id": "0001",
                "weight_with_calyx_g": "12.0",
                "width_mm": "22.0",
                "height_mm": "31.0",
                "variety": "A",
                "source_sheet": "S1",
                "photo": "YES",
                "role": "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            }
        ]
        with self.assertRaises(ValueError):
            _integrity_check_auxiliary(
                aux_rows,
                records,
                {"0001", "0002", "0003", "0004"},
            )


if __name__ == "__main__":
    unittest.main()
