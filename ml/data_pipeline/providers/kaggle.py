from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..models import DownloadResult, SourceRecord
from .base import ProviderAdapter


class KaggleAdapter(ProviderAdapter):
    def download(self, source: SourceRecord, output_dir: Path) -> DownloadResult:
        if not shutil.which("kaggle"):
            raise RuntimeError("Kaggle CLI is required and must be authenticated")
        dataset = source.retrieval["dataset"]
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["kaggle", "datasets", "download", "-d", dataset, "-p", str(output_dir), "--unzip"], check=True)
        files = tuple(sorted(path for path in output_dir.rglob("*") if path.is_file()))
        return DownloadResult(source.source_id, source.provider, output_dir, files, {"dataset": dataset, "file_count": len(files)})
