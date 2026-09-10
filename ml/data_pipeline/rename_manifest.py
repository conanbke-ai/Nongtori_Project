from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .farm_contract import resolve_farm_scope

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
BLOCKING_STATUSES = {
    "SOURCE_ASSET_CONTEXT_CONFLICT", "AMBIGUOUS_SOURCE_FILE", "SOURCE_ASSET_COUNT_MISMATCH",
    "MISSING_SOURCE_FILE", "EXTRA_SOURCE_FILE", "EMPTY_FINAL_NAME", "DUPLICATE_FINAL_NAME",
    "UNMATCHED_ORIGINAL_NO", "UNSUPPORTED_EXTENSION", "TARGET_FILE_ALREADY_EXISTS", "INVALID_METADATA",
}
MANIFEST_COLUMNS = [
    "farm_id", "capture_session_id", "sample_id", "source_asset_key", "source_file",
    "source_original_no", "target_final_name", "asset_relation", "match_strategy",
    "validation_status", "content_sha256", "working_object_path", "working_session_path",
    "rollback_source_file", "rollback_target_file",
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
    return [AssetCandidate(path=p, original_no=normalize_original_no(p.name))
            for p in sorted((p for p in source_dir.iterdir() if p.is_file()), key=lambda p: p.name.lower())]


def _active_metadata_rows(rows: Iterable[dict[str, Any]], *, farm_scope: str) -> list[dict[str, Any]]:
    members = resolve_farm_scope(farm_scope)
    active: list[dict[str, Any]] = []
    for row in rows:
        if not _text(row.get("ID")):
            continue
        if _text(row.get("Farm")).upper() not in members:
            continue
        if not _text(row.get("Original_No")) and not _text(row.get("Final_Name")):
            continue
        active.append(dict(row))
    return active


def _source_asset_key(*, farm_code: str, capture_session_id: str, original_no: str) -> str:
    return f"{farm_code}:{capture_session_id}:{original_no}"


def _context_signature(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (_text(row.get("Farm")).upper(), _text(row.get("Date")), _text(row.get("Zone")), _text(row.get("DataType")))


def preflight_rename(metadata_rows: Iterable[dict[str, Any]], source_dir: Path, *, farm_id: str, capture_session_id: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
    scope = _text(farm_id).upper()
    members = resolve_farm_scope(scope, field_name="farm_id/farm_scope")
    rows = _active_metadata_rows(metadata_rows, farm_scope=scope)
    assets = list_assets(source_dir)
    statuses: list[str] = []

    rows_by_original: dict[str, list[dict[str, Any]]] = {}
    final_counts: dict[str, int] = {}
    for row in rows:
        original = normalize_original_no(row.get("Original_No"))
        final_name = _text(row.get("Final_Name"))
        if not original:
            statuses.append("INVALID_METADATA")
        else:
            rows_by_original.setdefault(original, []).append(row)
        if not final_name:
            statuses.append("EMPTY_FINAL_NAME")
        else:
            final_counts[final_name.lower()] = final_counts.get(final_name.lower(), 0) + 1
    if any(v > 1 for v in final_counts.values()):
        statuses.append("DUPLICATE_FINAL_NAME")

    conflicting_originals: set[str] = set()
    for original, group in rows_by_original.items():
        contexts = {_context_signature(row) for row in group}
        if len(contexts) > 1:
            conflicting_originals.add(original)
            statuses.append("SOURCE_ASSET_CONTEXT_CONFLICT")

    asset_by_original: dict[str, list[Path]] = {}
    for asset in assets:
        asset_by_original.setdefault(asset.original_no, []).append(asset.path)
        if asset.path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            statuses.append("UNSUPPORTED_EXTENSION")
    if any(len(paths) > 1 for paths in asset_by_original.values()):
        statuses.append("AMBIGUOUS_SOURCE_FILE")

    manifests: list[dict[str, str]] = []
    matched_paths: set[Path] = set()
    unmatched_originals: list[str] = []

    def append_group(group: list[dict[str, Any]], path: Path, strategy: str, validation: str) -> None:
        digest = sha256_file(path)
        relation = "SHARED_SOURCE_ASSET" if len(group) > 1 else "ONE_TO_ONE_SOURCE_ASSET"
        original = normalize_original_no(group[0].get("Original_No"))
        for row in group:
            actual_farm = _text(row.get("Farm")).upper()
            asset_key = _source_asset_key(farm_code=actual_farm, capture_session_id=capture_session_id, original_no=original)
            final_name = _text(row.get("Final_Name"))
            manifests.append({
                "farm_id": actual_farm, "capture_session_id": capture_session_id,
                "sample_id": _text(row.get("ID")), "source_asset_key": asset_key,
                "source_file": path.name, "source_original_no": original, "target_final_name": final_name,
                "asset_relation": relation, "match_strategy": strategy, "validation_status": validation,
                "content_sha256": digest, "working_object_path": "", "working_session_path": "",
                "rollback_source_file": final_name, "rollback_target_file": path.name,
            })

    for original, group in rows_by_original.items():
        if original in conflicting_originals:
            continue
        options = asset_by_original.get(original, [])
        if len(options) == 1:
            matched_paths.add(options[0])
            append_group(group, options[0], "ORIGINAL_NO_EXACT", "READY_TO_RENAME")
        else:
            unmatched_originals.append(original)

    remaining_assets = [a.path for a in assets if a.path not in matched_paths]
    if unmatched_originals:
        fallback_groups = [rows_by_original[o] for o in unmatched_originals if o not in conflicting_originals]
        if len(fallback_groups) == len(remaining_assets) and remaining_assets:
            for group, path in zip(fallback_groups, sorted(remaining_assets, key=lambda p: p.name.lower())):
                append_group(group, path, "NATURAL_ORDER_FALLBACK", "READY_WITH_WARNING")
                matched_paths.add(path)
            remaining_assets = []
        else:
            statuses.append("UNMATCHED_ORIGINAL_NO")

    expected_source_assets = len(rows_by_original)
    if expected_source_assets != len(assets):
        statuses.append("SOURCE_ASSET_COUNT_MISMATCH")
    if remaining_assets:
        statuses.append("EXTRA_SOURCE_FILE")
    represented_samples = {m["sample_id"] for m in manifests}
    if len(represented_samples) < len(rows):
        statuses.append("MISSING_SOURCE_FILE")

    blocking = sorted(set(statuses) & BLOCKING_STATUSES)
    summary = {
        "farm_scope": scope, "resolved_farm_codes": sorted(members), "capture_session_id": capture_session_id,
        "sheet_rows": len(rows), "expected_source_assets": expected_source_assets, "source_files": len(assets),
        "manifest_rows": len(manifests), "shared_asset_groups": sum(1 for g in rows_by_original.values() if len(g) > 1),
        "blocking_errors": blocking, "status": "PREFLIGHT_BLOCKED" if blocking else "PREFLIGHT_PASSED",
    }
    if blocking:
        for manifest in manifests:
            manifest["validation_status"] = "BLOCKED"
    return manifests, summary


def write_rename_manifest(rows: Iterable[dict[str, str]], output_path: Path) -> Path:
    output_path = Path(output_path); output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS); writer.writeheader()
        for row in rows: writer.writerow({k: row.get(k, "") for k in MANIFEST_COLUMNS})
    return output_path


def write_preflight_summary(summary: dict[str, Any], output_path: Path) -> Path:
    output_path = Path(output_path); output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
