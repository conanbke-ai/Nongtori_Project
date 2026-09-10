from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from ..models import DownloadResult, SourceRecord
from .base import ProviderAdapter

_CHUNK = 1024 * 1024


def stream_download(url: str, destination: Path, expected_sha256: str | None = None) -> dict[str, str | int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(url) as response, destination.open("wb") as out:
        while True:
            chunk = response.read(_CHUNK)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    sha256 = digest.hexdigest()
    if expected_sha256 and sha256.lower() != expected_sha256.lower():
        destination.unlink(missing_ok=True)
        raise ValueError(f"checksum mismatch for {destination.name}")
    return {"sha256": sha256, "size_bytes": size}


class DirectHttpAdapter(ProviderAdapter):
    def download(self, source: SourceRecord, output_dir: Path) -> DownloadResult:
        url = source.retrieval["url"]
        filename = source.retrieval.get("filename") or Path(urlparse(url).path).name or f"{source.source_id}.bin"
        destination = Path(output_dir) / filename
        metadata = stream_download(url, destination, source.retrieval.get("sha256"))
        return DownloadResult(source.source_id, source.provider, Path(output_dir), (destination,), metadata)
