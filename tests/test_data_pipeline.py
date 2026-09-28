from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.audit import audit_directory
from ml.data_pipeline.dedup import deduplicate_manifest
from ml.data_pipeline.field_audit import audit_field_rows
from ml.data_pipeline.dryad_weight_snapshot import freeze_dryad_weight_snapshot
from ml.data_pipeline.incremental import scan_incremental_rows
from ml.data_pipeline.models import SourceRecord
from ml.data_pipeline.normalize import ExternalMapping, LabelContractError, normalize_external_row, normalize_field_row, write_normalized
from ml.data_pipeline.providers.direct_http import DirectHttpAdapter
from ml.data_pipeline.registry import DatasetRegistry
from ml.data_pipeline.rename_manifest import preflight_rename
from ml.data_pipeline.snapshot import create_snapshot
from ml.data_pipeline.split import create_split_manifest
from ml.data_pipeline.training_snapshot import create_training_snapshot
from ml.data_pipeline.working_assets import materialize_working_assets


class RegistryTest(unittest.TestCase):
    def test_load_and_duplicate_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = {"source_id": "DATA-X-001", "provider": "direct_http", "title": "x", "original_url": "https://example.invalid", "retrieval": {"url": "file:///tmp/x"}}
            (root / "a.json").write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(DatasetRegistry(root).get("DATA-X-001").title, "x")


class IncrementalIngestionTest(unittest.TestCase):
    def test_new_unchanged_updated_removed_revision_flow(self):
        initial = [{"Farm": "M", "ID": "1", "Grade": "NA", "Maturity": "3"}, {"Farm": "M", "ID": "2", "Grade": "SP", "Maturity": "4"}]
        ledger, counts = scan_incremental_rows(initial, [], recorded_at="2026-09-10T00:00:00+00:00")
        self.assertEqual(counts, {"NEW": 2, "UPDATED": 0, "REMOVED": 0, "UNCHANGED": 0})
        current = [{"Farm": "M", "ID": "1", "Grade": "SP", "Maturity": "3"}, {"Farm": "M", "ID": "3", "Grade": "NA", "Maturity": "2"}]
        ledger2, counts2 = scan_incremental_rows(current, ledger, recorded_at="2026-09-11T00:00:00+00:00")
        self.assertEqual(counts2, {"NEW": 1, "UPDATED": 1, "REMOVED": 1, "UNCHANGED": 0})
        updated = next(e for e in ledger2 if e["source_key"] == "M:1" and e["revision"] == "2")
        self.assertEqual(json.loads(updated["changed_fields_json"])["Grade"], {"old": "NA", "new": "SP"})
        ledger3, counts3 = scan_incremental_rows(current, ledger2, recorded_at="2026-09-12T00:00:00+00:00")
        self.assertEqual(counts3["UNCHANGED"], 2)
        self.assertEqual(len(ledger3), len(ledger2))


class FieldAuditTest(unittest.TestCase):
    def test_str_and_lef_are_task_separated(self):
        rows = [{"ID": "1", "Class": "STR", "Maturity": "3", "Grade": "SP", "Health": "NOR"}, {"ID": "2", "Class": "STR", "Maturity": "3", "Grade": "NA", "Health": "NOR"}, {"ID": "3", "Class": "LEF", "Health": "MIT"}]
        report = audit_field_rows(rows)
        self.assertEqual(report["fruit_rows"], 2)
        self.assertEqual(report["leaf_rows"], 1)
        leaf = normalize_field_row(rows[2])
        self.assertEqual(leaf["task_eligible"], "false")


