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
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            rows = []
            for info in archive.infolist():
                rows.append({
                    "fruit_id": "0001",
                    "archive_path": "Pictures_01.zip",
                    "archive_file_id": "101",
                    "archive_sha256": "archive-digest",
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
            "digest": "archive-digest",
            "_links": {"self": {"href": "/api/v2/files/101"}},
        }]
        return payload, candidate, official

    def test_materialize_reuse_and_repair(self) -> None:
        payload, candidate, official = self._fixture()
        calls = {"readers": 0}

        def reader_factory(record, **kwargs):
            calls["readers"] += 1
            return io.BytesIO(payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate_path = root / "candidate.json"
            output_root = root / "assets"
            output_manifest = root / "materialized.json"
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

            patches = (
                mock.patch(
                    "ml.data_pipeline.dryad_materialization.resolve_manifest",
                    return_value=({"identifier": "doi:10.25338/B8V308"}, official),
                ),
                mock.patch(
                    "ml.data_pipeline.dryad_materialization.resolve_access_token",
                    return_value="token",
                ),
            )
            with patches[0], patches[1]:
                first = materialize_strict_candidates(
                    candidate_path,
                    output_root,
                    output_manifest,
                    reader_factory=reader_factory,
                    checkpoint_every=1,
                )
                self.assertEqual(first["status"], MATERIALIZED_STATUS)
                self.assertEqual(first["downloaded_count"], 2)
                self.assertEqual(first["reused_count"], 0)
                self.assertEqual(len(first["files"]), 2)

                second = materialize_strict_candidates(
                    candidate_path,
                    output_root,
                    output_manifest,
                    reader_factory=reader_factory,
                )
                self.assertEqual(second["downloaded_count"], 0)
                self.assertEqual(second["reused_count"], 2)
                self.assertEqual(calls["readers"], 1)

                damaged = output_root / second["files"][0]["relative_path"]
                damaged.write_bytes(b"corrupt")
                third = materialize_strict_candidates(
                    candidate_path,
                    output_root,
                    output_manifest,
                    reader_factory=reader_factory,
                )
                self.assertEqual(third["downloaded_count"], 1)
                self.assertEqual(third["repaired_count"], 1)
                self.assertEqual(third["reused_count"], 1)
                self.assertEqual(calls["readers"], 2)
                self.assertEqual(
                    f"{zlib.crc32(damaged.read_bytes()) & 0xFFFFFFFF:08x}",
                    third["files"][0]["crc32"],
                )

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
            ), mock.patch(
                "ml.data_pipeline.dryad_materialization.resolve_access_token",
                return_value="token",
            ):
                with self.assertRaisesRegex(Exception, "Unsafe ZIP member path"):
                    materialize_strict_candidates(path, root / "assets", root / "out.json")


if __name__ == "__main__":
    unittest.main()
