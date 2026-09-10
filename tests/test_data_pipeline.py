from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.audit import audit_directory
from ml.data_pipeline.dedup import deduplicate_manifest
from ml.data_pipeline.models import SourceRecord
from ml.data_pipeline.normalize import ExternalMapping, LabelContractError, normalize_external_row, normalize_field_row, write_normalized
from ml.data_pipeline.providers.direct_http import DirectHttpAdapter
from ml.data_pipeline.registry import DatasetRegistry
from ml.data_pipeline.snapshot import create_snapshot
from ml.data_pipeline.split import create_split_manifest
from ml.data_pipeline.training_snapshot import create_training_snapshot


class RegistryTest(unittest.TestCase):
    def test_load_and_duplicate_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = {"source_id": "DATA-X-001", "provider": "direct_http", "title": "x", "original_url": "https://example.invalid", "retrieval": {"url": "file:///tmp/x"}}
            (root / "a.json").write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(DatasetRegistry(root).get("DATA-X-001").title, "x")


class LabelMappingTest(unittest.TestCase):
    def test_field_grade_drives_harvest_without_changing_maturity(self):
        harvested = normalize_field_row({"ID": "0001", "Group_ID": "G1", "Maturity": "3", "Grade": "SP", "Health": "NOR", "Final_Name": "a.jpg"})
        waiting = normalize_field_row({"ID": "0002", "Group_ID": "G2", "Maturity": "3", "Grade": "NA", "Health": "NOR", "Final_Name": "b.jpg"})
        self.assertEqual(harvested["canonical_stage"], "TURNING_LATE")
        self.assertEqual(harvested["observed_harvest"], "true")
        self.assertEqual(waiting["canonical_stage"], "TURNING_LATE")
        self.assertEqual(waiting["observed_harvest"], "false")

    def test_malformed_requires_jm_but_jm_does_not_imply_malformed(self):
        malformed = normalize_field_row({"ID": "0003", "Group_ID": "G3", "Maturity": "4", "Grade": "JM", "Health": "MAL", "Final_Name": "c.jpg"})
        self.assertEqual(malformed["grade_reason"], "MALFORMED")
        with self.assertRaises(LabelContractError):
            normalize_field_row({"ID": "0004", "Group_ID": "G4", "Maturity": "4", "Grade": "SP", "Health": "MAL", "Final_Name": "d.jpg"})

    def test_external_overripe_maps_to_maturity4_jm_without_harvest_claim(self):
        mapping = ExternalMapping(source_id="DATA-RIP-X", mapping_version="MAP-X-v1", labels={"overripe": {"canonical_stage": "OVERRIPE", "maturity": 4, "grade": "JM", "confidence": "HIGH", "basis": "FIELD_POLICY"}})
        row = normalize_external_row({"sample_id": "x1", "label": "overripe", "asset_path": "x.jpg"}, mapping)
        self.assertEqual(row["nongtori_maturity"], "4")
        self.assertEqual(row["nongtori_grade"], "JM")
        self.assertEqual(row["grade_reason"], "OVERRIPE")
        self.assertEqual(row["observed_harvest"], "")


class NormalizeSplitSnapshotTest(unittest.TestCase):
    def test_dedup_atomic_split_and_immutable_training_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized = root / "normalized.csv"
            rows = [
                normalize_field_row({"ID": "1", "Group_ID": "G1", "Maturity": "3", "Grade": "SP", "Health": "NOR", "Final_Name": "1.jpg", "content_sha256": "a" * 64}),
                normalize_field_row({"ID": "2", "Group_ID": "G1", "Maturity": "3", "Grade": "SP", "Health": "NOR", "Final_Name": "2.jpg", "content_sha256": "b" * 64}),
                normalize_field_row({"ID": "3", "Group_ID": "G2", "Maturity": "4", "Grade": "JM", "Health": "NOR", "Final_Name": "3.jpg", "content_sha256": "a" * 64}),
                normalize_field_row({"ID": "4", "Group_ID": "G3", "Maturity": "2", "Grade": "NA", "Health": "NOR", "Final_Name": "4.jpg", "content_sha256": "c" * 64}),
            ]
            write_normalized(rows, normalized)
            dedup = root / "dedup.csv"
            report = deduplicate_manifest(normalized, dedup)
            self.assertEqual(report["duplicate"], 1)
            split = root / "split.csv"
            counts = create_split_manifest(dedup, split, seed="test-seed")
            self.assertEqual(sum(counts.values()), 4)
            with split.open(encoding="utf-8", newline="") as f:
                split_rows = list(csv.DictReader(f))
            self.assertEqual(len({r["split"] for r in split_rows if r["atomic_group"] == "G1"}), 1)
            self.assertEqual(next(r for r in split_rows if r["sample_id"] == "3")["split"], "excluded")
            snapshots = root / "snapshots"
            snapshot = create_training_snapshot("train-snap-001", normalized_manifest=normalized, dedup_manifest=dedup, split_manifest=split, snapshot_root=snapshots, label_mapping_version="MAP-FIELD-001-v1", source_ids=["DATA-FIELD-001"])
            meta = json.loads((snapshot / "TRAINING_SNAPSHOT.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "SNAPSHOT_READY")
            with self.assertRaises(FileExistsError):
                create_training_snapshot("train-snap-001", normalized_manifest=normalized, dedup_manifest=dedup, split_manifest=split, snapshot_root=snapshots, label_mapping_version="MAP-FIELD-001-v1")


class PipelineTest(unittest.TestCase):
    def test_direct_download_audit_and_immutable_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_file = root / "source.bin"
            source_file.write_bytes(b"nongtori-test-data")
            source = SourceRecord.from_dict({"source_id": "DATA-X-001", "provider": "direct_http", "title": "local fixture", "original_url": source_file.as_uri(), "version_or_revision": "v1", "retrieval": {"url": source_file.as_uri(), "filename": "fixture.bin"}})
            raw = root / "raw"
            result = DirectHttpAdapter().download(source, raw)
            self.assertEqual(result.files[0].read_bytes(), b"nongtori-test-data")
            audit_dir = root / "audit"
            report = audit_directory(raw, audit_dir)
            self.assertEqual(report["file_count"], 1)
            self.assertEqual(report["status"], "AUDITED")
            snapshots = root / "snapshots"
            snapshot = create_snapshot("snap-001", source.source_id, "v1", audit_dir, snapshots)
            self.assertTrue((snapshot / "SNAPSHOT.json").exists())
            with self.assertRaises(FileExistsError):
                create_snapshot("snap-001", source.source_id, "v1", audit_dir, snapshots)


if __name__ == "__main__":
    unittest.main()
