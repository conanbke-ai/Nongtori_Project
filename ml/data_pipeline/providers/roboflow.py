from __future__ import annotations

import os
from pathlib import Path

from ..models import DownloadResult, SourceRecord
from .base import ProviderAdapter


class RoboflowAdapter(ProviderAdapter):
    """Download a pinned public Roboflow Universe dataset version."""

    @staticmethod
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

    def download(self, source: SourceRecord, output_dir: Path) -> DownloadResult:
        self._load_env_local()
        env_var = str(source.retrieval.get("env_var") or "ROBOFLOW_API_KEY")
        api_key = os.environ.get(env_var)
        if not api_key:
            raise RuntimeError(
                f"Roboflow API key is missing. Put {env_var}=... in .env.local. "
                "Do not commit or paste the key into source files."
            )

        try:
            from roboflow import Roboflow
        except ImportError as exc:
            raise RuntimeError(
                "roboflow package is required: python -m pip install roboflow"
            ) from exc

        workspace = str(source.retrieval["workspace"])
        project_slug = str(source.retrieval["project"])
        version_number = int(
            source.retrieval.get("version_number")
            or source.version_or_revision
            or 0
        )
        if version_number <= 0:
            raise RuntimeError(
                f"{source.source_id} must pin a positive Roboflow version_number"
            )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        rf = Roboflow(api_key=api_key)
        project = rf.workspace(workspace).project(project_slug)
        version = project.version(version_number)
        dataset = version.download("yolov8", location=str(output_dir), overwrite=True)

        root = Path(getattr(dataset, "location", output_dir))
        if not root.exists():
            root = output_dir

        files = tuple(sorted(path for path in root.rglob("*") if path.is_file()))
        if not files:
            raise RuntimeError(
                f"Roboflow returned no files for {workspace}/{project_slug}/{version_number}"
            )

        return DownloadResult(
            source.source_id,
            source.provider,
            root,
            files,
            {
                "workspace": workspace,
                "project": project_slug,
                "version_number": version_number,
                "format": "yolov8",
                "file_count": len(files),
            },
        )
