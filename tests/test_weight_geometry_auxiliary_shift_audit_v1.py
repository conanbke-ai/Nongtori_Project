from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.geometry_auxiliary_shift_audit_v1 import (
    audit_geometry_auxiliary_shift,
)


class GeometryAuxiliaryShiftAuditV1Test(unittest.TestCase):
    def _write_official(self, path: Path) -> None:
        rows = [
            {"fruit_id":"0001","split":"train","weight_with_calyx_g":"10","width_mm":"20","height_mm":"30"},
            {"fruit_id":"0002","split":"train","weight_with_calyx_g":"20","width_mm":"30","height_mm":"40"},
            {"fruit_id":"0003","split":"validation","weight_with_calyx_g":"15","width_mm":"25","height_mm":"35"},
            {"fruit_id":"0004","split":"test","weight_with_calyx_g":"25","width_mm":"35","height_mm":"45"},
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer=csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader(); writer.writerows(rows)

    def _write_aux(self, path: Path, overlap: bool=False) -> None:
        rows = [
            {
                "fruit_id":"0001" if overlap else "1001",
                "weight_with_calyx_g":"24",
                "width_mm":"34",
                "height_mm":"44",
                "variety":"A",
                "source_sheet":"S1",
                "photo":"NO",
                "role":"AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            },
            {
                "fruit_id":"1002",
                "weight_with_calyx_g":"26",
                "width_mm":"36",
                "height_mm":"46",
                "variety":"B",
                "source_sheet":"S2",
                "photo":"NO",
                "role":"AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            },
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer=csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader(); writer.writerows(rows)

    def test_uses_official_train_only_for_shift_statistics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            official=root/"official.csv"; aux=root/"aux.csv"
            self._write_official(official); self._write_aux(aux)

            report=audit_geometry_auxiliary_shift(
                official, aux, root/"out.json"
            )

            self.assertEqual(report["official_counts"]["train"], 2)
            self.assertEqual(report["official_counts"]["validation_locked"], 1)
            self.assertEqual(report["official_counts"]["test_locked"], 1)
            self.assertEqual(report["strict_train"]["numeric"]["weight_with_calyx_g"]["count"], 2)
            self.assertFalse(report["leakage_guards"]["official_validation_read_for_statistics"])
            self.assertFalse(report["leakage_guards"]["official_test_read_for_statistics"])

    def test_detects_distribution_shift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            official=root/"official.csv"; aux=root/"aux.csv"
            self._write_official(official); self._write_aux(aux)

            report=audit_geometry_auxiliary_shift(
                official, aux, root/"out.json"
            )

            self.assertGreater(
                report["shift_summary"]["grade_distribution_total_variation"], 0
            )
            self.assertGreater(
                report["shift_summary"]["aux_minus_strict_numeric_means"]["weight_with_calyx_g"],
                0,
            )

    def test_rejects_strict_auxiliary_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            official=root/"official.csv"; aux=root/"aux.csv"
            self._write_official(official); self._write_aux(aux, overlap=True)

            with self.assertRaises(ValueError):
                audit_geometry_auxiliary_shift(
                    official, aux, root/"out.json"
                )


if __name__ == "__main__":
    unittest.main()
