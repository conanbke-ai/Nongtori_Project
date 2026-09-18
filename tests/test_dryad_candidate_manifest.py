from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ml.data_pipeline.dryad_candidate_manifest import (
    build_candidate_manifest_identity,
    build_strict_candidate_manifest,
    load_cached_candidate_manifest,
    write_candidate_manifest,
)
from ml.data_pipeline.dryad_image_join_audit import build_image_join_cache_identity


class DryadCandidateManifestTests(unittest.TestCase):
    def _files(self) -> list[dict[str, object]]:
        return [
            {
                "path": f"Pictures_{index:02d}.zip",
                "size": 1000 + index,
                "digestType": "sha-256",
                "digest": f"digest-{index}",
                "_links": {"self": {"href": f"/api/v2/files/{100 + index}"}},
            }
            for index in range(1, 8)
        ]

    def test_candidate_manifest_cache_identity_tracks_join_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            datasheet = Path(temp_dir) / "datasheet.xlsx"
            datasheet.write_bytes(b"datasheet")
            files = self._files()
            join_identity = build_image_join_cache_identity(datasheet, files)
            join_report = {"cache_identity": join_identity, "audit": {}}

            identity = build_candidate_manifest_identity(
                datasheet,
                files,
                join_report,
            )
            self.assertEqual(
                identity["image_join_fingerprint"],
                join_identity["fingerprint"],
            )

            changed = self._files()
            changed[0]["digest"] = "changed"
            with self.assertRaisesRegex(Exception, "does not match"):
                build_candidate_manifest_identity(
                    datasheet,
                    changed,
                    join_report,
                )

    def test_strict_manifest_requires_exactly_22_rows_per_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            datasheet = Path(temp_dir) / "datasheet.xlsx"
            datasheet.write_bytes(b"datasheet")
            files = self._files()
            join_identity = build_image_join_cache_identity(datasheet, files)
            join_report = {
                "cache_identity": join_identity,
                "audit": {
                    "view_counts_by_fruit": {
                        "0001": 22,
                        "0002": 22,
                        "0003": 21,
                    },
                    "strict_training_candidate_summary": {
                        "strict_22_view_weight_fruit_count": 2,
                    },
                },
            }

            def rows_for_archive(record, **kwargs):
                if record["path"] != "Pictures_01.zip":
                    return []
                rows = []
                for fruit_id in ("0001", "0002"):
                    for view in range(1, 23):
                        rows.append(
                            {
                                "fruit_id": fruit_id,
                                "archive_path": "Pictures_01.zip",
                                "archive_file_id": "101",
                                "archive_sha256": "digest-1",
                                "filename": f"{fruit_id}_view_{view:02d}.jpg",
                                "file_size": 100,
                                "compress_size": 90,
                                "compress_type": 8,
                                "crc32": "12345678",
                                "header_offset": view * 100,
                            }
                        )
                return rows

            with mock.patch(
                "ml.data_pipeline.dryad_candidate_manifest.primary_weight_candidate_ids_from_datasheet",
                return_value=["0001", "0002", "0003"],
            ), mock.patch(
                "ml.data_pipeline.dryad_candidate_manifest.resolve_access_token",
                return_value="token",
            ), mock.patch(
                "ml.data_pipeline.dryad_candidate_manifest._zip_info_rows",
                side_effect=rows_for_archive,
            ):
                report = build_strict_candidate_manifest(
                    datasheet,
                    files,
                    join_report,
                )

            self.assertEqual(
                report["status"],
                "STRICT_CANDIDATE_MANIFEST_VERIFIED",
            )
            self.assertEqual(report["fruit_count"], 2)
            self.assertEqual(report["image_count"], 44)
            self.assertEqual(report["wrong_view_count_fruit_count"], 0)
            self.assertEqual(len(report["rows"]), 44)

            output = Path(temp_dir) / "strict-candidate-manifest.json"
            write_candidate_manifest(report, output)
            reused = load_cached_candidate_manifest(
                output,
                datasheet=datasheet,
                files=files,
                image_join_report=join_report,
            )
            self.assertIsNotNone(reused)
            self.assertEqual(reused["rows_sha256"], report["rows_sha256"])


if __name__ == "__main__":
    unittest.main()
