from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from ml.data_pipeline import dyson_annotations
from ml.data_pipeline.dyson_annotations import (
    acquire_dyson_annotations,
    audit_dyson_annotations,
    extract_dyson_annotations,
)
from ml.data_pipeline.dyson_weight_reference import DysonPipelineError


class DysonAnnotationPipelineTests(unittest.TestCase):
    def _write_annotation_zip(self, path: Path) -> None:
        payload = {
            "image": "strawberry_dyson_lincoln_tbd__001_1_rgb.png",
            "annotations": [
                {
                    "id": 1,
                    "bbox": [10, 20, 30, 40],
                    "keypoints": [[11, 21], [12, 22]],
                    "category": "ripe",
                }
            ],
        }
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "dyson_annotations/strawberry_dyson_lincoln_tbd__001_1.json",
                json.dumps(payload),
            )
            zf.writestr(
                "__MACOSX/dyson_annotations/._strawberry_dyson_lincoln_tbd__001_1.json",
                b"metadata",
            )
            zf.writestr("README.txt", b"ignore")

    def test_extract_and_schema_audit_are_descriptive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "dyson_annotations.zip"
            annotation_root = root / "annotations"
            audit_root = root / "audit"
            self._write_annotation_zip(archive)

            extraction = extract_dyson_annotations(
                archive,
                annotation_root / "extracted",
            )
            report = audit_dyson_annotations(annotation_root, audit_root)

            self.assertEqual(extraction["json_member_count"], 1)
            self.assertEqual(extraction["skipped_macos_metadata_count"], 1)
            self.assertEqual(extraction["skipped_non_json_count"], 1)
            self.assertEqual(report["json_file_count"], 1)
            self.assertEqual(report["parse_error_count"], 0)
            self.assertEqual(report["top_level_type_counts"], {"object": 1})
            self.assertEqual(report["interesting_key_counts"]["bbox"], 1)
            self.assertEqual(report["interesting_key_counts"]["keypoints"], 1)
            self.assertEqual(report["interesting_key_counts"]["category"], 1)
            self.assertEqual(
                report["list_dict_keysets"]["$.annotations"][0]["keyset"],
                "bbox|category|id|keypoints",
            )

    def test_acquisition_reuses_verified_archive_and_keeps_noncommercial_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            annotation_root = root / "annotations"
            audit_root = root / "audit"
            annotation_root.mkdir()
            archive = annotation_root / "dyson_annotations.zip"
            self._write_annotation_zip(archive)

            size = archive.stat().st_size
            blob_sha1 = dyson_annotations._git_blob_sha1(archive)
            with mock.patch.object(
                dyson_annotations,
                "ANNOTATION_ARCHIVE_SIZE",
                size,
            ), mock.patch.object(
                dyson_annotations,
                "ANNOTATION_GIT_BLOB_SHA1",
                blob_sha1,
            ):
                report = acquire_dyson_annotations(
                    annotation_root,
                    audit_root,
                    opener=mock.Mock(side_effect=AssertionError("download should not run")),
                )

            self.assertTrue(report["reused_verified_archive"])
            self.assertFalse(report["commercial_training_ready"])
            self.assertEqual(report["verified_git_blob_sha1"], blob_sha1)
            self.assertEqual(
                report["extraction"]["status"],
                "DYSON_ANNOTATIONS_MATERIALIZED",
            )

    def test_extract_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "dyson_annotations.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../escape.json", "{}")

            with self.assertRaisesRegex(DysonPipelineError, "unsafe path"):
                extract_dyson_annotations(archive, root / "out")


if __name__ == "__main__":
    unittest.main()
