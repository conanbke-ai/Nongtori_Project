from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from ml.data_pipeline.dryad_materialization import (
    MATERIALIZED_STATUS,
    materialize_strict_candidates,
)


class DryadMaterializationTests(unittest.TestCase):
    def _fixture(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("0001_view_01.jpg", b"image-one")
            archive.writestr("0001_view_02.jpg", b"image-two")
        payload = raw.getvalue()
        archive_digest = __import__("hashlib").sha256(payload).hexdigest()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            rows = []
            for info in archive.infolist():
                rows.append({
                    "fruit_id": "0001",
                    "archive_path": "Pictures_01.zip",
                    "archive_file_id": "101",
                    "archive_sha256": archive_digest,
                    "filename": info.filename,
                    "file_size": info.file_size,
                    "compress_size": info.compress_size,
                    "compress_type": info.compress_type,
                    "crc32": f"{info.CRC & 0xFFFFFFFF:08x}",
                    "header_offset": info.header_offset,
                })
        candidate = {
            "status": "STRICT_CANDIDATE_MANIFEST_VERIFIED",
            "rows_sha256": "candidate-sha",
            "image_count": 2,
            "rows": rows,
        }
        official = [{
            "path": "Pictures_01.zip",
            "size": len(payload),
            "digestType": "sha-256",
            "digest": archive_digest,
            "_links": {"self": {"href": "/api/v2/files/101"}},
        }]
        return payload, candidate, official

    def test_materialize_archive_cache_reuse_and_repair(self) -> None:
        payload, candidate, official = self._fixture()
        calls = {"downloads": 0}

        def archive_downloader(record, output, *, timeout):
            calls["downloads"] += 1
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(payload)
            return {"action": "DOWNLOADED_VERIFIED", "path": str(output)}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_path = root / "candidate.json"
            output_root = root / "assets"
            output_manifest = root / "materialized.json"
            cache_dir = root / "cache"
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

            with mock.patch(
                "ml.data_pipeline.dryad_materialization.resolve_manifest",
                return_value=({"identifier": "doi:10.25338/B8V308"}, official),
            ):
                first = materialize_strict_candidates(
                    candidate_path,
                    output_root,
                    output_manifest,
                    archive_cache_dir=cache_dir,
                    archive_downloader=archive_downloader,
                    checkpoint_every=1,
                )
                self.assertEqual(first["status"], MATERIALIZED_STATUS)
                self.assertEqual(first["downloaded_count"], 2)
                self.assertEqual(first["reused_count"], 0)
                self.assertEqual(first["archive_download_count"], 1)
                self.assertEqual(first["materialization_mode"], "SEQUENTIAL_ARCHIVE_CACHE")
                self.assertFalse((cache_dir / "Pictures_01.zip").exists())

                second = materialize_strict_candidates(
                    candidate_path,
                    output_root,
                    output_manifest,
                    archive_cache_dir=cache_dir,
                    archive_downloader=archive_downloader,
                )
                self.assertEqual(second["downloaded_count"], 0)
                self.assertEqual(second["reused_count"], 2)
                self.assertEqual(calls["downloads"], 1)

                damaged = output_root / second["files"][0]["relative_path"]
                damaged.write_bytes(b"corrupt")
                third = materialize_strict_candidates(
                    candidate_path,
                    output_root,
                    output_manifest,
                    archive_cache_dir=cache_dir,
                    archive_downloader=archive_downloader,
                )
                self.assertEqual(third["downloaded_count"], 1)
                self.assertEqual(third["repaired_count"], 1)
                self.assertEqual(third["reused_count"], 1)
                self.assertEqual(calls["downloads"], 2)

    def test_keep_archives_preserves_verified_zip(self) -> None:
        payload, candidate, official = self._fixture()

        def archive_downloader(record, output, *, timeout):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(payload)
            return {"action": "DOWNLOADED_VERIFIED", "path": str(output)}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_path = root / "candidate.json"
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            cache_dir = root / "cache"
            with mock.patch(
                "ml.data_pipeline.dryad_materialization.resolve_manifest",
                return_value=({"identifier": "doi:10.25338/B8V308"}, official),
            ):
                materialize_strict_candidates(
                    candidate_path,
                    root / "assets",
                    root / "out.json",
                    archive_cache_dir=cache_dir,
                    keep_archives=True,
                    archive_downloader=archive_downloader,
                )
            self.assertTrue((cache_dir / "Pictures_01.zip").exists())

    def test_rejects_unsafe_member_path(self) -> None:
        _, candidate, official = self._fixture()
        candidate["rows"][0]["filename"] = "../escape.jpg"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "candidate.json"
            path.write_text(json.dumps(candidate), encoding="utf-8")
            with mock.patch(
                "ml.data_pipeline.dryad_materialization.resolve_manifest",
                return_value=({"identifier": "doi:10.25338/B8V308"}, official),
            ):
                with self.assertRaisesRegex(Exception, "Unsafe ZIP member path"):
                    materialize_strict_candidates(
                        path,
                        root / "assets",
                        root / "out.json",
                    )


if __name__ == "__main__":
    unittest.main()
