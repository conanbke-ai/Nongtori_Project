from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.dyson_annotation_join import (
    annotation_path_from_rgb,
    audit_dyson_annotation_join,
)
from ml.data_pipeline.dyson_weight_reference import DATASET_ROLE


class DysonAnnotationJoinAuditTests(unittest.TestCase):
    def _write_snapshot(self, root: Path, rows: list[dict[str, str]]) -> Path:
        snapshot = root / "snapshot"
        snapshot.mkdir()
        descriptor = {
            "status": "DYSON_REFERENCE_SNAPSHOT_FROZEN",
            "dataset_role": DATASET_ROLE,
            "commercial_training_ready": False,
            "strict_berry_count": len(rows),
        }
        (snapshot / "REFERENCE_SNAPSHOT.json").write_text(
            json.dumps(descriptor),
            encoding="utf-8",
        )

        fieldnames = [
            "berry_key",
            "scene_id",
            "berry_instance_id",
            "view_1_rgb_path",
            "view_1_x",
            "view_1_y",
            "view_2_rgb_path",
            "view_2_x",
            "view_2_y",
            "view_3_rgb_path",
            "view_3_x",
            "view_3_y",
            "dataset_role",
            "commercial_training_ready",
        ]
        with (snapshot / "physical-berry-manifest.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return snapshot

    def _berry(
        self,
        *,
        berry_instance_id: str = "1",
        x: str = "20",
        y: str = "30",
        rgb: str = "extracted/1/1/003/strawberry_dyson_lincoln_tbd__003_1_rgb.png",
    ) -> dict[str, str]:
        return {
            "berry_key": f"scene#berry-{berry_instance_id}",
            "scene_id": "scene",
            "berry_instance_id": berry_instance_id,
            "view_1_rgb_path": rgb,
            "view_1_x": x,
            "view_1_y": y,
            "view_2_rgb_path": "",
            "view_2_x": "",
            "view_2_y": "",
            "view_3_rgb_path": "",
            "view_3_x": "",
            "view_3_y": "",
            "dataset_role": DATASET_ROLE,
            "commercial_training_ready": "False",
        }

    def _write_annotation(
        self,
        annotation_root: Path,
        annotations: list[dict],
        *,
        scene: str = "003",
        view: int = 1,
    ) -> Path:
        path = (
            annotation_root
            / "dyson_annotations"
            / "1"
            / scene
            / f"strawberry_dyson_lincoln_tbd__{scene}_{view}_keypoint.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"annotations": annotations}),
            encoding="utf-8",
        )
        return path

    def test_path_mapping_is_partition_aware(self):
        annotation_root = Path("annotations")
        first = annotation_path_from_rgb(
            "extracted/1/1/003/strawberry_dyson_lincoln_tbd__003_2_rgb.png",
            annotation_root,
        )
        second = annotation_path_from_rgb(
            "extracted/4/4/003/strawberry_dyson_lincoln_tbd__003_2_rgb.png",
            annotation_root,
        )

        self.assertEqual(
            first.as_posix(),
            "annotations/dyson_annotations/1/003/strawberry_dyson_lincoln_tbd__003_2_keypoint.json",
        )
        self.assertEqual(
            second.as_posix(),
            "annotations/dyson_annotations/4/003/strawberry_dyson_lincoln_tbd__003_2_keypoint.json",
        )
        self.assertNotEqual(first, second)

    def test_unique_center_in_bbox_is_joined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root, [self._berry()])
            annotation_root = root / "annotations"
            audit_root = root / "audit"
            self._write_annotation(
                annotation_root,
                [
                    {
                        "bbox": [10.0, 20.0, 40.0, 50.0],
                        "bbox_mode": 0,
                        "category_id": 1,
                        "segmentation": [[10, 20, 40, 20, 40, 50, 10, 50]],
                    },
                    {
                        "bbox": [100.0, 100.0, 130.0, 140.0],
                        "bbox_mode": 0,
                        "category_id": 0,
                        "segmentation": [],
                    },
                ],
            )

            report = audit_dyson_annotation_join(
                snapshot_dir=snapshot,
                annotation_root=annotation_root,
                audit_root=audit_root,
            )
            rows = list(
                csv.DictReader(
                    (audit_root / "berry-annotation-join.csv").open(encoding="utf-8")
                )
            )

            self.assertEqual(report["unique_geometric_match_count"], 1)
            self.assertEqual(report["unique_annotation_object_count"], 2)
            self.assertEqual(rows[0]["join_status"], "UNIQUE_GEOMETRIC_MATCH")
            self.assertEqual(rows[0]["annotation_index"], "0")
            self.assertEqual(rows[0]["category_id"], "1")
            self.assertFalse(report["commercial_training_ready"])

    def test_annotation_index_is_not_berry_instance_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(
                root,
                [self._berry(berry_instance_id="99", x="115", y="115")],
            )
            annotation_root = root / "annotations"
            audit_root = root / "audit"
            self._write_annotation(
                annotation_root,
                [
                    {"bbox": [0, 0, 20, 20], "bbox_mode": 0, "category_id": 0},
                    {"bbox": [100, 100, 130, 130], "bbox_mode": 0, "category_id": 1},
                ],
            )

            audit_dyson_annotation_join(
                snapshot_dir=snapshot,
                annotation_root=annotation_root,
                audit_root=audit_root,
            )
            row = next(
                csv.DictReader(
                    (audit_root / "berry-annotation-join.csv").open(encoding="utf-8")
                )
            )

            self.assertEqual(row["berry_instance_id"], "99")
            self.assertEqual(row["annotation_index"], "1")
            self.assertEqual(row["join_status"], "UNIQUE_GEOMETRIC_MATCH")

    def test_zero_hit_is_not_forced_to_nearest_bbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root, [self._berry(x="90", y="90")])
            annotation_root = root / "annotations"
            audit_root = root / "audit"
            self._write_annotation(
                annotation_root,
                [{"bbox": [10, 20, 40, 50], "bbox_mode": 0, "category_id": 1}],
            )

            report = audit_dyson_annotation_join(
                snapshot_dir=snapshot,
                annotation_root=annotation_root,
                audit_root=audit_root,
            )
            row = next(
                csv.DictReader(
                    (audit_root / "berry-annotation-join.csv").open(encoding="utf-8")
                )
            )

            self.assertEqual(report["no_object_match_count"], 1)
            self.assertEqual(row["join_status"], "NO_OBJECT_MATCH")
            self.assertEqual(row["annotation_index"], "")

    def test_overlapping_boxes_are_ambiguous_and_unselected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root, [self._berry()])
            annotation_root = root / "annotations"
            audit_root = root / "audit"
            self._write_annotation(
                annotation_root,
                [
                    {"bbox": [10, 20, 40, 50], "bbox_mode": 0, "category_id": 0},
                    {"bbox": [15, 25, 45, 55], "bbox_mode": 0, "category_id": 1},
                ],
            )

            report = audit_dyson_annotation_join(
                snapshot_dir=snapshot,
                annotation_root=annotation_root,
                audit_root=audit_root,
            )
            row = next(
                csv.DictReader(
                    (audit_root / "berry-annotation-join.csv").open(encoding="utf-8")
                )
            )

            self.assertEqual(report["ambiguous_match_count"], 1)
            self.assertEqual(row["join_status"], "AMBIGUOUS_MATCH")
            self.assertEqual(row["candidate_hit_count"], "2")
            self.assertEqual(row["annotation_index"], "")
            self.assertEqual(row["category_id"], "")

    def test_missing_json_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root, [self._berry()])
            audit_root = root / "audit"

            report = audit_dyson_annotation_join(
                snapshot_dir=snapshot,
                annotation_root=root / "annotations",
                audit_root=audit_root,
            )

            self.assertEqual(report["no_annotation_image_count"], 1)
            self.assertEqual(report["annotation_file_resolved_count"], 0)

    def test_invalid_bbox_is_reported_when_file_has_no_valid_bbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root, [self._berry()])
            annotation_root = root / "annotations"
            audit_root = root / "audit"
            self._write_annotation(
                annotation_root,
                [{"bbox": [10, 20, 10, 50], "bbox_mode": 0, "category_id": 1}],
            )

            report = audit_dyson_annotation_join(
                snapshot_dir=snapshot,
                annotation_root=annotation_root,
                audit_root=audit_root,
            )

            self.assertEqual(report["invalid_bbox_count"], 1)
            self.assertEqual(report["unique_invalid_bbox_object_count"], 1)

    def test_schema_counts_are_unique_per_json_not_per_berry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(
                root,
                [
                    self._berry(berry_instance_id="1", x="20", y="30"),
                    self._berry(berry_instance_id="2", x="110", y="110"),
                ],
            )
            annotation_root = root / "annotations"
            audit_root = root / "audit"
            self._write_annotation(
                annotation_root,
                [
                    {"bbox": [10, 20, 40, 50], "bbox_mode": 0, "category_id": 0},
                    {"bbox": [100, 100, 130, 130], "bbox_mode": 0, "category_id": 1},
                ],
            )

            report = audit_dyson_annotation_join(
                snapshot_dir=snapshot,
                annotation_root=annotation_root,
                audit_root=audit_root,
            )

            self.assertEqual(report["unique_annotation_json_count"], 1)
            self.assertEqual(report["unique_annotation_object_count"], 2)
            self.assertEqual(report["bbox_mode_counts"], {"0": 2})
            self.assertEqual(report["category_id_counts"], {"0": 1, "1": 1})

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root, [self._berry()])
            annotation_root = root / "annotations"
            audit_a = root / "audit-a"
            audit_b = root / "audit-b"
            self._write_annotation(
                annotation_root,
                [{"bbox": [10, 20, 40, 50], "bbox_mode": 0, "category_id": 1}],
            )

            first = audit_dyson_annotation_join(
                snapshot_dir=snapshot,
                annotation_root=annotation_root,
                audit_root=audit_a,
            )
            second = audit_dyson_annotation_join(
                snapshot_dir=snapshot,
                annotation_root=annotation_root,
                audit_root=audit_b,
            )

            self.assertEqual(
                (audit_a / "berry-annotation-join.csv").read_bytes(),
                (audit_b / "berry-annotation-join.csv").read_bytes(),
            )
            for payload in (first, second):
                payload["artifacts"] = {}
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
