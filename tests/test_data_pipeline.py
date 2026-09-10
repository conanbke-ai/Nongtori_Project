from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.audit import audit_directory
from ml.data_pipeline.models import SourceRecord
from ml.data_pipeline.providers.direct_http import DirectHttpAdapter
from ml.data_pipeline.registry import DatasetRegistry
from ml.data_pipeline.snapshot import create_snapshot


class RegistryTest(unittest.TestCase):
    def test_load_and_duplicate_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = {"source_id": "DATA-X-001", "provider": "direct_http", "title": "x", "original_url": "https://example.invalid", "retrieval": {"url": "file:///tmp/x"}}
            (root / "a.json").write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(DatasetRegistry(root).get("DATA-X-001").title, "x")


class PipelineTest(unittest.TestCase):
    def test_direct_download_audit_and_immutable_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_file = root / "source.bin"
            source_file.write_bytes(b"nongtori-test-data")
            source = SourceRecord.from_dict({
                "source_id": "DATA-X-001", "provider": "direct_http", "title": "local fixture",
                "original_url": source_file.as_uri(), "version_or_revision": "v1",
                "retrieval": {"url": source_file.as_uri(), "filename": "fixture.bin"},
            })
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
