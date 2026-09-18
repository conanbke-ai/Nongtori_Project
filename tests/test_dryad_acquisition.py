from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ml.data_pipeline.dryad_acquisition import (
    DryadAccessError,
    file_id,
    select_file,
    verify_download,
)


class DryadAcquisitionTests(unittest.TestCase):
    def test_select_file_requires_exact_path(self) -> None:
        files = [
            {"path": "datasheet.xlsx", "_links": {"self": {"href": "/api/v2/files/141475"}}},
            {"path": "pictures1.zip", "_links": {"self": {"href": "/api/v2/files/1"}}},
        ]
        selected = select_file(files, "datasheet.xlsx")
        self.assertEqual(file_id(selected), "141475")

        with self.assertRaises(DryadAccessError):
            select_file(files, "missing.xlsx")

    def test_verify_download_checks_size_and_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "datasheet.xlsx"
            payload = b"PK synthetic xlsx bytes"
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            report = verify_download(
                path,
                {
                    "size": len(payload),
                    "digestType": "sha-256",
                    "digest": digest,
                },
            )
            self.assertTrue(report["digest_verified"])
            self.assertEqual(report["sha256"], digest)

            with self.assertRaises(DryadAccessError):
                verify_download(path, {"size": len(payload) + 1})

    def test_resolve_access_token_prefers_temporary_token(self) -> None:
        with mock.patch.dict("os.environ", {"DRYAD_TOKEN": "temporary-token"}, clear=True):
            self.assertEqual(resolve_access_token(), "temporary-token")

    def test_request_access_token_requires_client_credentials_before_network(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(DryadAccessError, "DRYAD_CLIENT_ID"):
                request_access_token()

    def test_resolve_access_token_requests_token_from_client_credentials(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"DRYAD_CLIENT_ID": "client-id", "DRYAD_CLIENT_SECRET": "client-secret"},
            clear=True,
        ), mock.patch(
            "ml.data_pipeline.dryad_acquisition.request_access_token",
            return_value="derived-token",
        ) as request_token:
            self.assertEqual(resolve_access_token(), "derived-token")
            request_token.assert_called_once()


if __name__ == "__main__":
    unittest.main()
