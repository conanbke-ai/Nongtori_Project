from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.audit import audit_directory
from ml.data_pipeline.dedup import deduplicate_manifest
from ml.data_pipeline.field_audit import audit_field_rows
from ml.data_pipeline.incremental import scan_incremental_rows
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


class IncrementalIngestionTest(unittest.TestCase):
    def test_new_unchanged_updated_removed_revision_flow(self):
        initial = [
            {"Farm": "M", "ID": "1", "Grade": "NA", "Maturity": "3"},
            {"Farm": "M", "ID": "2", "Grade": "SP", "Maturity": "4"},
        ]
        ledger, counts = scan_incremental_rows(initial, [], recorded_at="2026-09-10T00:00:00+00:00")
        self.assertEqual(counts, {"NEW": 2, "UPDATED": 0, "REMOVED": 0, "UNCHANGED": 0})
        current = [
            {"Farm": "M", "ID": "1", "Grade": "SP", "Maturity": "3"},
            {"Farm": "M", "ID": "3", "Grade": "NA", "Maturity": "2"},
        ]
        ledger2, counts2 = scan_incremental_rows(current, ledger, recorded_at="2026-09-11T00:00:00+00:00")
        self.assertEqual(counts2, {"NEW": 1, "UPDATED": 1, "REMOVED": 1, "UNCHANGED": 0})
        updated = next(e for e in ledger2 if e["source_key"] == "M:1" and e["revision"] == "2")
        self.assertEqual(json.loads(updated["changed_fields_json"])["Grade"], {"old": "NA", "new": "SP"})
        removed = next(e for e in ledger2 if e["source_key"] == "M:2" and e["revision"] == "2")
        self.assertEqual(removed["state_after"], "REMOVED_FROM_SOURCE")
        ledger3, counts3 = scan_incremental_rows(current, ledger2, recorded_at="2026-09-12T00:00:00+00:00")
        self.assertEqual(counts3["UNCHANGED"], 2)
        self.assertEqual(len(ledger3), len(ledger2))


class FieldAuditTest(unittest.TestCase):
    def test_str_and_lef_are_task_separated(self):
        rows = [
            {"ID": "1", "Class": "STR", "Maturity": "3", "Grade": "SP", "Health": "NOR"},
            {"ID": "2", "Class": "STR", "Maturity": "3", "Grade": "NA", "Health": "NOR"},
            {"ID": "3", "Class": "LEF", "Health": "MIT"},
        ]
        report = audit_field_rows(rows)
        self.assertEqual(report["fruit_rows"], 2)
        self.assertEqual(report["leaf_rows"], 1)
        self.assertEqual(report["maturity3_harvested"], 1)
        self.assertEqual(report["maturity3_not_harvested"], 1)
        leaf = normalize_field_row(rows[2])
        self.assertEqual(leaf["task_eligible"], "false")
        self.assertEqual(leaf["exclusion_reason"], "NON_FRUIT_RIPENESS_TARGET")


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
            root = Path(tmp)
            normalized = root / "normalized.csv"
            rows = [
                normalize_field_row({"ID": "1", "Class": "STR", "Group_ID": "G1", "Maturity": "3", "Grade": "SP", "Health": "NOR", "Final_Name": "1.jpg", "content_sha256": "a" * 64}),
                normalize_field_row({"ID": "2", "Class": "STR", "Group_ID": "G1", "Maturity": "3", "Grade": "SP", "Health": "NOR", "Final_Name": "2.jpg", "content_sha256": "b" * 64}),
                normalize_field_row({"ID": "3", "Class": "STR", "Group_ID": "G2", "Maturity": "4", "Grade": "JM", "Health": "NOR", "Final_Name": "3.jpg", "content_sha256": "a" * 64}),
                normalize_field_row({"ID": "4", "Class": "STR", "Group_ID": "G3", "Maturity": "2", "Grade": "NA", "Health": "NOR", "Final_Name": "4.jpg", "content_sha256": "c" * 64}),
            ]
            write_normalized(rows, normalized)
            dedup = root / "dedup.csv"
            report = deduplicate_manifest(normalized, dedup)
            self.assertEqual(report["duplicate"], 1)
            split = root / "split.csv"
            counts = create_split_manifest(dedup, split, seed="test-seed")
            self.assertEqual(sum(counts.values()), 4)
            snapshots = root / "snapshots"
            snapshot = create_training_snapshot("train-snap-001", normalized_manifest=normalized, dedup_manifest=dedup, split_manifest=split, snapshot_root=snapshots, label_mapping_version="MAP-FIELD-001-v1", source_ids=["DATA-FIELD-001"])
            self.assertTrue((snapshot / "TRAINING_SNAPSHOT.json").exists())


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
            self.assertEqual(report["status"], "AUDITED")
            snapshots = root / "snapshots"
            snapshot = create_snapshot("snap-001", source.source_id, "v1", audit_dir, snapshots)
            self.assertTrue((snapshot / "SNAPSHOT.json").exists())


if __name__ == "__main__":
    unittest.main()
