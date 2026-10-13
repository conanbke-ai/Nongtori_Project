from __future__ import annotations

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.mite_public_snapshot import _build_atomic_components, _is_valid_yolo_line


class MitePublicSnapshotTests(unittest.TestCase):
    def test_zero_width_bbox_is_excluded(self):
        ok, class_id = _is_valid_yolo_line("0 0.5 0.5 0 0.1")
        self.assertFalse(ok)
        self.assertEqual(class_id, 0)

    def test_valid_bbox_is_kept(self):
        ok, class_id = _is_valid_yolo_line("2 0.5 0.5 0.2 0.2")
        self.assertTrue(ok)
        self.assertEqual(class_id, 2)

    def test_origin_or_exact_hash_forms_one_atomic_component(self):
        rows = [
            {"image":"a.jpg","origin_key":"origin-a","image_sha256":"sha-a"},
            {"image":"b.jpg","origin_key":"origin-a","image_sha256":"sha-b"},
            {"image":"c.jpg","origin_key":"origin-c","image_sha256":"sha-b"},
            {"image":"d.jpg","origin_key":"origin-d","image_sha256":"sha-d"},
        ]
        groups = _build_atomic_components(rows)
        self.assertEqual(groups["a.jpg"], groups["b.jpg"])
        self.assertEqual(groups["b.jpg"], groups["c.jpg"])
        self.assertNotEqual(groups["a.jpg"], groups["d.jpg"])


if __name__ == "__main__":
    unittest.main()
