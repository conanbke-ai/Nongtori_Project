import unittest

from ml.data_pipeline.kgcv_quality_audit import (
    build_report,
    inspect_measurement_manifest,
    summarize_kgcv_quality_rows,
)


class KgcvQualityAuditTests(unittest.TestCase):
    def test_hf_rows_expose_dimensions_but_not_weight(self):
        rows = [
            {
                "row_idx": 0,
                "row": {
                    "objects": {
                        "categories": [1, 3],
                        "diameter": [25.1, 31.2],
                        "length": [34.5, 42.8],
                        "decimal_stage": [0.1, 1.0],
                    }
                },
            }
        ]
        report = summarize_kgcv_quality_rows(rows)
        self.assertEqual(report["status"], "AUDITED")
        self.assertEqual(report["availability"]["diameter"], 2)
        self.assertEqual(report["availability"]["length"], 2)
        self.assertEqual(report["availability"]["weight"], 0)
        self.assertEqual(report["weight_join_status"], "WEIGHT_JOIN_AUDIT_REQUIRED")
        self.assertEqual(report["grade_policy"]["thresholds_g"], {"SP": 22.0, "HI": 16.0, "MD": 12.0})
        self.assertEqual(report["grade_policy"]["model_target"], "WEIGHT_REGRESSION_THEN_POLICY")

    def test_parallel_object_arrays_are_required(self):
        rows = [{
            "row_idx": 7,
            "row": {"objects": {
                "categories": [1, 3],
                "diameter": [25.1],
                "length": [34.5, 42.8],
                "decimal_stage": [0.1, 1.0],
            }},
        }]
        report = summarize_kgcv_quality_rows(rows)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["errors"][0]["error"], "OBJECT_ARRAY_LENGTH_MISMATCH")

    def test_measurement_files_do_not_imply_verified_join(self):
        manifest = inspect_measurement_manifest([
            "data_taggedFruit_diameter_2023.csv",
            "data_taggedFruit_length_2023.csv",
            "data_taggedFruit_freshMatter_2023.csv",
        ])
        self.assertTrue(manifest["has_weight_measurements"])
        self.assertFalse(manifest["join_key_verified"])
        self.assertEqual(manifest["status"], "WEIGHT_JOIN_AUDIT_REQUIRED")

    def test_build_report_never_marks_weight_training_ready_without_join_evidence(self):
        rows = [{
            "row_idx": 1,
            "row": {"objects": {
                "categories": [1],
                "diameter": [20.0],
                "length": [30.0],
                "decimal_stage": [0.1],
            }},
        }]
        report = build_report(rows, ["data_taggedFruit_freshMatter_2023.csv"])
        self.assertTrue(report["decision"]["dimension_baseline_ready"])
        self.assertFalse(report["decision"]["weight_training_ready"])
        self.assertIn("fruit_identity_join_key", report["decision"]["next_required_evidence"])


if __name__ == "__main__":
    unittest.main()
