from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def create_training_snapshot(snapshot_id: str, *, normalized_manifest: Path, dedup_manifest: Path, split_manifest: Path, snapshot_root: Path, label_mapping_version: str, schema_version: str = "v1", source_ids: list[str] | None = None) -> Path:
    snapshot_dir = Path(snapshot_root) / snapshot_id
    if snapshot_dir.exists():
        raise FileExistsError(f"immutable training snapshot already exists: {snapshot_id}")
    artifacts = {
        "normalized_manifest.csv": Path(normalized_manifest),
        "dedup_manifest.csv": Path(dedup_manifest),
        "split_manifest.csv": Path(split_manifest),
    }
    for name, path in artifacts.items():
        if not path.exists():
            raise FileNotFoundError(f"{name} source missing: {path}")
    snapshot_dir.mkdir(parents=True)
    hashes: dict[str, str] = {}
    for name, path in artifacts.items():
        destination = snapshot_dir / name
        shutil.copy2(path, destination)
        hashes[name] = _sha256(destination)
    metadata = {
        "snapshot_id": snapshot_id,
        "snapshot_type": "TRAINING",
        "status": "SNAPSHOT_READY",
        "source_ids": sorted(source_ids or []),
        "schema_version": schema_version,
        "label_mapping_version": label_mapping_version,
        "artifact_hashes": hashes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (snapshot_dir / "TRAINING_SNAPSHOT.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot_dir
