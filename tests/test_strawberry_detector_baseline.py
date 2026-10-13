from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ml.detector_baseline.fasterrcnn_v001 import (
    DetectorBaselineError,
    _ap_from_pr,
    _load_audit,
    _parse_yolo,
)


class StrawberryDetectorBaselineContractTests(unittest.TestCase):
    def test_parse_yolo_collapses_class_identity_outside_dataset_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_text(
                "5 0.5 0.5 0.2 0.4\n1 0.25 0.25 0.1 0.1\n",
                encoding="utf-8",
            )
            boxes = _parse_yolo(path, width=1000, height=500)
            self.assertEqual(len(boxes), 2)
            self.assertEqual(boxes[0], [400.0, 150.0, 600.0, 350.0])

    def test_parse_yolo_clamps_boundary_rounding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edge.txt"
            path.write_text(
                "0 0.2337760417 0.0208333333 0.0486979167 0.0416666667\n",
                encoding="utf-8",
            )
            boxes = _parse_yolo(path, width=1000, height=1000)
            self.assertEqual(len(boxes), 1)
            self.assertGreaterEqual(boxes[0][1], 0.0)

    def test_training_requires_ready_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.json"
            path.write_text(
                json.dumps({"status": "STRAWBERRY_DETECTOR_DATA_READY"}),
                encoding="utf-8",
            )
            payload = _load_audit(path)
            self.assertEqual(payload["status"], "STRAWBERRY_DETECTOR_DATA_READY")

            path.write_text(
                json.dumps({"status": "STRAWBERRY_DETECTOR_DATA_READY_WITH_EXCEPTIONS"}),
                encoding="utf-8",
            )
            with self.assertRaises(DetectorBaselineError):
                _load_audit(path)

    def test_ap_uses_interpolated_precision(self):
        ap = _ap_from_pr(
            recalls=[0.25, 0.50, 0.75, 1.0],
            precisions=[1.0, 0.8, 0.7, 0.5],
        )
        self.assertGreater(ap, 0.0)
        self.assertLessEqual(ap, 1.0)


if __name__ == "__main__":
    unittest.main()
