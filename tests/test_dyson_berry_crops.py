from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ml.data_pipeline.dyson_berry_crops import materialize_dyson_berry_crops
from ml.data_pipeline.dyson_weight_reference import DATASET_ROLE


class DysonBerryCropMaterializationTests(unittest.TestCase):
    def _write_snapshot(self, root: Path) -> Path:
        snapshot = root / "snapshot"
        snapshot.mkdir()
        (snapshot / "REFERENCE_SNAPSHOT.json").write_text(
            json.dumps({
                "status": "DYSON_REFERENCE_SNAPSHOT_FROZEN",
                "dataset_role": DATASET_ROLE,
                "commercial_training_ready": False,
                "strict_berry_count": 1,
            }),
            encoding="utf-8",
        )
        with (snapshot / "physical-berry-manifest.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "berry_key","weight_g","dimension_1","dimension_2","dimension_3",
                    "dataset_role","commercial_training_ready",
                ],
            )
            writer.writeheader()
            writer.writerow({
                "berry_key":"scene#berry-1",
                "weight_g":"12.5",
                "dimension_1":"30",
                "dimension_2":"25",
                "dimension_3":"20",
                "dataset_role":DATASET_ROLE,
                "commercial_training_ready":"False",
            })
        return snapshot

    def _write_join(self, root: Path, status: str = "UNIQUE_GEOMETRIC_MATCH") -> Path:
        audit = root / "join"
        audit.mkdir()
        rows = [{
            "berry_key":"scene#berry-1",
            "scene_id":"extracted/1/1/003/strawberry_dyson_lincoln_tbd__003",
            "berry_instance_id":"1",
            "view_index":"1",
            "rgb_path":"extracted/1/1/003/sample_1_rgb.png",
            "source_center_x":"20",
            "source_center_y":"30",
            "bbox_x1":"10.5",
            "bbox_y1":"20.5",
            "bbox_x2":"40.5",
            "bbox_y2":"50.5",
            "bbox_mode":"0",
            "category_id":"1",
            "join_status":status,
            "dataset_role":DATASET_ROLE,
            "commercial_training_ready":"False",
        }]
        with (audit / "berry-annotation-join.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        (audit / "berry-annotation-join-audit.json").write_text(
            json.dumps({
                "status":"DYSON_ANNOTATION_JOIN_AUDIT_COMPLETE_WITH_EXCEPTIONS",
                "dataset_role":DATASET_ROLE,
                "commercial_training_ready":False,
                "expected_berry_view_count":1,
                "unique_geometric_match_count":1 if status == "UNIQUE_GEOMETRIC_MATCH" else 0,
            }),
            encoding="utf-8",
        )
        return audit

    def test_materializes_only_unique_matches_with_deterministic_pixel_box(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root)
            join = self._write_join(root)
            raw = root / "raw"
            source = raw / "extracted" / "1" / "1" / "003" / "sample_1_rgb.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"rgb")
            out = root / "out"
            audit = root / "crop-audit"

            seen = {}
            def fake_writer(source_path, output_path, pixel_box):
                seen["box"] = pixel_box
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"crop")
                return (100, 100)

            report = materialize_dyson_berry_crops(
                snapshot_dir=snapshot,
                raw_root=raw,
                join_audit_root=join,
                output_root=out,
                audit_root=audit,
                crop_writer=fake_writer,
            )

            self.assertEqual(seen["box"], (10, 20, 41, 51))
            self.assertEqual(report["eligible_unique_join_count"], 1)
            self.assertEqual(report["materialized_count"], 1)
            self.assertEqual(report["successful_crop_count"], 1)
            self.assertEqual(report["status"], "DYSON_BERRY_CROPS_MATERIALIZED")

            with (audit / "berry-crop-manifest.csv").open(encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["weight_g"], "12.5")
            self.assertEqual(row["crop_width"], "31")
            self.assertEqual(row["crop_height"], "31")
            self.assertEqual(row["materialization_status"], "MATERIALIZED")
            self.assertEqual(row["dataset_role"], DATASET_ROLE)
            self.assertEqual(row["commercial_training_ready"], "False")

    def test_non_unique_join_is_excluded_and_writer_not_called(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root)
            join = self._write_join(root, status="AMBIGUOUS_MATCH")

            report = materialize_dyson_berry_crops(
                snapshot_dir=snapshot,
                raw_root=root / "raw",
                join_audit_root=join,
                output_root=root / "out",
                audit_root=root / "audit",
                crop_writer=mock.Mock(side_effect=AssertionError("writer must not run")),
            )

            self.assertEqual(report["eligible_unique_join_count"], 0)
            self.assertEqual(report["excluded_non_unique_join_count"], 1)
            self.assertEqual(report["successful_crop_count"], 0)

    def test_missing_source_is_reported_without_fabrication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root)
            join = self._write_join(root)

            report = materialize_dyson_berry_crops(
                snapshot_dir=snapshot,
                raw_root=root / "raw",
                join_audit_root=join,
                output_root=root / "out",
                audit_root=root / "audit",
                crop_writer=mock.Mock(side_effect=AssertionError("writer must not run")),
            )

            self.assertEqual(report["source_rgb_missing_count"], 1)
            self.assertEqual(report["successful_crop_count"], 0)
            self.assertEqual(report["status"], "DYSON_BERRY_CROPS_MATERIALIZED_WITH_EXCEPTIONS")

    def test_out_of_bounds_is_reported_and_not_clamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root)
            join = self._write_join(root)
            raw = root / "raw"
            source = raw / "extracted" / "1" / "1" / "003" / "sample_1_rgb.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"rgb")

            def fake_writer(source_path, output_path, pixel_box):
                from ml.data_pipeline.dyson_weight_reference import DysonPipelineError
                raise DysonPipelineError(
                    f"bbox outside source image bounds: {source_path} box={pixel_box} image=20x20"
                )

            report = materialize_dyson_berry_crops(
                snapshot_dir=snapshot,
                raw_root=raw,
                join_audit_root=join,
                output_root=root / "out",
                audit_root=root / "audit",
                crop_writer=fake_writer,
            )

            self.assertEqual(report["bbox_out_of_bounds_count"], 1)
            self.assertEqual(report["successful_crop_count"], 0)

    def test_existing_crop_is_reused_without_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._write_snapshot(root)
            join = self._write_join(root)
            raw = root / "raw"
            source = raw / "extracted" / "1" / "1" / "003" / "sample_1_rgb.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"rgb")

            out = root / "out"
            expected = out / "strawberry_dyson_lincoln_tbd__003" / "berry-1-"
            # First run discovers the deterministic path.
            def writer(source_path, output_path, pixel_box):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"crop")
                return (100, 100)

            first = materialize_dyson_berry_crops(
                snapshot_dir=snapshot,
                raw_root=raw,
                join_audit_root=join,
                output_root=out,
                audit_root=root / "audit1",
                crop_writer=writer,
            )
            self.assertEqual(first["materialized_count"], 1)

            second = materialize_dyson_berry_crops(
                snapshot_dir=snapshot,
                raw_root=raw,
                join_audit_root=join,
                output_root=out,
                audit_root=root / "audit2",
                crop_writer=mock.Mock(side_effect=AssertionError("writer must not rerun")),
            )
            self.assertEqual(second["reused_existing_crop_count"], 1)
            self.assertEqual(second["successful_crop_count"], 1)


if __name__ == "__main__":
    unittest.main()
