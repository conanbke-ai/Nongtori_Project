from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.rename_manifest import preflight_rename
from ml.data_pipeline.working_assets import materialize_working_assets


class SharedSourceAssetTest(unittest.TestCase):
    def test_same_original_no_can_back_multiple_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "IMG_0001.jpg").write_bytes(b"one-physical-image")
            rows = [
                {"ID": "1", "Farm": "M", "Date": "2026.01.05", "Zone": "Z1", "DataType": "R", "Original_No": "IMG_0001", "Final_Name": "SB_1.jpg"},
                {"ID": "2", "Farm": "M", "Date": "2026.01.05", "Zone": "Z1", "DataType": "R", "Original_No": "IMG_0001", "Final_Name": "SB_2.jpg"},
            ]
            manifest, summary = preflight_rename(rows, source, farm_id="M", capture_session_id="S1")
            self.assertEqual(summary["status"], "PREFLIGHT_PASSED")
            self.assertEqual(summary["sheet_rows"], 2)
            self.assertEqual(summary["expected_source_assets"], 1)
            self.assertEqual(summary["source_files"], 1)
            self.assertEqual(summary["shared_asset_groups"], 1)
            self.assertEqual(len(manifest), 2)
            self.assertEqual({row["asset_relation"] for row in manifest}, {"SHARED_SOURCE_ASSET"})
            self.assertEqual(len({row["source_asset_key"] for row in manifest}), 1)
            self.assertEqual(len({row["content_sha256"] for row in manifest}), 1)

            materialized, counts = materialize_working_assets(manifest, source, root / "objects", root / "sessions")
            self.assertEqual(counts["SESSION_LINKED"], 2)
            self.assertEqual(len({row["working_object_path"] for row in materialized}), 1)
            self.assertTrue(all(Path(row["working_session_path"]).exists() for row in materialized))

    def test_same_original_no_with_conflicting_context_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "IMG_0001.jpg").write_bytes(b"one-physical-image")
            rows = [
                {"ID": "1", "Farm": "M", "Date": "2026.01.05", "Zone": "Z1", "DataType": "R", "Original_No": "IMG_0001", "Final_Name": "SB_1.jpg"},
                {"ID": "2", "Farm": "M", "Date": "2026.01.05", "Zone": "Z2", "DataType": "R", "Original_No": "IMG_0001", "Final_Name": "SB_2.jpg"},
            ]
            manifest, summary = preflight_rename(rows, source, farm_id="M", capture_session_id="S1")
            self.assertEqual(summary["status"], "PREFLIGHT_BLOCKED")
            self.assertIn("SOURCE_ASSET_CONTEXT_CONFLICT", summary["blocking_errors"])
            with self.assertRaises(ValueError):
                materialize_working_assets(manifest, source, root / "objects", root / "sessions")


if __name__ == "__main__":
    unittest.main()
