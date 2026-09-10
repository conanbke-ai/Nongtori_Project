from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SourceStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    DOWNLOADED = "DOWNLOADED"
    AUDITED = "AUDITED"
    APPROVED = "APPROVED"
    NORMALIZED = "NORMALIZED"
    SNAPSHOT_READY = "SNAPSHOT_READY"
    IN_USE = "IN_USE"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"
    SUPERSEDED = "SUPERSEDED"
    NON_COMMERCIAL_ONLY = "NON_COMMERCIAL_ONLY"


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_type: str
    provider: str
    title: str
    original_url: str
    retrieval: dict[str, Any]
    version_or_revision: str | None = None
    license: str | None = None
    license_checked_at: str | None = None
    redistribution_allowed: str = "unknown"
    commercial_use: str = "review_required"
    status: SourceStatus = SourceStatus.DISCOVERED
    original_labels: list[str] = field(default_factory=list)
    nongtori_mapping: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SourceRecord":
        return cls(
            source_id=raw["source_id"],
            source_type=raw.get("source_type", "dataset"),
            provider=raw["provider"],
            title=raw["title"],
            original_url=raw["original_url"],
            retrieval=dict(raw.get("retrieval", {})),
            version_or_revision=raw.get("version_or_revision"),
            license=raw.get("license"),
            license_checked_at=raw.get("license_checked_at"),
            redistribution_allowed=raw.get("redistribution_allowed", "unknown"),
            commercial_use=raw.get("commercial_use", "review_required"),
            status=SourceStatus(raw.get("status", "DISCOVERED")),
            original_labels=list(raw.get("original_labels", [])),
            nongtori_mapping=dict(raw.get("nongtori_mapping", {})),
            notes=raw.get("notes", ""),
        )


@dataclass(frozen=True)
class DownloadResult:
    source_id: str
    provider: str
    output_dir: Path
    files: tuple[Path, ...]
    metadata: dict[str, Any]
