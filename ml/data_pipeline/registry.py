from __future__ import annotations

import json
from pathlib import Path

from .models import SourceRecord


class DatasetRegistry:
    def __init__(self, source_dir: Path):
        self.source_dir = Path(source_dir)
        self._sources: dict[str, SourceRecord] = {}
        self.reload()

    def reload(self) -> None:
        sources: dict[str, SourceRecord] = {}
        for path in sorted(self.source_dir.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            source = SourceRecord.from_dict(raw)
            if source.source_id in sources:
                raise ValueError(f"duplicate source_id: {source.source_id}")
            sources[source.source_id] = source
        self._sources = sources

    def get(self, source_id: str) -> SourceRecord:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise KeyError(f"unknown source_id: {source_id}") from exc

    def list(self) -> list[SourceRecord]:
        return [self._sources[key] for key in sorted(self._sources)]
