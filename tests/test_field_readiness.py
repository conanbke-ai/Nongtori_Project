from __future__ import annotations

import unittest

from ml.data_pipeline.field_readiness import classify_row, evaluate_rows


def base_str(**overrides):
    row = {
        "Date": "2026.01.06",
        "ID": "0001",
        "Group_ID": "0001",
        "Original_No": "20260106_090000",
        "Farm": "M",
        "Zone": "1동-1-A",
        "Variety": "Sulhyang",
        "Class": "STR",
        "DataType": "R",
        "View_Type": "RT45",
        "Occlusion": "0",
        "Maturity": "3",
        "Grade": "SP",
        "Final_Name": "SB_2026.01.06_M_STR_0001_3_SP_NOR_R.jpg",
    }
    row.update(overrides)
    return row


class FieldReadinessTest(unittest.TestCase):
    def test_valid_str_is_ready_metadata(self):
        result = classify_row(base_str(), 2)
        self.assertEqual(result["readiness"], "READY_METADATA")
        self.assertEqual(result["reason_codes"], [])

    def test_wip_missing_identity_is_partial(self):
        result = classify_row(base_str(ID="", Group_ID="", Original_No=""), 10)
        self.assertEqual(result["readiness"], "PARTIAL")
        self.assertTrue(any(code.startswith("MISSING_REQUIRED:") for code in result["reason_codes"]))

    def test_group_scope_c_is_invalid_stored_farm(self):
        result = classify_row(base_str(Farm="C"), 11)
        self.assertEqual(result["readiness"], "INVALID_FOR_TRAINING")
        self.assertIn("GROUP_SCOPE_C_NOT_STORED_FARM", result["reason_codes"])

    def test_out_of_range_maturity_is_invalid(self):
        result = classify_row(base_str(Maturity="5"), 12)
        self.assertEqual(result["readiness"], "INVALID_FOR_TRAINING")
        self.assertIn("INVALID_MATURITY:5", result["reason_codes"])

    def test_date_original_no_mismatch_is_warning_not_auto_fix(self):
        result = classify_row(base_str(Date="2026.01.05"), 13)
        self.assertEqual(result["readiness"], "READY_METADATA")
        self.assertIn("DATE_ORIGINAL_NO_TIMESTAMP_MISMATCH", result["warnings"])

    def test_leaf_does_not_require_maturity(self):
        row = base_str(Class="LEF", Maturity="", Grade="NA", Health="MIT_R")
        result = classify_row(row, 14)
        self.assertEqual(result["readiness"], "READY_METADATA")

    def test_duplicate_original_no_is_warned_on_all_rows(self):
        rows = [
            base_str(ID="0106", Group_ID="0046", Original_No="P1_260106_102747_887", Final_Name="a.jpg"),
            base_str(ID="0108", Group_ID="0047", Original_No="P1_260106_102747_887", Final_Name="b.jpg"),
        ]
        evaluated, summary = evaluate_rows(rows)
        for row in evaluated:
            self.assertIn("DUPLICATE_ORIGINAL_NO:P1_260106_102747_887", row["warnings"])
        self.assertEqual(summary["warning_counts"]["DUPLICATE_ORIGINAL_NO:P1_260106_102747_887"], 2)

    def test_duplicate_final_name_is_warned(self):
        rows = [
            base_str(ID="0201", Group_ID="0201", Original_No="20260106_100001", Final_Name="same.jpg"),
            base_str(ID="0202", Group_ID="0202", Original_No="20260106_100002", Final_Name="same.jpg"),
        ]
        evaluated, _ = evaluate_rows(rows)
        self.assertTrue(all("DUPLICATE_FINAL_NAME:same.jpg" in row["warnings"] for row in evaluated))


if __name__ == "__main__":
    unittest.main()
