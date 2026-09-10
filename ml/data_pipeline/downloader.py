from __future__ import annotations

from pathlib import Path

from .models import DownloadResult, SourceRecord
from .providers import AIHubAdapter, DirectHttpAdapter, HuggingFaceAdapter, KaggleAdapter, MendeleyAdapter


class DatasetDownloader:
    def __init__(self):
        self.adapters = {
            "direct_http": DirectHttpAdapter(),
            "mendeley": MendeleyAdapter(),
            "huggingface": HuggingFaceAdapter(),
            "kaggle": KaggleAdapter(),
            "aihub": AIHubAdapter(),
        }

    def download(self, source: SourceRecord, raw_root: Path) -> DownloadResult:
        provider = source.provider.lower()
        try:
            adapter = self.adapters[provider]
        except KeyError as exc:
            raise ValueError(f"unsupported provider: {source.provider}") from exc
        output_dir = Path(raw_root) / source.source_id / (source.version_or_revision or "unversioned")
        output_dir.mkdir(parents=True, exist_ok=True)
        return adapter.download(source, output_dir)
