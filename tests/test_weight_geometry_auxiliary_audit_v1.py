from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.geometry_auxiliary_audit_v1 import (
    audit_geometry_auxiliary_candidates,
)


class GeometryAuxiliaryAuditV1Test(unittest.TestCase):
    def _write_split(self, path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["fruit_id", "split"])
            writer.writeheader()
            writer.writerows(
                [
                    {"fruit_id": "0001", "split": "train"},
                    {"fruit_id": "0002", "split": "validation"},
                    {"fruit_id": "0003", "split": "test"},
                ]
            )

    def test_auxiliary_pool_excludes_strict_cohort_and_preserves_holdouts(self):
        records = {
            "0001": {"fruit_id": "0001", "weight_with_calyx_g": 15.0, "width_mm": 30.0, "height_mm": 35.0},
            "0002": {"fruit_id": "0002", "weight_with_calyx_g": 17.0, "width_mm": 31.0, "height_mm": 36.0},
            "0003": {"fruit_id": "0003", "weight_with_calyx_g": 23.0, "width_mm": 32.0, "height_mm": 37.0},
            "0004": {"fruit_id": "0004", "weight_with_calyx_g": 11.0, "width_mm": 28.0, "height_mm": 33.0, "photo": "NO"},
            "0005": {"fruit_id": "0005", "weight_with_calyx_g": 19.0, "width_mm": 29.0, "height_mm": 34.0, "photo": "NO"},
            "0006": {"fruit_id": "0006", "weight_with_calyx_g": 21.0, "width_mm": None, "height_mm": 34.0},
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            split_csv = root / "fruit-splits.csv"
            self._write_split(split_csv)

            report = audit_geometry_auxiliary_candidates(
                root / "unused.xlsx",
                split_csv,
                root / "out",
                weight_loader=lambda _: records,
            )

            self.assertEqual(report["strict_rgb_weight_count"], 3)
            self.assertEqual(report["auxiliary_geometry_train_candidate_count"], 2)
            self.assertEqual(
                report["official_split_counts"],
                {"train": 1, "validation": 1, "test": 1},
            )
            self.assertTrue(
                report["leakage_guards"]["official_validation_membership_unchanged"]
            )
            self.assertTrue(
                report["leakage_guards"]["official_test_membership_unchanged"]
            )

            with Path(report["candidate_csv"]).open(
                encoding="utf-8", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["fruit_id"] for row in rows}, {"0004", "0005"})
            self.assertTrue(
                all(
                    row["role"] == "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE"
                    for row in rows
                )
            )

    def test_blocks_when_strict_fruit_is_missing_from_weight_records(self):
        records = {
            "0001": {"fruit_id": "0001", "weight_with_calyx_g": 15.0, "width_mm": 30.0, "height_mm": 35.0},
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            split_csv = root / "fruit-splits.csv"
            self._write_split(split_csv)

            with self.assertRaises(ValueError):
                audit_geometry_auxiliary_candidates(
                    root / "unused.xlsx",
                    split_csv,
                    root / "out",
                    weight_loader=lambda _: records,
                )


if __name__ == "__main__":
    unittest.main()
