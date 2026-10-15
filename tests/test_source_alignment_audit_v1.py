from __future__ import annotations

import json
import unittest
from pathlib import Path


class SourceAlignmentAuditV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            Path("configs/source-alignment-audit-v1.json").read_text(encoding="utf-8")
        )

    def test_pest_source_method_is_yolo11_large(self):
        pest = self.payload["domains"]["pest"]
        self.assertEqual(pest["source_alignment"], "NOT_SOURCE_ALIGNED")
        self.assertEqual(pest["source_method"]["model"], "YOLO11-Large")
        self.assertEqual(pest["source_method"]["epochs"], 100)
        self.assertEqual(pest["source_method"]["patience"], 25)

    def test_ripeness_requires_source_aligned_reproduction(self):
        ripeness = self.payload["domains"]["ripeness"]
        self.assertEqual(ripeness["existing_role"], "DEVELOPMENT_BENCHMARK_ONLY")
        models = {item["model"] for item in ripeness["source_methods"]}
        self.assertEqual(models, {"FasterRCNN-ResNet50-FPN", "DenseNet121"})

    def test_grade_12_16_22_is_hadong_field_policy_not_official_standard(self):
        grade = self.payload["domains"]["grade"]
        self.assertEqual(grade["current_internal_thresholds_g"], [12, 16, 22])
        self.assertEqual(
            grade["existing_role"],
            "FIELD_BUSINESS_GRADE_POLICY",
        )
        self.assertEqual(
            grade["source_alignment"],
            "FIELD_POLICY_SOURCE_CONFIRMED",
        )
        self.assertEqual(
            grade["field_policy_source"]["source_name"],
            "하동딸기 농협직판장 분류 기준",
        )
        self.assertEqual(
            grade["official_size_class_thresholds_g"],
            {"S": "<12", "M": "12-<17", "L": "17-<25", "2L": ">=25"},
        )
        self.assertNotEqual(
            grade["policy_separation"]["field_business_grade"],
            grade["policy_separation"]["official_size_class"],
        )


if __name__ == "__main__":
    unittest.main()
