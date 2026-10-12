from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.strawberry_detector_data import prepare_strawberry_detector_data


class StrawberryDetectorDataTests(unittest.TestCase):
    def _write_pair(self, root: Path, key: str, label_text: str) -> None:
        image = root / "images" / f"{key}.jpg"
        label = root / "labels" / f"{key}.txt"
        image.parent.mkdir(parents=True, exist_ok=True)
        label.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"fake-image")
        label.write_text(label_text, encoding="utf-8")

    def test_collapses_ripeness_classes_to_single_detector_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_pair(
                root,
                "a",
                "0 0.5 0.5 0.2 0.2\n5 0.7 0.6 0.1 0.1\n",
            )
            report = prepare_strawberry_detector_data(
                source_root=root,
                audit_root=root / "audit",
                seed="test",
            )
            self.assertEqual(report["eligible_image_count"], 1)
            self.assertEqual(report["eligible_object_count"], 2)
            self.assertEqual(report["original_class_counts"], {"Green": 1, "Red": 1})
            with (root / "audit" / "detector-object-manifest.csv").open(
                encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["detector_class_name"] for row in rows}, {"strawberry"})
            self.assertEqual({row["detector_class_id"] for row in rows}, {"0"})

    def test_invalid_bbox_is_excluded_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_pair(root, "a", "2 0.95 0.5 0.2 0.2\n")
            report = prepare_strawberry_detector_data(
                source_root=root,
                audit_root=root / "audit",
            )
            self.assertEqual(report["eligible_image_count"], 0)
            self.assertEqual(report["parse_error_count"], 1)
            self.assertEqual(report["status"], "STRAWBERRY_DETECTOR_DATA_BLOCKED")

    def test_split_is_deterministic_and_image_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(20):
                self._write_pair(
                    root,
                    f"sample-{index:02d}",
                    "1 0.5 0.5 0.2 0.2\n3 0.4 0.4 0.1 0.1\n",
                )

            first = prepare_strawberry_detector_data(
                source_root=root,
                audit_root=root / "audit-a",
                seed="stable",
            )
            second = prepare_strawberry_detector_data(
                source_root=root,
                audit_root=root / "audit-b",
                seed="stable",
            )
            self.assertEqual(first["split_counts"], second["split_counts"])

            with (root / "audit-a" / "detector-object-manifest.csv").open(
                encoding="utf-8"
            ) as handle:
                objects = list(csv.DictReader(handle))
            by_image = {}
            for row in objects:
                by_image.setdefault(row["image_key"], set()).add(row["split"])
            self.assertTrue(all(len(splits) == 1 for splits in by_image.values()))

    def test_missing_pair_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "images").mkdir()
            (root / "images" / "lonely.jpg").write_bytes(b"x")
            report = prepare_strawberry_detector_data(
                source_root=root,
                audit_root=root / "audit",
            )
            self.assertEqual(report["missing_label_count"], 1)
            self.assertEqual(report["eligible_image_count"], 0)


if __name__ == "__main__":
    unittest.main()
