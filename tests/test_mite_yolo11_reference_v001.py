from __future__ import annotations

import unittest

from ml.detector_baseline.mite_yolo11_reference_v001 import (
    CLASS_NAMES,
    EXPECTED_BOXES,
    EXPECTED_SPLIT,
    SNAPSHOT_ID,
    SOURCE_CONTRACT,
)


class MiteYolo11ReferenceV001Tests(unittest.TestCase):
    def test_source_contract_matches_mitevision_v210(self):
        self.assertEqual(SOURCE_CONTRACT["architecture"], "YOLO11-Large")
        self.assertEqual(SOURCE_CONTRACT["weights"], "yolo11l.pt")
        self.assertEqual(SOURCE_CONTRACT["epochs"], 100)
        self.assertEqual(SOURCE_CONTRACT["patience"], 25)
        self.assertEqual(SOURCE_CONTRACT["imgsz"], 1024)
        self.assertEqual(SOURCE_CONTRACT["batch"], 16)
        self.assertEqual(SOURCE_CONTRACT["seed"], 42)
        self.assertTrue(SOURCE_CONTRACT["synthetic_data"])

    def test_snapshot_contract_is_leakage_safe_morphology_v001(self):
        self.assertEqual(SNAPSHOT_ID, "MITE-PUBLIC-MORPHOLOGY-V001")
        self.assertEqual(
            EXPECTED_SPLIT,
            {"train": 854, "validation": 203, "test": 192},
        )
        self.assertEqual(EXPECTED_BOXES, 17364)

    def test_class_contract_matches_v210(self):
        self.assertEqual(
            CLASS_NAMES,
            ["Adult_female", "Immature", "Viable_egg"],
        )


if __name__ == "__main__":
    unittest.main()
