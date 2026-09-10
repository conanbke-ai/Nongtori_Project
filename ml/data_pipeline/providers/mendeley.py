from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from ..models import DownloadResult, SourceRecord
from .base import ProviderAdapter
from .direct_http import stream_download


class MendeleyAdapter(ProviderAdapter):
    """Download a published Mendeley Data version through its public file API."""

    def download(self, source: SourceRecord, output_dir: Path) -> DownloadResult:
        dataset_id = source.retrieval["dataset_id"]
        version = str(source.retrieval.get("version", "1"))
        api_url = f"https://data.mendeley.com/public-api/datasets/{dataset_id}/files?folder_id=root&version={version}"
        with urllib.request.urlopen(api_url) as response:
            files = json.load(response)
        if not files:
            raise RuntimeError(f"Mendeley returned no files for {dataset_id} v{version}")
        output_dir = Path(output_dir)
        downloaded: list[Path] = []
        entries: list[dict[str, object]] = []
        for index, item in enumerate(files, start=1):
            url = item["content_details"]["download_url"]
            filename = item.get("filename") or item.get("name") or Path(urlparse(url).path).name or f"mendeley-file-{index}"
            destination = output_dir / filename
            meta = stream_download(url, destination)
            downloaded.append(destination)
            entries.append({"filename": filename, **meta})
        return DownloadResult(source.source_id, source.provider, output_dir, tuple(downloaded), {"api_url": api_url, "files": entries})