class RenameManifestTest(unittest.TestCase):
    def test_exact_match_and_content_store_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"; source.mkdir()
            (source / "IMG_0001.jpg").write_bytes(b"same-image")
            rows = [{"ID": "1", "Farm": "M", "Original_No": "IMG_0001", "Final_Name": "SB_1.jpg"}]
            manifest, summary = preflight_rename(rows, source, farm_id="M", capture_session_id="S1")
            self.assertEqual(summary["status"], "PREFLIGHT_PASSED")
            self.assertEqual(manifest[0]["match_strategy"], "ORIGINAL_NO_EXACT")
            out1, counts1 = materialize_working_assets(manifest, source, root / "objects", root / "sessions")
            self.assertTrue(Path(out1[0]["working_session_path"]).exists())
            self.assertEqual(counts1["SESSION_LINKED"], 1)
            (source / "IMG_0002.jpg").write_bytes(b"same-image")
            rows2 = [{"ID": "2", "Farm": "M", "Original_No": "IMG_0002", "Final_Name": "SB_2.jpg"}]
            manifest2, summary2 = preflight_rename(rows2, source, farm_id="M", capture_session_id="S2")
            # isolate the second capture session source set as production ingestion does
            source2 = root / "source2"; source2.mkdir(); (source2 / "IMG_0002.jpg").write_bytes(b"same-image")
            manifest2, summary2 = preflight_rename(rows2, source2, farm_id="M", capture_session_id="S2")
            self.assertEqual(summary2["status"], "PREFLIGHT_PASSED")
            _, counts2 = materialize_working_assets(manifest2, source2, root / "objects", root / "sessions")
            self.assertEqual(counts2["REUSED"], 1)

    def test_count_mismatch_blocks_materialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"; source.mkdir()
            (source / "IMG_0001.jpg").write_bytes(b"1")
            rows = [
                {"ID": "1", "Farm": "M", "Original_No": "IMG_0001", "Final_Name": "SB_1.jpg"},
                {"ID": "2", "Farm": "M", "Original_No": "IMG_0002", "Final_Name": "SB_2.jpg"},
            ]
            manifest, summary = preflight_rename(rows, source, farm_id="M", capture_session_id="S1")
            self.assertEqual(summary["status"], "PREFLIGHT_BLOCKED")
            with self.assertRaises(ValueError):
                materialize_working_assets(manifest, source, root / "objects", root / "sessions")


class LabelMappingTest(unittest.TestCase):
    def test_field_grade_drives_harvest_without_changing_maturity(self):
        harvested = normalize_field_row({"ID": "0001", "Class": "STR", "Group_ID": "G1", "Maturity": "3", "Grade": "SP", "Health": "NOR", "Final_Name": "a.jpg"})
        waiting = normalize_field_row({"ID": "0002", "Class": "STR", "Group_ID": "G2", "Maturity": "3", "Grade": "NA", "Health": "NOR", "Final_Name": "b.jpg"})
        self.assertEqual(harvested["canonical_stage"], "TURNING_LATE")
        self.assertEqual(harvested["observed_harvest"], "true")
        self.assertEqual(waiting["observed_harvest"], "false")

    def test_malformed_requires_jm_but_jm_does_not_imply_malformed(self):
        malformed = normalize_field_row({"ID": "0003", "Class": "STR", "Group_ID": "G3", "Maturity": "4", "Grade": "JM", "Health": "MAL", "Final_Name": "c.jpg"})
        self.assertEqual(malformed["grade_reason"], "MALFORMED")
        with self.assertRaises(LabelContractError):
            normalize_field_row({"ID": "0004", "Class": "STR", "Group_ID": "G4", "Maturity": "4", "Grade": "SP", "Health": "MAL", "Final_Name": "d.jpg"})

    def test_external_overripe_maps_to_maturity4_jm_without_harvest_claim(self):
        mapping = ExternalMapping(source_id="DATA-RIP-X", mapping_version="MAP-X-v1", labels={"overripe": {"canonical_stage": "OVERRIPE", "maturity": 4, "grade": "JM", "confidence": "HIGH", "basis": "FIELD_POLICY"}})
        row = normalize_external_row({"sample_id": "x1", "label": "overripe", "asset_path": "x.jpg"}, mapping)
        self.assertEqual(row["nongtori_maturity"], "4")
        self.assertEqual(row["nongtori_grade"], "JM")
        self.assertEqual(row["observed_harvest"], "")


