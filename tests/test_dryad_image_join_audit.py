from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ml.data_pipeline.dryad_image_join_audit import (
    RemoteZipRangeReader,
    audit_filename_inventory,
    build_image_join_cache_identity,
    finalize_published_subset_audit,
    infer_fruit_id,
    load_cached_image_join_report,
)


class DryadImageJoinAuditTests(unittest.TestCase):
    def test_infer_fruit_id_matches_exact_known_four_digit_token(self) -> None:
        known = {"0001", "0125", "1611"}
        self.assertEqual(infer_fruit_id("photos/fruit_0125_view_03.jpg", known), ("0125", "MATCHED"))
        self.assertEqual(infer_fruit_id("photos/view_9999.jpg", known), (None, "UNMATCHED"))
        self.assertEqual(infer_fruit_id("0125_1611.jpg", known), (None, "AMBIGUOUS"))

    def test_filename_inventory_requires_exactly_22_views_per_fruit(self) -> None:
        fruit_ids = ["0001", "0002"]
        names = {
            "Pictures_01.zip": [f"0001/view_{i:02d}_0001.jpg" for i in range(1, 23)],
            "Pictures_02.zip": [f"0002/view_{i:02d}_0002.jpg" for i in range(1, 23)],
        }
        report = audit_filename_inventory(names, fruit_ids=fruit_ids)
        self.assertEqual(report["status"], "JOIN_VERIFIED")
        self.assertEqual(report["expected_image_count"], 44)
        self.assertEqual(report["matched_image_count"], 44)
        self.assertEqual(report["wrong_view_count_fruit_count"], 0)
        self.assertEqual(report["view_count_distribution"], {"22": 2})
        self.assertEqual(report["complete_22_view_fruit_count"], 2)
        self.assertEqual(report["partial_view_fruit_count"], 0)
        self.assertEqual(report["overcomplete_view_fruit_count"], 0)

        names["Pictures_02.zip"] = names["Pictures_02.zip"][:-1]
        broken = audit_filename_inventory(names, fruit_ids=fruit_ids)
        self.assertEqual(broken["status"], "REVIEW_REQUIRED")
        self.assertEqual(broken["wrong_view_count_fruit_count"], 1)
        self.assertEqual(broken["view_count_distribution"], {"21": 1, "22": 1})
        self.assertEqual(broken["complete_22_view_fruit_count"], 1)
        self.assertEqual(broken["partial_view_fruit_count"], 1)

    def test_image_join_cache_reuses_only_matching_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            datasheet = Path(temp_dir) / "datasheet.xlsx"
            datasheet.write_bytes(b"datasheet-v1")
            output = Path(temp_dir) / "image-join-audit.json"
            files = [
                {
                    "path": "Pictures_01.zip",
                    "size": 100,
                    "digestType": "sha-256",
                    "digest": "archive-a",
                }
            ]
            identity = build_image_join_cache_identity(datasheet, files)
            report = {
                "cache_identity": identity,
                "audit": {"status": "JOIN_VERIFIED"},
            }
            output.write_text(json.dumps(report), encoding="utf-8")

            reused = load_cached_image_join_report(
                output,
                datasheet=datasheet,
                files=files,
            )
            self.assertIsNotNone(reused)

            changed_files = [
                {
                    "path": "Pictures_01.zip",
                    "size": 100,
                    "digestType": "sha-256",
                    "digest": "archive-b",
                }
            ]
            self.assertIsNone(
                load_cached_image_join_report(
                    output,
                    datasheet=datasheet,
                    files=changed_files,
                )
            )

            datasheet.write_bytes(b"datasheet-v2")
            self.assertIsNone(
                load_cached_image_join_report(
                    output,
                    datasheet=datasheet,
                    files=files,
                )
            )

    def test_published_subset_finalization_accepts_photo_yes_subset(self) -> None:
        report = {
            "audit": {
                "fruit_id_count": 5,
                "image_count": 67,
                "unmatched_image_count": 0,
                "ambiguous_filename_sample": [],
                "photo_metadata_join": {
                    "NO": {"ZERO": 2},
                    "YES": {
                        "COMPLETE_22": 2,
                        "PARTIAL": 1,
                    },
                },
                "training_candidate_overlap": {
                    "primary_weight_candidate_count": 4,
                    "primary_with_any_picture_count": 3,
                    "primary_with_complete_22_views_count": 2,
                    "primary_missing_all_pictures_count": 1,
                    "primary_incomplete_picture_count": 1,
                    "primary_with_any_picture_image_count": 67,
                },
            }
        }
        finalized = finalize_published_subset_audit(report)
        self.assertEqual(
            finalized["audit"]["status"],
            "PUBLISHED_SUBSET_VERIFIED_WITH_VIEW_EXCEPTIONS",
        )
        self.assertTrue(
            finalized["audit"]["published_subset_validation"]["reconciled"]
        )
        self.assertEqual(
            finalized["audit"]["strict_training_candidate_summary"]["strict_22_view_weight_fruit_count"],
            2,
        )
        self.assertEqual(
            finalized["audit"]["strict_training_candidate_summary"]["strict_22_view_weight_image_count"],
            44,
        )

    def test_remote_zip_range_reader_supports_zipfile_without_full_download(self) -> None:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("0001_view_01.jpg", b"x")
            archive.writestr("0001_view_02.jpg", b"y")
        raw = payload.getvalue()
        requests: list[tuple[int, int]] = []

        def fetcher(record, start, end, *, access_token, timeout):
            requests.append((start, end))
            return raw[start : end + 1]

        reader = RemoteZipRangeReader(
            {"size": len(raw), "path": "Pictures_01.zip"},
            access_token="token",
            min_chunk_size=64 * 1024,
            fetcher=fetcher,
        )
        with zipfile.ZipFile(reader) as archive:
            self.assertEqual(
                archive.namelist(),
                ["0001_view_01.jpg", "0001_view_02.jpg"],
            )
        self.assertTrue(requests)
        self.assertTrue(all((end - start + 1) <= len(raw) for start, end in requests))


if __name__ == "__main__":
    unittest.main()
