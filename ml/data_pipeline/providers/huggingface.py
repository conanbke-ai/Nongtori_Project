from __future__ import annotations

import shutil
from pathlib import Path

from ..models import DownloadResult, SourceRecord
from .base import ProviderAdapter


class HuggingFaceAdapter(ProviderAdapter):
    def download(self, source: SourceRecord, output_dir: Path) -> DownloadResult:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError("huggingface_hub is required: pip install huggingface_hub") from exc

        repo_id = source.retrieval["repo_id"]
        revision = source.retrieval.get("revision") or source.version_or_revision
        patterns = source.retrieval.get("allow_patterns")
        root = Path(snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            revision=revision,
            allow_patterns=patterns,
            local_dir=Path(output_dir),
        ))
        files = tuple(sorted(path for path in root.rglob("*") if path.is_file()))
        return DownloadResult(source.source_id, source.provider, root, files, {"repo_id": repo_id, "revision": revision, "file_count": len(files)})