class NormalizeSplitSnapshotTest(unittest.TestCase):
    def test_dedup_atomic_split_and_immutable_training_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); normalized = root / "normalized.csv"
            rows = [
                normalize_field_row({"ID": "1", "Class": "STR", "Group_ID": "G1", "Maturity": "3", "Grade": "SP", "Health": "NOR", "Final_Name": "1.jpg", "content_sha256": "a" * 64}),
                normalize_field_row({"ID": "2", "Class": "STR", "Group_ID": "G1", "Maturity": "3", "Grade": "SP", "Health": "NOR", "Final_Name": "2.jpg", "content_sha256": "b" * 64}),
                normalize_field_row({"ID": "3", "Class": "STR", "Group_ID": "G2", "Maturity": "4", "Grade": "JM", "Health": "NOR", "Final_Name": "3.jpg", "content_sha256": "a" * 64}),
                normalize_field_row({"ID": "4", "Class": "STR", "Group_ID": "G3", "Maturity": "2", "Grade": "NA", "Health": "NOR", "Final_Name": "4.jpg", "content_sha256": "c" * 64}),
            ]
            write_normalized(rows, normalized)
            dedup = root / "dedup.csv"; self.assertEqual(deduplicate_manifest(normalized, dedup)["duplicate"], 1)
            split = root / "split.csv"; create_split_manifest(dedup, split, seed="test-seed")
            snapshot = create_training_snapshot("train-snap-001", normalized_manifest=normalized, dedup_manifest=dedup, split_manifest=split, snapshot_root=root / "snapshots", label_mapping_version="MAP-FIELD-001-v1", source_ids=["DATA-FIELD-001"])
            self.assertTrue((snapshot / "TRAINING_SNAPSHOT.json").exists())


