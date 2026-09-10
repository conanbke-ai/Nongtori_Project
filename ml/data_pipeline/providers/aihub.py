from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ..models import DownloadResult, SourceRecord
from .base import ProviderAdapter


class AIHubAdapter(ProviderAdapter):
    def download(self, source: SourceRecord, output_dir: Path) -> DownloadResult:
        shell = shutil.which("aihubshell")
        if not shell:
            raise RuntimeError("aihubshell is required; install it from the official AI-Hub Open API page")
        api_key = os.getenv("AIHUB_API_KEY")
        if not api_key:
            raise RuntimeError("AIHUB_API_KEY is required")
        dataset_key = str(source.retrieval["dataset_key"])
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        command = [shell, "-aihubapikey", api_key, "-mode", "d", "-datasetkey", dataset_key]
        file_keys = source.retrieval.get("file_keys")
        if file_keys:
            command += ["-filekey", ",".join(map(str, file_keys))]
        subprocess.run(command, cwd=output_dir, check=True)
        files = tuple(sorted(path for path in output_dir.rglob("*") if path.is_file()))
        return DownloadResult(source.source_id, source.provider, output_dir, files, {"dataset_key": dataset_key, "file_count": len(files)})
