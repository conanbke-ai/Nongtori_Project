from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_snapshot(snapshot_id: str, source_id: str, source_version: str, audit_dir: Path, snapshot_root: Path, *, schema_version: str = "v1", label_mapping_version: str = "unmapped") -> Path:
    audit_dir = Path(audit_dir)
    snapshot_dir = Path(snapshot_root) / snapshot_id
    if snapshot_dir.exists():
        raise FileExistsError(f"immutable snapshot already exists: {snapshot_id}")
    manifest = audit_dir / "manifest.csv"
    audit = audit_dir / "audit.json"
    if not manifest.exists() or not audit.exists():
        raise FileNotFoundError("audit manifest/report required before snapshot")
    snapshot_dir.mkdir(parents=True)
    shutil.copy2(manifest, snapshot_dir / "manifest.csv")
    shutil.copy2(audit, snapshot_dir / "audit.json")
    manifest_bytes = manifest.read_bytes()
    metadata = {
        "snapshot_id": snapshot_id,
        "source_ids": [source_id],
        "source_versions": [source_version],
        "schema_version": schema_version,
        "label_mapping_version": label_mapping_version,
        "manifest_hash": sha256_bytes(manifest_bytes),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (snapshot_dir / "SNAPSHOT.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot_dir
