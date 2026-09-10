from __future__ import annotations

import csv
import os
import shutil
from pathlib import Path
from typing import Iterable

from .rename_manifest import MANIFEST_COLUMNS


def _safe_link_or_copy(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return "REUSED"
    try:
        os.link(source, target)
        return "HARDLINKED"
    except OSError:
        shutil.copy2(source, target)
        return "COPIED"


def materialize_working_assets(
    manifest_rows: Iterable[dict[str, str]],
    source_dir: Path,
    object_store_root: Path,
    session_root: Path,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    source_dir = Path(source_dir)
    object_store_root = Path(object_store_root)
    session_root = Path(session_root)
    rows = [dict(row) for row in manifest_rows]
    if not rows:
        raise ValueError("empty rename manifest cannot be materialized")
    if any(row.get("validation_status") == "BLOCKED" for row in rows):
        raise ValueError("blocked rename manifest cannot be materialized")

    counts = {"COPIED": 0, "HARDLINKED": 0, "REUSED": 0, "SESSION_LINKED": 0}
    for row in rows:
        digest = (row.get("content_sha256") or "").strip().lower()
        source_name = (row.get("source_file") or "").strip()
        final_name = (row.get("target_final_name") or "").strip()
        farm_id = (row.get("farm_id") or "").strip()
        session_id = (row.get("capture_session_id") or "").strip()
        if not digest or len(digest) != 64:
            raise ValueError(f"valid sha256 required for {source_name}")
        if not source_name or not final_name or not farm_id or not session_id:
            raise ValueError("source_file, target_final_name, farm_id and capture_session_id are required")

        source = source_dir / source_name
        if not source.exists():
            raise FileNotFoundError(source)
        suffix = source.suffix.lower()
        object_path = object_store_root / digest[:2] / f"{digest}{suffix}"
        state = _safe_link_or_copy(source, object_path)
        counts[state] += 1

        session_path = session_root / farm_id / session_id / final_name
        if session_path.exists():
            if session_path.samefile(object_path):
                pass
            else:
                raise FileExistsError(f"working session target already exists: {session_path}")
        else:
            session_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(object_path, session_path)
            except OSError:
                shutil.copy2(object_path, session_path)
            counts["SESSION_LINKED"] += 1

        row["working_object_path"] = str(object_path)
        row["working_session_path"] = str(session_path)
    return rows, counts


def read_manifest(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_materialized_manifest(rows: Iterable[dict[str, str]], output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in MANIFEST_COLUMNS})
    return output_path


def write_rollback_manifest(rows: Iterable[dict[str, str]], output_path: Path) -> Path:
    fieldnames = ["farm_id", "capture_session_id", "sample_id", "source_asset_key", "working_session_path", "rollback_source_file", "rollback_target_file", "content_sha256"]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return output_path
