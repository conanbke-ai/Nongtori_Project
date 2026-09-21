from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ml.data_pipeline.dryad_manifest_audit import (
    EXPECTED_PATHS,
    audit_manifest_records,
    audit_official_manifest,
    write_manifest_audit,
)


def _record(index: int, path: str, *, size: int = 100, digest: str | None = None):
    return {
        "path": path,
        "size": size,
        "digestType": "sha-256",
        "digest": digest or hashlib.sha256(path.encode("utf-8")).hexdigest(),
        "_links": {"self": {"href": f"/api/v2/files/{1000 + index}"}},
    }


class DryadManifestAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = {
            "identifier": "doi:10.25338/B8V308",
            "publicationDate": "2018-02-08",
            "versionNumber": 1,
        }

    def test_complete_official_manifest_is_verified(self) -> None:
        files = [_record(index, path) for index, path in enumerate(EXPECTED_PATHS)]
        report = audit_manifest_records(self.dataset, files)
        self.assertEqual(report["status"], "MANIFEST_VERIFIED")
        self.assertEqual(report["checks"]["expected_file_count"], 28)
        self.assertEqual(report["category_counts"], {
            "datasheet": 1,
            "pictures": 7,
            "scans": 20,
            "unexpected": 0,
        })
        self.assertEqual(report["missing_paths"], [])
        self.assertEqual(report["duplicate_paths"], [])
        self.assertEqual(len(report["manifest_rows_sha256"]), 64)

    def test_missing_duplicate_and_unexpected_paths_are_reported(self) -> None:
        files = [_record(index, path) for index, path in enumerate(EXPECTED_PATHS[:-1])]
        files.append(_record(99, "Pictures_01.zip"))
        files.append(_record(100, "notes.txt"))
        report = audit_manifest_records(self.dataset, files)
        self.assertEqual(report["status"], "MANIFEST_REVIEW_REQUIRED")
        self.assertEqual(report["missing_paths"], ["Scans_20.zip"])
        self.assertEqual(report["duplicate_paths"], ["Pictures_01.zip"])
        self.assertEqual(report["unexpected_paths"], ["notes.txt"])

    def test_invalid_size_digest_and_duplicate_digest_are_reported(self) -> None:
        files = [_record(index, path) for index, path in enumerate(EXPECTED_PATHS)]
        files[0]["size"] = 0
        files[1]["digestType"] = "md5"
        files[1]["digest"] = "bad"
        shared = hashlib.sha256(b"shared").hexdigest()
        files[2]["digest"] = shared
        files[3]["digest"] = shared
        report = audit_manifest_records(self.dataset, files)
        self.assertFalse(report["checks"]["all_sizes_positive"])
        self.assertFalse(report["checks"]["all_digests_sha256"])
        self.assertFalse(report["checks"]["no_duplicate_sha256"])
        self.assertEqual(report["invalid_sizes"][0]["path"], "datasheet.xlsx")
        self.assertEqual(report["invalid_digests"][0]["path"], "Pictures_01.zip")
        self.assertEqual(report["duplicate_sha256"][0]["paths"], ["Pictures_02.zip", "Pictures_03.zip"])

    def test_live_wrapper_uses_resolved_manifest_and_writer_persists_json(self) -> None:
        files = [_record(index, path) for index, path in enumerate(EXPECTED_PATHS)]
        with mock.patch(
            "ml.data_pipeline.dryad_manifest_audit.resolve_manifest",
            return_value=(self.dataset, files),
        ) as resolve:
            report = audit_official_manifest(timeout=17)
        resolve.assert_called_once_with("doi:10.25338/B8V308", timeout=17)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "manifest-audit.json"
            write_manifest_audit(report, output)
            self.assertIn("MANIFEST_VERIFIED", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
