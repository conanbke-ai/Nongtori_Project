from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.annotation_audit import audit_kgcv_json, audit_strawberry_ds_yolo
from ml.data_pipeline.audit_expectations import verify_audit_expectation


class ExternalAnnotationAuditTest(unittest.TestCase):
    def test_strawberry_ds_yolo_classes_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n4 0.4 0.4 0.3 0.3\n", encoding="utf-8")
            report = audit_strawberry_ds_yolo(root)
            self.assertEqual(report["status"], "AUDITED")
            self.assertEqual(report["annotation_count"], 2)
            self.assertEqual(report["class_counts"]["Green"], 1)
            self.assertEqual(report["class_counts"]["Late-Turning"], 1)

    def test_kgcv_decimal_stage_is_audited_without_invented_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {
                "imagePath": "20230101_x.jpg",
                "shapes": [
                    {"label": "small g, 8.84, 7.62, 0.4"},
                    {"label": "turning red, 25.0, 30.0, 0.2"},
                    {"label": "turning red, 26.0, 31.0, 0.8"},
                    {"label": "overripe, 28.0, 34.0, 0.9"},
                ],
            }
            (root / "a.json").write_text(json.dumps(payload), encoding="utf-8")
            report = audit_kgcv_json(root)
            self.assertEqual(report["status"], "AUDITED")
            self.assertEqual(report["class_counts"]["turning red"], 2)
            self.assertEqual(report["decimal_stage_summary"]["turning red"]["min"], 0.2)
            self.assertEqual(report["decimal_stage_summary"]["turning red"]["max"], 0.8)
            self.assertEqual(report["turning_red_calibration"]["policy"], "DO_NOT_INVENT_THRESHOLD")
            self.assertEqual(report["turning_red_calibration"]["status"], "READY_FOR_EMPIRICAL_CALIBRATION")

    def test_kgcv_rejects_decimal_outside_zero_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.json").write_text(json.dumps({"shapes": [{"label": "turning red, 1, 1, 1.2"}]}), encoding="utf-8")
            report = audit_kgcv_json(root)
            self.assertEqual(report["status"], "REVIEW_REQUIRED")
            self.assertEqual(report["errors"][0]["error"], "DECIMAL_STAGE_OUT_OF_RANGE")

    def test_expectation_gate_detects_source_derivative_mismatch(self):
        expectation = {
            "expectation_id": "EXPECT-X-v1",
            "source_id": "DATA-RIP-001",
            "raw_audit_expectation": {
                "file_count_field": "label_files",
                "file_count": 247,
                "annotation_count": 1062,
                "class_counts": {"Green": 455},
            },
        }
        matching = {
            "source_id": "DATA-RIP-001",
            "label_files": 247,
            "annotation_count": 1062,
            "class_counts": {"Green": 455},
        }
        self.assertEqual(verify_audit_expectation(matching, expectation)["status"], "MATCH")
        derivative = dict(matching)
        derivative["annotation_count"] = 1083
        result = verify_audit_expectation(derivative, expectation)
        self.assertEqual(result["status"], "MISMATCH")
        self.assertEqual(result["mismatches"][0]["name"], "annotation_count")


if __name__ == "__main__":
    unittest.main()
