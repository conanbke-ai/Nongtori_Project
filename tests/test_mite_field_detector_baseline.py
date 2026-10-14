from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ml.detector_baseline.mite_field_v001 import (
    CLASS_NAMES,
    MITE_LABEL,
    _iou,
    _parse_yolo_multiclass,
)


class MiteFieldDetectorBaselineTests(unittest.TestCase):
    def test_class_contract(self):
        self.assertEqual(CLASS_NAMES[0], "Tetranychus Urticae")
        self.assertEqual(MITE_LABEL, 1)

    def test_parse_yolo_maps_zero_based_source_to_one_based_detector_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "label.txt"
            path.write_text(
                "0 0.5 0.5 0.2 0.2\n3 0.25 0.25 0.1 0.1\n",
                encoding="utf-8",
            )
            boxes, labels = _parse_yolo_multiclass(path, 100, 200)
            self.assertEqual(labels, [1, 4])
            self.assertEqual(len(boxes), 2)
            self.assertEqual(boxes[0], [40.0, 80.0, 60.0, 120.0])

    def test_iou(self):
        self.assertAlmostEqual(_iou([0, 0, 10, 10], [0, 0, 10, 10]), 1.0)
        self.assertEqual(_iou([0, 0, 1, 1], [2, 2, 3, 3]), 0.0)

    def test_degenerate_bbox_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "label.txt"
            path.write_text("0 0.5 0.5 0 0.1\n", encoding="utf-8")
            with self.assertRaises(Exception):
                _parse_yolo_multiclass(path, 100, 100)


if __name__ == "__main__":
    unittest.main()
