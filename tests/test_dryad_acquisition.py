from __future__ import annotations

import hashlib
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from ml.data_pipeline.dryad_acquisition import (
    DryadAccessError,
    build_public_manifest_inventory,
    download_file,
    download_file_resumable,
    download_url,
    ensure_datasheet,
    file_id,
    load_env_local,
    request_access_token,
    resolve_access_token,
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

    def test_load_env_local_does_not_override_process_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env.local"
            path.write_text("DRYAD_CLIENT_ID=file-id\nDRYAD_CLIENT_SECRET=file-secret\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"DRYAD_CLIENT_ID": "process-id"}, clear=True):
                load_env_local(path)
                self.assertEqual(__import__("os").environ["DRYAD_CLIENT_ID"], "process-id")
                self.assertEqual(__import__("os").environ["DRYAD_CLIENT_SECRET"], "file-secret")

    def test_resolve_access_token_prefers_explicit_or_env_token(self) -> None:
        self.assertEqual(resolve_access_token(token="explicit-token"), "explicit-token")
        with mock.patch.dict("os.environ", {"DRYAD_TOKEN": "env-token"}, clear=True):
            self.assertEqual(resolve_access_token(), "env-token")

    def test_request_access_token_requires_client_credentials_before_network(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch("pathlib.Path.exists", return_value=False):
            with self.assertRaisesRegex(DryadAccessError, "DRYAD_CLIENT_ID"):
                request_access_token()

    def test_resolve_access_token_uses_client_credentials_when_no_token(self) -> None:
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

    def test_download_url_prefers_manifest_download_link(self) -> None:
        record = {
            "_links": {
                "self": {"href": "/api/v2/files/141475"},
                "stash:download": {"href": "/api/v2/files/141475/download"},
            }
        }
        self.assertEqual(
            download_url(record),
            "https://datadryad.org/api/v2/files/141475/download",
        )

    def test_download_renews_once_after_401_when_token_not_explicit(self) -> None:
        record = {"size": 2, "_links": {"self": {"href": "/api/v2/files/141475"}}}
        unauthorized = urllib.error.HTTPError(
            "https://datadryad.org/api/v2/files/141475/download",
            401,
            "Unauthorized",
            hdrs=None,
            fp=None,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "datasheet.xlsx"
            def transfer(_record, path, *, access_token, timeout):
                if access_token == "expired-token":
                    raise unauthorized
                path.write_bytes(b"PK")
            with mock.patch(
                "ml.data_pipeline.dryad_acquisition.resolve_access_token",
                return_value="expired-token",
            ), mock.patch(
                "ml.data_pipeline.dryad_acquisition.request_access_token",
                return_value="fresh-token",
            ) as refresh, mock.patch(
                "ml.data_pipeline.dryad_acquisition._transfer_file",
                side_effect=transfer,
            ):
                result = download_file(record, output)
            refresh.assert_called_once()
            self.assertEqual(result["size"], 2)

    def test_explicit_token_does_not_silently_refresh_after_401(self) -> None:
        record = {"size": 2, "_links": {"self": {"href": "/api/v2/files/141475"}}}
        unauthorized = urllib.error.HTTPError(
            "https://datadryad.org/api/v2/files/141475/download",
            401,
            "Unauthorized",
            hdrs=None,
            fp=None,
        )
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch(
            "ml.data_pipeline.dryad_acquisition.resolve_access_token",
            return_value="explicit-token",
        ), mock.patch(
            "ml.data_pipeline.dryad_acquisition._transfer_file",
            side_effect=unauthorized,
        ), mock.patch(
            "ml.data_pipeline.dryad_acquisition.request_access_token"
        ) as refresh:
            with self.assertRaises(urllib.error.HTTPError):
                download_file(record, Path(temp_dir) / "datasheet.xlsx", token="explicit-token")
            refresh.assert_not_called()

    def test_ensure_datasheet_reuses_verified_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "datasheet.xlsx"
            payload = b"PK verified"
            output.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            dataset = {
                "identifier": "doi:10.25338/B8V308",
                "publicationDate": "2018-02-08",
                "versionNumber": 1,
            }
            files = [{
                "path": "datasheet.xlsx",
                "size": len(payload),
                "digestType": "sha-256",
                "digest": digest,
                "_links": {"self": {"href": "/api/v2/files/141475"}},
            }]
            with mock.patch(
                "ml.data_pipeline.dryad_acquisition.download_file"
            ) as download:
                report = ensure_datasheet(output, dataset, files)
            download.assert_not_called()
            self.assertEqual(report["action"], "REUSED_VERIFIED")
            self.assertTrue(report["verification"]["digest_verified"])

    def test_ensure_datasheet_redownloads_after_verification_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "datasheet.xlsx"
            output.write_bytes(b"stale")
            dataset = {
                "identifier": "doi:10.25338/B8V308",
                "publicationDate": "2018-02-08",
                "versionNumber": 1,
            }
            files = [{
                "path": "datasheet.xlsx",
                "size": 8,
                "digestType": "sha-256",
                "digest": "expected",
                "_links": {"self": {"href": "/api/v2/files/141475"}},
            }]
            with mock.patch(
                "ml.data_pipeline.dryad_acquisition.download_file",
                return_value={"path": str(output), "size": 8, "digest_verified": True},
            ) as download:
                report = ensure_datasheet(output, dataset, files)
            download.assert_called_once()
            self.assertEqual(report["action"], "REDOWNLOADED_AFTER_VERIFICATION_FAILURE")

    def test_public_manifest_inventory_classifies_archives(self) -> None:
        dataset = {"identifier": "doi:10.25338/B8V308", "publicationDate": "2018-02-08", "versionNumber": 1}
        files = [
            {"path": "datasheet.xlsx", "size": 100, "_links": {"self": {"href": "/api/v2/files/1"}}},
            {"path": "Pictures_01.zip", "size": 200, "_links": {"self": {"href": "/api/v2/files/2"}}},
            {"path": "Scans_01.zip", "size": 300, "_links": {"self": {"href": "/api/v2/files/3"}}},
        ]
        with mock.patch(
            "ml.data_pipeline.dryad_acquisition.resolve_manifest",
            return_value=(dataset, files),
        ):
            report = build_public_manifest_inventory()
        self.assertEqual(report["file_count"], 3)
        self.assertEqual(report["picture_archive_count"], 1)
        self.assertEqual(report["scan_archive_count"], 1)
        self.assertEqual(report["picture_archive_bytes"], 200)
        self.assertEqual(report["scan_archive_bytes"], 300)
        self.assertEqual([item["role"] for item in report["files"]], ["DATASHEET", "PICTURE_ARCHIVE", "SCAN_ARCHIVE"])


    def test_resumable_archive_download_appends_from_partial_file(self) -> None:
        payload = b"abcdefghijklmnopqrstuvwxyz"
        record = {
            "path": "Pictures_01.zip",
            "size": len(payload),
            "digestType": "sha-256",
            "digest": hashlib.sha256(payload).hexdigest(),
            "_links": {"self": {"href": "/api/v2/files/101"}},
        }

        class Response:
            status = 206
            def __init__(self, body):
                self.body = body
                self.offset = 0
            def getcode(self):
                return self.status
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, size=-1):
                if self.offset >= len(self.body):
                    return b""
                if size < 0:
                    size = len(self.body) - self.offset
                out = self.body[self.offset:self.offset + size]
                self.offset += len(out)
                return out

        class Opener:
            def __init__(self):
                self.range_headers = []
            def open(self, request, timeout):
                self.range_headers.append(request.headers.get("Range"))
                return Response(payload[10:])

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "Pictures_01.zip"
            part = output.with_name(output.name + ".part")
            part.write_bytes(payload[:10])
            opener = Opener()
            with mock.patch(
                "ml.data_pipeline.dryad_acquisition.resolve_access_token",
                return_value="token",
            ):
                result = download_file_resumable(
                    record,
                    output,
                    opener=opener,
                    sleeper=lambda _delay: None,
                )
            self.assertEqual(output.read_bytes(), payload)
            self.assertEqual(opener.range_headers, ["bytes=10-"])
            self.assertEqual(result["action"], "RESUMED_AND_VERIFIED")


if __name__ == "__main__":
    unittest.main()
