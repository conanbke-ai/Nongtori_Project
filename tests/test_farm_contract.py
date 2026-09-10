from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.farm_contract import CANONICAL_FARM_CODES, FARM_SCOPES, audit_farm_codes, resolve_farm_scope, validate_farm_code
from ml.data_pipeline.incremental import build_source_key
from ml.data_pipeline.normalize import LabelContractError, normalize_field_row
from ml.data_pipeline.rename_manifest import preflight_rename


class FarmContractTest(unittest.TestCase):
    def test_codes_and_scopes_are_separate(self):
        self.assertEqual(CANONICAL_FARM_CODES, frozenset({"M", "C1", "C2", "U"}))
        self.assertEqual(FARM_SCOPES, frozenset({"M", "C", "C1", "C2", "U"}))
        self.assertEqual(resolve_farm_scope("C"), frozenset({"C1", "C2"}))
        self.assertEqual(resolve_farm_scope("C1"), frozenset({"C1"}))
        with self.assertRaises(ValueError):
            validate_farm_code("C")

    def test_incremental_storage_key_keeps_actual_farm_code(self):
        self.assertEqual(build_source_key({"Farm": "C1", "ID": "0001"}), "C1:0001")
        with self.assertRaises(ValueError):
            build_source_key({"Farm": "C", "ID": "0001"})

    def test_field_normalize_keeps_actual_farm_code_contract(self):
        row = {"ID": "1", "Farm": "C", "Class": "STR", "Maturity": "3", "Grade": "SP", "Health": "NOR"}
        with self.assertRaises(LabelContractError):
            normalize_field_row(row)

    def test_field_audit_reports_c_when_stored_as_row_value(self):
        report = audit_farm_codes([
            {"ID": "1", "Farm": "M"}, {"ID": "2", "Farm": "C1"}, {"ID": "3", "Farm": "C2"},
            {"ID": "4", "Farm": "U"}, {"ID": "5", "Farm": "C"},
        ])
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["farm_counts"], {"C1": 1, "C2": 1, "M": 1, "U": 1})
        self.assertEqual(report["invalid_farm_rows"], [{"id": "5", "farm": "C"}])

    def test_rename_preflight_c_scope_selects_c1_and_c2(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "IMG_1.jpg").write_bytes(b"x")
            (source / "IMG_2.jpg").write_bytes(b"y")
            rows = [
                {"ID": "1", "Farm": "C1", "Original_No": "IMG_1", "Final_Name": "a.jpg", "Date": "2026-01-01", "Zone": "A", "DataType": "R"},
                {"ID": "2", "Farm": "C2", "Original_No": "IMG_2", "Final_Name": "b.jpg", "Date": "2026-01-01", "Zone": "B", "DataType": "R"},
                {"ID": "3", "Farm": "M", "Original_No": "IMG_3", "Final_Name": "c.jpg", "Date": "2026-01-01", "Zone": "C", "DataType": "R"},
            ]
            manifest, summary = preflight_rename(rows, source, farm_id="C", capture_session_id="S1")
            self.assertEqual(summary["status"], "PREFLIGHT_PASSED")
            self.assertEqual(summary["resolved_farm_codes"], ["C1", "C2"])
            self.assertEqual({row["farm_id"] for row in manifest}, {"C1", "C2"})


if __name__ == "__main__":
    unittest.main()
