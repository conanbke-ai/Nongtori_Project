from __future__ import annotations

import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional local dependency boundary
    np = None

from ml.data_pipeline.dyson_weight_reference import (
    DATASET_ROLE,
    DysonPipelineError,
    LICENSE,
    acquire_dyson_dataset,
    audit_dyson_dataset,
    classify_sample_file,
    extract_dyson_archives,
    is_macos_metadata_path,
)


class DysonWeightReferenceTests(unittest.TestCase):
    def setUp(self):
        if np is None and self._testMethodName not in {
            "test_suffix_to_sample_stem",
            "test_acquisition_blocks_when_gdown_missing",
            "test_acquisition_manifest_keeps_noncommercial_guard",
        }:
            self.skipTest("NumPy unavailable in this test environment")

    def test_macos_metadata_detection(self):
        self.assertTrue(is_macos_metadata_path(Path("__MACOSX/1/001/._sample_label.npy")))
        self.assertTrue(is_macos_metadata_path(Path("001/._sample_rgb.png")))
        self.assertTrue(is_macos_metadata_path(Path("001/.DS_Store")))
        self.assertFalse(is_macos_metadata_path(Path("001/sample_label.npy")))

    def test_suffix_to_sample_stem(self):
        cases = {
            "strawberry_001_rgb.png": ("strawberry_001", "rgb"),
            "strawberry_001_label.npy": ("strawberry_001", "weight_label"),
            "strawberry_001_rdepth.npy": ("strawberry_001", "raw_depth"),
            "strawberry_001_bgremoved.png": ("strawberry_001", "bgremoved_rgb"),
            "strawberry_001_pc.ply": ("strawberry_001", "point_cloud"),
        }
        for name, expected in cases.items():
            self.assertEqual(classify_sample_file(Path(name)), expected)

    def test_complete_sample_join_and_label_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()

            stem = "strawberry_dyson_test_001"
            (raw / f"{stem}_rgb.png").write_bytes(b"rgb")
            (raw / f"{stem}_bgremoved.png").write_bytes(b"bg")
            (raw / f"{stem}_pc.ply").write_text("ply", encoding="utf-8")
            np.save(raw / f"{stem}_rdepth.npy", np.array([[1.0]], dtype=np.float32))
            np.save(raw / f"{stem}_label.npy", np.array([12.5, 14.0], dtype=np.float32))

            report = audit_dyson_dataset(raw, audit)

            self.assertEqual(report["exact_rgb_weight_matched_count"], 1)
            self.assertEqual(report["weight_label_summary"]["total_label_rows"], 1)
            self.assertEqual(report["weight_label_summary"]["total_label_numeric_values"], 2)
            self.assertEqual(report["weight_label_summary"]["shape_counts"], {"(2,)": 1})
            self.assertFalse(report["commercial_training_ready"])
            self.assertEqual(report["dataset_role"], DATASET_ROLE)
            self.assertEqual(report["license"], LICENSE)

    def test_missing_rgb_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()
            np.save(raw / "sample_label.npy", np.array([12.0], dtype=np.float32))

            report = audit_dyson_dataset(raw, audit)

            self.assertEqual(report["missing_rgb_count"], 1)
            self.assertEqual(report["status"], "DYSON_REFERENCE_AUDIT_WITH_EXCEPTIONS")

    def test_missing_label_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()
            (raw / "sample_rgb.png").write_bytes(b"rgb")

            report = audit_dyson_dataset(raw, audit)

            self.assertEqual(report["missing_weight_count"], 1)

    def test_same_basename_in_different_partitions_is_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            for partition in ("1", "2"):
                folder = raw / "extracted" / partition
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "sample_rgb.png").write_bytes(partition.encode())
                np.save(folder / "sample_label.npy", np.array([[12.0, 1.0, 2.0]], dtype=np.float32))

            report = audit_dyson_dataset(raw, audit)

            self.assertEqual(report["total_sample_ids"], 2)
            self.assertEqual(report["duplicate_role_count"], 0)
            self.assertEqual(report["exact_rgb_weight_matched_count"], 2)

    def test_scene_schema_links_full_and_coordinate_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            folder = raw / "extracted" / "1" / "1" / "003"
            folder.mkdir(parents=True)

            scene = "strawberry_dyson_lincoln_tbd__003"
            for view in (1, 2, 3):
                (folder / f"{scene}_{view}_rgb.png").write_bytes(f"rgb-{view}".encode())

            full = np.array(
                [
                    [1.0, 22.8, 46.05, 36.11, 32.36, 363.0, 244.0],
                    [2.0, 4.7, 28.63, 20.30, 19.62, 285.0, 342.0],
                ],
                dtype=np.float32,
            )
            coords2 = np.array([[1.0, 319.0, 253.0], [2.0, 261.0, 331.0]], dtype=np.float32)
            coords3 = np.array([[1.0, 347.0, 201.0], [2.0, 275.0, 298.0]], dtype=np.float32)
            np.save(folder / f"{scene}_1_label.npy", full)
            np.save(folder / f"{scene}_2_label.npy", coords2)
            np.save(folder / f"{scene}_3_label.npy", coords3)

            report = audit_dyson_dataset(raw, audit)
            scene_report = report["scene_schema_summary"]

            self.assertEqual(scene_report["scene_count"], 1)
            self.assertEqual(scene_report["three_view_scene_count"], 1)
            self.assertEqual(scene_report["full_label_scene_count"], 1)
            self.assertEqual(scene_report["full_label_row_count"], 2)
            self.assertEqual(scene_report["three_column_row_count"], 4)
            self.assertEqual(scene_report["scene_instance_id_match_count"], 1)
            self.assertEqual(scene_report["scene_instance_id_mismatch_count"], 0)
            self.assertEqual(scene_report["candidate_weight_column"]["count"], 2)
            self.assertAlmostEqual(scene_report["candidate_weight_column"]["min"], 4.7, places=4)
            self.assertAlmostEqual(scene_report["candidate_weight_column"]["max"], 22.8, places=4)

    def test_rgb_hash_duplicates_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            for partition in ("1", "2"):
                folder = raw / "extracted" / partition
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "sample_1_rgb.png").write_bytes(b"same-rgb")
                np.save(
                    folder / "sample_1_label.npy",
                    np.array([[1.0, 12.0, 30.0, 25.0, 20.0, 100.0, 100.0]], dtype=np.float32),
                )

            report = audit_dyson_dataset(raw, audit)
            rgb = report["scene_schema_summary"]["rgb_identity"]

            self.assertEqual(rgb["rgb_file_count"], 2)
            self.assertEqual(rgb["unique_rgb_sha256_count"], 1)
            self.assertEqual(rgb["duplicate_rgb_file_count"], 1)

    def test_scene_exception_report_captures_mismatch_and_six_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            folder = raw / "extracted" / "1" / "1" / "900"
            folder.mkdir(parents=True)

            scene = "strawberry_dyson_lincoln_tbd__900"
            for view in (1, 2, 3):
                (folder / f"{scene}_{view}_rgb.png").write_bytes(f"rgb-{view}".encode())

            full6 = np.array([[1.0, 19.0, 30.0, 20.0, 100.0, 80.0]], dtype=np.float32)
            coords2 = np.array([[1.0, 110.0, 90.0]], dtype=np.float32)
            coords3 = np.array([[2.0, 120.0, 95.0]], dtype=np.float32)
            np.save(folder / f"{scene}_1_label.npy", full6)
            np.save(folder / f"{scene}_2_label.npy", coords2)
            np.save(folder / f"{scene}_3_label.npy", coords3)

            report = audit_dyson_dataset(raw, audit)
            exc_path = audit / "scene-schema-exceptions.json"
            exc = json.loads(exc_path.read_text(encoding="utf-8"))

            self.assertEqual(report["scene_schema_summary"]["exception_summary"]["mismatch_scene_count"], 1)
            self.assertEqual(exc["mismatch_scene_count"], 1)
            self.assertEqual(exc["six_column_row_count"], 1)
            self.assertEqual(exc["incomplete_three_view_scene_count"], 0)

    def test_paper_delta_uses_scene_and_rgb_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            folder = raw / "extracted" / "1" / "1" / "901"
            folder.mkdir(parents=True)

            scene = "strawberry_dyson_lincoln_tbd__901"
            for view in (1, 2, 3):
                (folder / f"{scene}_{view}_rgb.png").write_bytes(f"rgb-{view}".encode())
                np.save(
                    folder / f"{scene}_{view}_label.npy",
                    np.array([[1.0, 12.0, 20.0]], dtype=np.float32),
                )

            report = audit_dyson_dataset(raw, audit)
            delta = report["scene_schema_summary"]["paper_delta"]

            self.assertEqual(delta["scene_delta"], 1 - 532)
            self.assertEqual(delta["rgb_delta"], 3 - 1588)

    def test_physical_berry_manifest_uses_only_strict_seven_column_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            folder = raw / "extracted" / "1" / "1" / "010"
            folder.mkdir(parents=True)

            scene = "strawberry_dyson_lincoln_tbd__010"
            for view in (1, 2, 3):
                (folder / f"{scene}_{view}_rgb.png").write_bytes(f"rgb-{view}".encode())

            np.save(
                folder / f"{scene}_1_label.npy",
                np.array(
                    [
                        [1.0, 19.5, 45.98, 34.48, 30.71, 331.0, 157.0],
                        [2.0, 2.0, 23.41, 15.13, 13.75, 196.0, 250.0],
                    ],
                    dtype=np.float32,
                ),
            )
            np.save(
                folder / f"{scene}_2_label.npy",
                np.array([[1.0, 300.0, 180.0]], dtype=np.float32),
            )
            np.save(
                folder / f"{scene}_3_label.npy",
                np.array([[1.0, 320.0, 190.0], [2.0, 210.0, 260.0]], dtype=np.float32),
            )

            report = audit_dyson_dataset(raw, audit)
            summary = report["scene_schema_summary"]["physical_berry_summary"]
            rows = list(csv.DictReader((audit / "physical-berry-manifest.csv").open(encoding="utf-8")))

            self.assertEqual(summary["strict_berry_count"], 2)
            self.assertEqual(summary["strict_scene_count"], 1)
            self.assertEqual(summary["matched_view_count_distribution"], {"2": 1, "3": 1})
            self.assertEqual(summary["all_view_1_2_3_berry_count"], 1)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source_schema"], "STRICT_7_COLUMN")
            self.assertEqual(rows[0]["dataset_role"], DATASET_ROLE)
            self.assertEqual(rows[0]["commercial_training_ready"], "False")

    def test_annotation_only_partition_is_classified_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            folder = raw / "extracted" / "2" / "2" / "011"
            folder.mkdir(parents=True)

            stem = "strawberry_dyson_lincoln_tbd__011_1"
            (folder / f"{stem}_rgb.png").write_bytes(b"rgb")
            (folder / f"{stem}.json").write_text("{}", encoding="utf-8")

            report = audit_dyson_dataset(raw, audit)
            roles = report["scene_schema_summary"]["partition_roles"]

            self.assertEqual(roles["2"], "ANNOTATION_ONLY_RGB_JSON")
            self.assertEqual(report["scene_schema_summary"]["physical_berry_summary"]["strict_berry_count"], 0)

    def test_multicolumn_label_requires_schema_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()
            (raw / "sample_rgb.png").write_bytes(b"rgb")
            np.save(
                raw / "sample_label.npy",
                np.array([[12.0, 100.0, 200.0], [13.0, 110.0, 210.0]], dtype=np.float32),
            )

            report = audit_dyson_dataset(raw, audit)

            summary = report["weight_label_summary"]
            self.assertEqual(summary["label_schema_status"], "UNRESOLVED_MULTI_COLUMN_LABEL")
            self.assertEqual(summary["total_label_rows"], 2)
            self.assertEqual(summary["total_label_numeric_values"], 6)
            self.assertEqual(summary["column_count_counts"], {"3": 1})
            self.assertEqual(report["status"], "DYSON_REFERENCE_SCHEMA_REVIEW_REQUIRED")

    def test_duplicate_role_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()
            (raw / "sample_rgb.png").write_bytes(b"a")
            (raw / "sample_RGB.PNG").write_bytes(b"b")
            np.save(raw / "sample_label.npy", np.array([12.0], dtype=np.float32))

            report = audit_dyson_dataset(raw, audit)

            self.assertEqual(report["duplicate_role_count"], 1)

    def test_invalid_nan_inf_negative_labels_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()
            (raw / "sample_rgb.png").write_bytes(b"rgb")
            np.save(
                raw / "sample_label.npy",
                np.array([12.0, np.nan, np.inf, -1.0], dtype=np.float32),
            )

            report = audit_dyson_dataset(raw, audit)

            summary = report["weight_label_summary"]
            self.assertEqual(summary["invalid_non_finite_values"], 2)
            self.assertEqual(summary["non_positive_numeric_values"], 1)
            self.assertEqual(report["status"], "DYSON_REFERENCE_AUDIT_WITH_EXCEPTIONS")

    def test_acquisition_blocks_when_gdown_missing(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "ml.data_pipeline.dyson_weight_reference._gdown_available",
            return_value=False,
        ):
            with self.assertRaisesRegex(DysonPipelineError, "pip install gdown"):
                acquire_dyson_dataset(
                    Path(tmp) / "raw",
                    Path(tmp) / "audit",
                )

    def _write_four_archives(self, root: Path) -> None:
        for index in range(1, 5):
            with zipfile.ZipFile(root / f"{index}.zip", "w", compression=zipfile.ZIP_DEFLATED) as zf:
                stem = f"sample_{index}"
                zf.writestr(f"{stem}_rgb.png", b"rgb")
                buffer = io.BytesIO()
                np.save(buffer, np.array([10.0 + index], dtype=np.float32))
                zf.writestr(f"{stem}_label.npy", buffer.getvalue())

    def test_extract_materializes_four_archives_and_rerun_reuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()
            self._write_four_archives(raw)

            first = extract_dyson_archives(raw, audit)
            second = extract_dyson_archives(raw, audit)

            self.assertEqual(first["archive_count"], 4)
            self.assertEqual(first["member_file_count"], 8)
            self.assertEqual(first["extracted_member_count"], 8)
            self.assertEqual(second["reused_member_count"], 8)
            self.assertEqual(second["extracted_member_count"], 0)
            self.assertTrue((raw / "extracted" / "1" / "sample_1_rgb.png").exists())

    def test_extract_rejects_incomplete_archive_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()
            with zipfile.ZipFile(raw / "1.zip", "w") as zf:
                zf.writestr("sample_rgb.png", b"rgb")

            with self.assertRaisesRegex(DysonPipelineError, "archive set"):
                extract_dyson_archives(raw, audit)

    def test_extract_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()
            for index in range(1, 5):
                with zipfile.ZipFile(raw / f"{index}.zip", "w") as zf:
                    name = "../escape.txt" if index == 1 else f"sample_{index}_rgb.png"
                    zf.writestr(name, b"x")

            with self.assertRaisesRegex(DysonPipelineError, "unsafe path"):
                extract_dyson_archives(raw, audit)

    def test_audit_ignores_existing_macos_metadata_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()
            (raw / "sample_rgb.png").write_bytes(b"rgb")
            np.save(raw / "sample_label.npy", np.array([12.0], dtype=np.float32))
            mac = raw / "__MACOSX" / "x"
            mac.mkdir(parents=True)
            (mac / "._sample_rgb.png").write_bytes(b"appledouble")
            (mac / "._sample_label.npy").write_bytes(b"not-numpy")
            (mac / ".DS_Store").write_bytes(b"meta")

            report = audit_dyson_dataset(raw, audit)

            self.assertEqual(report["exact_rgb_weight_matched_count"], 1)
            self.assertEqual(report["ignored_macos_metadata_count"], 3)
            self.assertEqual(report["unclassified_file_count"], 0)

    def test_audit_ignores_source_zip_files_after_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            audit = root / "audit"
            raw.mkdir()
            self._write_four_archives(raw)
            extract_dyson_archives(raw, audit)

            report = audit_dyson_dataset(raw, audit)

            self.assertEqual(report["source_archive_count"], 4)
            self.assertEqual(report["total_sample_ids"], 4)
            self.assertEqual(report["exact_rgb_weight_matched_count"], 4)
            self.assertEqual(report["unclassified_file_count"], 0)

    def test_external_raw_root_is_git_ignored(self):
        gitignore = Path(".gitignore").read_text(encoding="utf-8")
        self.assertIn("/data/external/", gitignore)

    def test_acquisition_uses_supported_gdown_641_options(self):
        captured = {}

        class Completed:
            returncode = 0

        def fake_runner(command, check=False):
            captured["command"] = list(command)
            output = Path(command[command.index("-O") + 1])
            output.mkdir(parents=True, exist_ok=True)
            for index in range(1, 5):
                with zipfile.ZipFile(output / f"{index}.zip", "w"):
                    pass
            return Completed()

        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "ml.data_pipeline.dyson_weight_reference._gdown_available",
            return_value=True,
        ):
            acquire_dyson_dataset(
                Path(tmp) / "raw",
                Path(tmp) / "audit",
                runner=fake_runner,
            )

        command = captured["command"]
        self.assertIn("--continue", command)
        self.assertIn("--retries", command)
        self.assertIn("--timeout", command)
        self.assertNotIn("--remaining-ok", command)
        self.assertNotIn("--fuzzy", command)
        self.assertNotIn("--folder", command)

    def test_acquisition_manifest_keeps_noncommercial_guard(self):
        class Completed:
            returncode = 0

        def fake_runner(command, check=False):
            output_index = command.index("-O") + 1
            output = Path(command[output_index])
            output.mkdir(parents=True, exist_ok=True)
            for index in range(1, 5):
                with zipfile.ZipFile(output / f"{index}.zip", "w"):
                    pass
            return Completed()

        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "ml.data_pipeline.dyson_weight_reference._gdown_available",
            return_value=True,
        ):
            report = acquire_dyson_dataset(
                Path(tmp) / "raw",
                Path(tmp) / "audit",
                runner=fake_runner,
            )

            self.assertFalse(report["commercial_training_ready"])
            self.assertEqual(report["dataset_role"], DATASET_ROLE)
            self.assertEqual(report["license"], LICENSE)


if __name__ == "__main__":
    unittest.main()