class DryadWeightSnapshotTest(unittest.TestCase):
    def _fixture(self, root: Path, *, complete: bool = True):
        asset_root = root / "strict-rgb"
        rows = []
        files = []
        weights = {}
        for fruit_id, weight in (("0001", 23.0), ("0002", 15.0)):
            weights[fruit_id] = {
                "weight_with_calyx_g": weight,
                "weight_without_calyx_g": weight - 1.0,
                "width_mm": 30.0,
                "height_mm": 40.0,
                "variety": "fixture",
                "shape": "conical",
            }
            for view in range(1, 23):
                filename = f"{fruit_id}_view_{view:02d}.jpg"
                relative = f"Pictures_01/{filename}"
                payload = f"{fruit_id}-{view}".encode("utf-8")
                path = asset_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                digest = hashlib.sha256(payload).hexdigest()
                rows.append({
                    "fruit_id": fruit_id,
                    "archive_path": "Pictures_01.zip",
                    "filename": filename,
                    "file_size": len(payload),
                    "crc32": "",
                })
                files.append({
                    "fruit_id": fruit_id,
                    "archive_path": "Pictures_01.zip",
                    "filename": filename,
                    "relative_path": relative,
                    "size": len(payload),
                    "crc32": "",
                    "sha256": digest,
                })

        candidate = {
            "status": "STRICT_CANDIDATE_MANIFEST_VERIFIED",
            "fruit_count": 2,
            "image_count": 44,
            "rows_sha256": "c" * 64,
            "rows": rows,
        }
        candidate_path = root / "candidate.json"
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

        materialized_files = files if complete else files[:-1]
        materialized = {
            "status": "STRICT_CANDIDATE_ASSETS_VERIFIED" if complete else "PARTIAL_MATERIALIZATION",
            "candidate_rows_sha256": candidate["rows_sha256"],
            "candidate_image_count": 44,
            "verified_file_count": len(materialized_files),
            "root": str(asset_root),
            "files": materialized_files,
        }
        materialized_path = root / "materialized.json"
        materialized_path.write_text(json.dumps(materialized), encoding="utf-8")
        datasheet = root / "datasheet.xlsx"
        datasheet.write_bytes(b"fixture-datasheet")
        return candidate_path, materialized_path, datasheet, weights

    def test_freezes_exact_fruit_atomic_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate, materialized, datasheet, weights = self._fixture(root)
            report = freeze_dryad_weight_snapshot(
                candidate_manifest=candidate,
                materialized_manifest=materialized,
                datasheet=datasheet,
                snapshot_root=root / "snapshots",
                seed="fixture-seed",
                train_ratio=0.5,
                val_ratio=0.0,
                test_ratio=0.5,
                weight_loader=lambda _path: weights,
            )
            self.assertEqual(report["status"], "WEIGHT_SNAPSHOT_FROZEN")
            self.assertEqual(report["fruit_count"], 2)
            self.assertEqual(report["image_count"], 44)
            self.assertEqual(report["split_policy"]["fruit_counts"], {"test": 1, "train": 1})
            self.assertEqual(report["split_policy"]["image_counts"], {"test": 22, "train": 22})
            snapshot_dir = Path(report["snapshot_dir"])
            self.assertTrue((snapshot_dir / "WEIGHT_SNAPSHOT.json").exists())
            with (snapshot_dir / "sample-manifest.csv").open(encoding="utf-8", newline="") as handle:
                samples = list(csv.DictReader(handle))
            split_by_fruit = {}
            for row in samples:
                split_by_fruit.setdefault(row["fruit_id"], row["split"])
                self.assertEqual(split_by_fruit[row["fruit_id"]], row["split"])
            self.assertEqual({row["weight_grade"] for row in samples if row["fruit_id"] == "0001"}, {"SP_WEIGHT"})
            self.assertEqual({row["weight_grade"] for row in samples if row["fruit_id"] == "0002"}, {"MD_WEIGHT"})

            with self.assertRaisesRegex(Exception, "already exists"):
                freeze_dryad_weight_snapshot(
                    candidate_manifest=candidate,
                    materialized_manifest=materialized,
                    datasheet=datasheet,
                    snapshot_root=root / "snapshots",
                    seed="fixture-seed",
                    train_ratio=0.5,
                    val_ratio=0.0,
                    test_ratio=0.5,
                    weight_loader=lambda _path: weights,
                )

    def test_blocks_partial_materialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate, materialized, datasheet, weights = self._fixture(root, complete=False)
            with self.assertRaisesRegex(Exception, "complete materialization"):
                freeze_dryad_weight_snapshot(
                    candidate_manifest=candidate,
                    materialized_manifest=materialized,
                    datasheet=datasheet,
                    snapshot_root=root / "snapshots",
                    weight_loader=lambda _path: weights,
                )


class PipelineTest(unittest.TestCase):
    def test_direct_download_audit_and_immutable_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source_file = root / "source.bin"; source_file.write_bytes(b"nongtori-test-data")
            source = SourceRecord.from_dict({"source_id": "DATA-X-001", "provider": "direct_http", "title": "local fixture", "original_url": source_file.as_uri(), "version_or_revision": "v1", "retrieval": {"url": source_file.as_uri(), "filename": "fixture.bin"}})
            result = DirectHttpAdapter().download(source, root / "raw")
            self.assertEqual(result.files[0].read_bytes(), b"nongtori-test-data")
            audit_dir = root / "audit"; self.assertEqual(audit_directory(root / "raw", audit_dir)["status"], "AUDITED")
            self.assertTrue((create_snapshot("snap-001", source.source_id, "v1", audit_dir, root / "snapshots") / "SNAPSHOT.json").exists())


if __name__ == "__main__": unittest.main()
