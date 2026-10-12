from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from ..models import DownloadResult, SourceRecord
from .base import ProviderAdapter
from .direct_http import stream_download


MENDELEY_API_ROOT = "https://api.data.mendeley.com"
MENDELEY_TOKEN_URL = "https://auth.data.mendeley.com/oauth2/token"


class MendeleyAccessError(RuntimeError):
    pass


def _load_env_local(path: Path = Path(".env.local")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _request_access_token(timeout: int = 60) -> str:
    _load_env_local()
    explicit = os.environ.get("MENDELEY_DATA_TOKEN")
    if explicit:
        return explicit

    client_id = os.environ.get("MENDELEY_DATA_CLIENT_ID")
    client_secret = os.environ.get("MENDELEY_DATA_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise MendeleyAccessError(
            "Mendeley Data credentials are missing. Register one Digital Commons Data API "
            "client, then put MENDELEY_DATA_CLIENT_ID and MENDELEY_DATA_CLIENT_SECRET in "
            ".env.local. After that, dataset downloads are fully automated."
        )

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "scope": "dcd:profile",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        MENDELEY_TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "Nongtori-Data-Pipeline/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise MendeleyAccessError(
            f"Failed to obtain Mendeley Data access token: HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise MendeleyAccessError(
            f"Failed to obtain Mendeley Data access token: {exc.reason}"
        ) from exc

    token = str(payload.get("access_token") or "")
    if not token:
        raise MendeleyAccessError("Mendeley Data token endpoint returned no access_token")
    return token


class MendeleyAdapter(ProviderAdapter):
    """Download a published Mendeley Data version through the authenticated API."""

    def _list_files(
        self,
        dataset_id: str,
        version: str,
        access_token: str,
    ) -> tuple[str, list[dict[str, object]]]:
        query = urllib.parse.urlencode(
            {
                "version": version,
                "folder_id": "root",
                "$start": 0,
                "$limit": 500,
            }
        )
        api_url = f"{MENDELEY_API_ROOT}/datasets/publics/{dataset_id}/files?{query}"
        request = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "Nongtori-Data-Pipeline/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise MendeleyAccessError(
                f"Mendeley file listing failed: HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise MendeleyAccessError(
                f"Mendeley file listing failed: {exc.reason}"
            ) from exc

        files = payload.get("results") or payload.get("files") or [] if isinstance(payload, dict) else payload
        if not isinstance(files, list) or not files:
            raise MendeleyAccessError(
                f"Mendeley returned no files for dataset {dataset_id} version {version}"
            )
        return api_url, files

    def download(self, source: SourceRecord, output_dir: Path) -> DownloadResult:
        dataset_id = source.retrieval["dataset_id"]
        version = str(source.retrieval.get("version", "1"))
        access_token = _request_access_token()
        api_url, files = self._list_files(dataset_id, version, access_token)

        output_dir = Path(output_dir)
        downloaded: list[Path] = []
        entries: list[dict[str, object]] = []
        for index, item in enumerate(files, start=1):
            details = item.get("content_details") or {}
            url = details.get("download_url")
            expected_sha256 = details.get("sha256_hash")
            filename = (
                item.get("filename")
                or item.get("name")
                or (Path(urlparse(str(url)).path).name if url else "")
                or f"mendeley-file-{index}"
            )
            destination = output_dir / str(filename)

            if url:
                meta = stream_download(
                    str(url),
                    destination,
                    str(expected_sha256) if expected_sha256 else None,
                )
            else:
                file_id = item.get("id")
                if not file_id:
                    raise MendeleyAccessError(
                        f"Mendeley file entry has neither download_url nor id: {item!r}"
                    )
                api_download_url = (
                    f"{MENDELEY_API_ROOT}/datasets/{dataset_id}/files/"
                    f"{file_id}/file_downloaded?version={urllib.parse.quote(version)}"
                )
                meta = stream_download(
                    api_download_url,
                    destination,
                    str(expected_sha256) if expected_sha256 else None,
                    headers={"Authorization": f"Bearer {access_token}"},
                )

            downloaded.append(destination)
            entries.append({"filename": str(filename), **meta})

        return DownloadResult(
            source.source_id,
            source.provider,
            output_dir,
            tuple(downloaded),
            {
                "api_url": api_url,
                "authenticated": True,
                "files": entries,
            },
        )
