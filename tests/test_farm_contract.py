from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.farm_contract import CANONICAL_FARM_CODES, audit_farm_codes, validate_farm_code
from ml.data_pipeline.incremental import build_source_key
from ml.data_pipeline.normalize import LabelContractError, normalize_field_row
from ml.data_pipeline.rename_manifest import preflight_rename


class FarmContractTest(unittest.TestCase):
    def test_canonical_codes_are_exact(self):
        self.assertEqual(CANONICAL_FARM_CODES, frozenset({"M", "C1", "C2", "U"}))
        for code in ("M", "C1", "C2", "U"):
            self.assertEqual(validate_farm_code(code), code)
        with self.assertRaises(ValueError):
            validate_farm_code("C")

    def test_incremental_key_rejects_noncanonical_c(self):
        self.assertEqual(build_source_key({"Farm": "C1", "ID": "0001"}), "C1:0001")
        with self.assertRaises(ValueError):
            build_source_key({"Farm": "C", "ID": "0001"})

    def test_field_normalize_rejects_noncanonical_c(self):
        row = {"ID": "1", "Farm": "C", "Class": "STR", "Maturity": "3", "Grade": "SP", "Health": "NOR"}
        with self.assertRaises(LabelContractError):
            normalize_field_row(row)

    def test_field_audit_reports_invalid_farm(self):
        report = audit_farm_codes([
            {"ID": "1", "Farm": "M"},
            {"ID": "2", "Farm": "C1"},
            {"ID": "3", "Farm": "C2"},
            {"ID": "4", "Farm": "U"},
            {"ID": "5", "Farm": "C"},
        ])
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["farm_counts"], {"C1": 1, "C2": 1, "M": 1, "U": 1})
        self.assertEqual(report["invalid_farm_rows"], [{"id": "5", "farm": "C"}])

    def test_rename_preflight_rejects_parent_folder_c_as_farm(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "IMG_1.jpg").write_bytes(b"x")
            rows = [{"ID": "1", "Farm": "C1", "Original_No": "IMG_1", "Final_Name": "a.jpg"}]
            with self.assertRaises(ValueError):
                preflight_rename(rows, source, farm_id="C", capture_session_id="S1")


if __name__ == "__main__":
    unittest.main()
