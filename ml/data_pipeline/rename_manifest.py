from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
BLOCKING_STATUSES = {
    "FILE_COUNT_MISMATCH",
    "SHEET_ROW_COUNT_MISMATCH",
    "MISSING_SOURCE_FILE",
    "EXTRA_SOURCE_FILE",
    "EMPTY_FINAL_NAME",
    "DUPLICATE_FINAL_NAME",
    "DUPLICATE_ORIGINAL_NO",
    "UNMATCHED_ORIGINAL_NO",
    "UNSUPPORTED_EXTENSION",
    "TARGET_FILE_ALREADY_EXISTS",
    "INVALID_METADATA",
}
MANIFEST_COLUMNS = [
    "farm_id", "capture_session_id", "source_file", "source_original_no", "target_final_name",
    "match_strategy", "validation_status", "content_sha256", "working_object_path",
    "working_session_path", "rollback_source_file", "rollback_target_file",
]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_original_no(value: Any) -> str:
    text = _text(value)
    return Path(text).stem.lower() if text else ""


@dataclass(frozen=True)
class AssetCandidate:
    path: Path
    original_no: str


def list_assets(source_dir: Path) -> list[AssetCandidate]:
    source_dir = Path(source_dir)
    candidates: list[AssetCandidate] = []
    for path in sorted((p for p in source_dir.iterdir() if p.is_file()), key=lambda p: p.name.lower()):
        candidates.append(AssetCandidate(path=path, original_no=normalize_original_no(path.name)))
    return candidates


def _active_metadata_rows(rows: Iterable[dict[str, Any]], *, farm_id: str) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for row in rows:
        if not _text(row.get("ID")):
            continue
        if _text(row.get("Farm")) != farm_id:
            continue
        if not _text(row.get("Original_No")) and not _text(row.get("Final_Name")):
            continue
        active.append(dict(row))
    return active


def preflight_rename(metadata_rows: Iterable[dict[str, Any]], source_dir: Path, *, farm_id: str, capture_session_id: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows = _active_metadata_rows(metadata_rows, farm_id=farm_id)
    assets = list_assets(source_dir)
    statuses: list[str] = []

    original_counts: dict[str, int] = {}
    final_counts: dict[str, int] = {}
    for row in rows:
        original = normalize_original_no(row.get("Original_No"))
        final_name = _text(row.get("Final_Name"))
        if not original:
            statuses.append("INVALID_METADATA")
        else:
            original_counts[original] = original_counts.get(original, 0) + 1
        if not final_name:
            statuses.append("EMPTY_FINAL_NAME")
        else:
            final_counts[final_name.lower()] = final_counts.get(final_name.lower(), 0) + 1
    if any(v > 1 for v in original_counts.values()):
        statuses.append("DUPLICATE_ORIGINAL_NO")
    if any(v > 1 for v in final_counts.values()):
        statuses.append("DUPLICATE_FINAL_NAME")

    asset_by_original: dict[str, list[Path]] = {}
    for asset in assets:
        asset_by_original.setdefault(asset.original_no, []).append(asset.path)
        if asset.path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            statuses.append("UNSUPPORTED_EXTENSION")

    manifests: list[dict[str, str]] = []
    matched_paths: set[Path] = set()
    unmatched_rows: list[dict[str, Any]] = []

    for row in rows:
        original = normalize_original_no(row.get("Original_No"))
        final_name = _text(row.get("Final_Name"))
        options = asset_by_original.get(original, [])
        if len(options) == 1:
            path = options[0]
            matched_paths.add(path)
            manifests.append({
                "farm_id": farm_id,
                "capture_session_id": capture_session_id,
                "source_file": path.name,
                "source_original_no": original,
                "target_final_name": final_name,
                "match_strategy": "ORIGINAL_NO_EXACT",
                "validation_status": "READY_TO_RENAME",
                "content_sha256": sha256_file(path),
                "working_object_path": "",
                "working_session_path": "",
                "rollback_source_file": final_name,
                "rollback_target_file": path.name,
            })
        else:
            unmatched_rows.append(row)

    remaining_assets = [a.path for a in assets if a.path not in matched_paths]
    if unmatched_rows:
        if len(unmatched_rows) == len(remaining_assets) and remaining_assets:
            for row, path in zip(unmatched_rows, sorted(remaining_assets, key=lambda p: p.name.lower())):
                manifests.append({
                    "farm_id": farm_id,
                    "capture_session_id": capture_session_id,
                    "source_file": path.name,
                    "source_original_no": normalize_original_no(row.get("Original_No")),
                    "target_final_name": _text(row.get("Final_Name")),
                    "match_strategy": "NATURAL_ORDER_FALLBACK",
                    "validation_status": "READY_WITH_WARNING",
                    "content_sha256": sha256_file(path),
                    "working_object_path": "",
                    "working_session_path": "",
                    "rollback_source_file": _text(row.get("Final_Name")),
                    "rollback_target_file": path.name,
                })
            remaining_assets = []
        else:
            statuses.append("UNMATCHED_ORIGINAL_NO")

    if len(rows) != len(assets):
        statuses.extend(["FILE_COUNT_MISMATCH", "SHEET_ROW_COUNT_MISMATCH"])
    if remaining_assets:
        statuses.append("EXTRA_SOURCE_FILE")
    if any(m["source_file"] == "" for m in manifests) or len(manifests) < len(rows):
        statuses.append("MISSING_SOURCE_FILE")

    blocking = sorted(set(statuses) & BLOCKING_STATUSES)
    summary = {
        "farm_id": farm_id,
        "capture_session_id": capture_session_id,
        "sheet_rows": len(rows),
        "source_files": len(assets),
        "matched": len(manifests),
        "blocking_errors": blocking,
        "status": "PREFLIGHT_BLOCKED" if blocking else "PREFLIGHT_PASSED",
    }
    if blocking:
        for manifest in manifests:
            manifest["validation_status"] = "BLOCKED"
    return manifests, summary


def write_rename_manifest(rows: Iterable[dict[str, str]], output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in MANIFEST_COLUMNS})
    return output_path


def write_preflight_summary(summary: dict[str, Any], output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
