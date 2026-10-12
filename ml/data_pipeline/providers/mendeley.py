from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from ..models import DownloadResult, SourceRecord
from .base import ProviderAdapter
from .direct_http import stream_download


MENDELEY_API_ROOT = "https://api.data.mendeley.com"


class MendeleyAdapter(ProviderAdapter):
    """Download a published Mendeley Data version through the current public API."""

    def _list_files(self, dataset_id: str, version: str) -> tuple[str, list[dict[str, object]]]:
        query = urllib.parse.urlencode(
            {
                "version": version,
                "folder_id": "root",
                "$start": 0,
                "$limit": 500,
            }
        )
        candidates = [
            f"{MENDELEY_API_ROOT}/datasets/publics/{dataset_id}/files?{query}",
            f"{MENDELEY_API_ROOT}/datasets/{dataset_id}/files?{query}",
        ]
        errors: list[str] = []
        headers = {
            "Accept": "application/json",
            "User-Agent": "Nongtori-Data-Pipeline/1.0 (+https://github.com/conanbke-ai/Nongtori_Project)",
        }

        for api_url in candidates:
            request = urllib.request.Request(api_url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = json.load(response)
            except urllib.error.HTTPError as exc:
                errors.append(f"{api_url} -> HTTP {exc.code}")
                continue
            except urllib.error.URLError as exc:
                errors.append(f"{api_url} -> {exc.reason}")
                continue

            if isinstance(payload, dict):
                files = payload.get("results") or payload.get("files") or []
            else:
                files = payload
            if isinstance(files, list) and files:
                return api_url, files
            errors.append(f"{api_url} -> empty/unsupported response")

        raise RuntimeError(
            "Mendeley public dataset file listing failed. "
            "The legacy data.mendeley.com/public-api endpoint is no longer used. "
            + "; ".join(errors)
        )

    def download(self, source: SourceRecord, output_dir: Path) -> DownloadResult:
        dataset_id = source.retrieval["dataset_id"]
        version = str(source.retrieval.get("version", "1"))
        api_url, files = self._list_files(dataset_id, version)

        output_dir = Path(output_dir)
        downloaded: list[Path] = []
        entries: list[dict[str, object]] = []
        for index, item in enumerate(files, start=1):
            details = item.get("content_details") or {}
            url = details.get("download_url")
            if not url:
                file_id = item.get("id")
                if not file_id:
                    raise RuntimeError(
                        f"Mendeley file entry has neither download_url nor id: {item!r}"
                    )
                url = (
                    f"{MENDELEY_API_ROOT}/datasets/{dataset_id}/files/"
                    f"{file_id}/file_downloaded?version={urllib.parse.quote(version)}"
                )

            filename = (
                item.get("filename")
                or item.get("name")
                or Path(urlparse(str(url)).path).name
                or f"mendeley-file-{index}"
            )
            destination = output_dir / str(filename)
            meta = stream_download(str(url), destination)
            downloaded.append(destination)
            entries.append({"filename": str(filename), **meta})

        return DownloadResult(
            source.source_id,
            source.provider,
            output_dir,
            tuple(downloaded),
            {"api_url": api_url, "files": entries},
        )
