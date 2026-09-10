from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import DownloadResult, SourceRecord


class ProviderAdapter(ABC):
    @abstractmethod
    def download(self, source: SourceRecord, output_dir: Path) -> DownloadResult:
        raise NotImplementedError
