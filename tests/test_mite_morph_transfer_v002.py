from __future__ import annotations

import unittest

from ml.detector_baseline.mite_morph_transfer_v002 import (
    EXPECTED_FIELD_BOXES,
    EXPECTED_FIELD_SPLIT,
    EXPECTED_MORPH_BOXES,
    EXPECTED_MORPH_SPLIT,
    FIELD_SNAPSHOT_ID,
    MORPH_CLASS_NAMES,
    MORPH_SNAPSHOT_ID,
    V001_VALIDATION_REFERENCE,
    transferable_state_dict,
)


class MiteMorphologyTransferV002Tests(unittest.TestCase):
    def test_snapshot_contracts_are_frozen(self):
        self.assertEqual(MORPH_SNAPSHOT_ID, "MITE-PUBLIC-MORPHOLOGY-V001")
        self.assertEqual(FIELD_SNAPSHOT_ID, "MITE-PUBLIC-FIELD-CONTEXT-V001")
        self.assertEqual(EXPECTED_MORPH_SPLIT, {"train": 854, "validation": 203, "test": 192})
        self.assertEqual(EXPECTED_FIELD_SPLIT, {"train": 1993, "validation": 427, "test": 424})
        self.assertEqual(EXPECTED_MORPH_BOXES, 17364)
        self.assertEqual(EXPECTED_FIELD_BOXES, 9179)

    def test_morphology_classes_are_exact_v210_contract(self):
        self.assertEqual(MORPH_CLASS_NAMES, ["Adult_female", "Immature", "Viable_egg"])

    def test_transfer_excludes_only_class_specific_predictor(self):
        state = {
            "backbone.body.0.weight": object(),
            "rpn.head.cls_logits.weight": object(),
            "roi_heads.box_head.fc6.weight": object(),
            "roi_heads.box_predictor.cls_score.weight": object(),
            "roi_heads.box_predictor.bbox_pred.weight": object(),
        }
        filtered = transferable_state_dict(state)
        self.assertIn("backbone.body.0.weight", filtered)
        self.assertIn("rpn.head.cls_logits.weight", filtered)
        self.assertIn("roi_heads.box_head.fc6.weight", filtered)
        self.assertNotIn("roi_heads.box_predictor.cls_score.weight", filtered)
        self.assertNotIn("roi_heads.box_predictor.bbox_pred.weight", filtered)

    def test_v001_reference_is_validation_only(self):
        self.assertEqual(V001_VALIDATION_REFERENCE["mite_map50_95"], 0.6840)
        self.assertNotIn("test", V001_VALIDATION_REFERENCE)


if __name__ == "__main__":
    unittest.main()
