from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from .dryad_acquisition import DryadAccessError, file_id, resolve_access_token
from .dryad_image_join_audit import (
    EXPECTED_VIEWS_PER_FRUIT,
    RemoteZipRangeReader,
    _picture_records,
    build_image_join_cache_identity,
    infer_fruit_id,
    load_cached_image_join_report,
)
from .dryad_weight_audit import primary_weight_candidate_ids_from_datasheet


STRICT_CANDIDATE_MANIFEST_SCHEMA_VERSION = 1
STRICT_CANDIDATE_POLICY = "VALID_WITH_CALYX_WEIGHT_AND_EXACTLY_22_PUBLISHED_VIEWS"


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_candidate_manifest_identity(
    datasheet: Path,
    files: list[dict[str, Any]],
    image_join_report: dict[str, Any],
) -> dict[str, Any]:
    join_identity = build_image_join_cache_identity(datasheet, files)
    join_cached_identity = image_join_report.get("cache_identity") or {}
    if join_cached_identity.get("fingerprint") != join_identity["fingerprint"]:
        raise DryadAccessError("Image-join audit cache does not match current Dryad source identity")

    identity = {
        "schema_version": STRICT_CANDIDATE_MANIFEST_SCHEMA_VERSION,
        "policy": STRICT_CANDIDATE_POLICY,
        "image_join_fingerprint": join_identity["fingerprint"],
        "expected_views_per_fruit": EXPECTED_VIEWS_PER_FRUIT,
    }
    return {
        **identity,
        "fingerprint": _canonical_json_sha256(identity),
    }


def load_cached_candidate_manifest(
    output: Path,
    *,
    datasheet: Path,
    files: list[dict[str, Any]],
    image_join_report: dict[str, Any],
) -> dict[str, Any] | None:
    output = Path(output)
    if not output.exists():
        return None
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    current = build_candidate_manifest_identity(datasheet, files, image_join_report)
    cached = payload.get("cache_identity")
    if not isinstance(cached, dict):
        return None
    if cached.get("fingerprint") != current["fingerprint"]:
        return None
    return payload


def _zip_info_rows(
    record: dict[str, Any],
    *,
    access_token: str,
    known_ids: set[str],
    strict_ids: set[str],
    timeout: int,
    min_chunk_size: int,
) -> list[dict[str, Any]]:
    reader = RemoteZipRangeReader(
        record,
        access_token=access_token,
        timeout=timeout,
        min_chunk_size=min_chunk_size,
    )
    archive_path = str(record.get("path") or "")
    archive_id = file_id(record)
    archive_digest = str(record.get("digest") or "")
    rows: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(reader) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                fruit_id, status = infer_fruit_id(info.filename, known_ids)
                if status != "MATCHED" or fruit_id not in strict_ids:
                    continue
                rows.append(
                    {
                        "fruit_id": fruit_id,
                        "archive_path": archive_path,
                        "archive_file_id": archive_id,
                        "archive_sha256": archive_digest,
                        "filename": info.filename,
                        "file_size": int(info.file_size),
                        "compress_size": int(info.compress_size),
                        "compress_type": int(info.compress_type),
                        "crc32": f"{int(info.CRC) & 0xFFFFFFFF:08x}",
                        "header_offset": int(info.header_offset),
                    }
                )
    except zipfile.BadZipFile as exc:
        raise DryadAccessError(
            f"Cannot read ZIP central directory for {archive_path}: {exc}"
        ) from exc
    return rows


def build_strict_candidate_manifest(
    datasheet: Path,
    files: list[dict[str, Any]],
    image_join_report: dict[str, Any],
    *,
    timeout: int = 120,
    min_chunk_size: int = 1024 * 1024,
) -> dict[str, Any]:
    cached_join = image_join_report.get("audit") or {}
    view_counts = cached_join.get("view_counts_by_fruit")
    if not isinstance(view_counts, dict):
        raise DryadAccessError("Image-join audit lacks per-fruit view counts")

    primary_ids = set(primary_weight_candidate_ids_from_datasheet(datasheet))
    strict_ids = {
        fruit_id
        for fruit_id in primary_ids
        if int(view_counts.get(fruit_id, 0)) == EXPECTED_VIEWS_PER_FRUIT
    }
    known_ids = set(view_counts)

    expected_strict_count = int(
        ((cached_join.get("strict_training_candidate_summary") or {}).get(
            "strict_22_view_weight_fruit_count"
        ))
        or len(strict_ids)
    )
    if len(strict_ids) != expected_strict_count:
        raise DryadAccessError(
            f"Strict candidate count mismatch: derived {len(strict_ids)}, expected {expected_strict_count}"
        )

    records = _picture_records(files)
    if len(records) != 7:
        raise DryadAccessError(f"Expected 7 picture archives, found {len(records)}")

    token = resolve_access_token(timeout=min(timeout, 60))
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.extend(
            _zip_info_rows(
                record,
                access_token=token,
                known_ids=known_ids,
                strict_ids=strict_ids,
                timeout=timeout,
                min_chunk_size=min_chunk_size,
            )
        )

    rows.sort(key=lambda row: (row["fruit_id"], row["archive_path"], row["filename"]))
    by_fruit: dict[str, int] = {}
    for row in rows:
        by_fruit[row["fruit_id"]] = by_fruit.get(row["fruit_id"], 0) + 1

    wrong_counts = {
        fruit_id: count
        for fruit_id, count in sorted(by_fruit.items())
        if count != EXPECTED_VIEWS_PER_FRUIT
    }
    missing = sorted(strict_ids - set(by_fruit))
    expected_images = len(strict_ids) * EXPECTED_VIEWS_PER_FRUIT

    status = (
        "STRICT_CANDIDATE_MANIFEST_VERIFIED"
        if len(rows) == expected_images and not wrong_counts and not missing
        else "REVIEW_REQUIRED"
    )

    row_identity = [
        {
            "fruit_id": row["fruit_id"],
            "archive_path": row["archive_path"],
            "archive_sha256": row["archive_sha256"],
            "filename": row["filename"],
            "file_size": row["file_size"],
            "compress_size": row["compress_size"],
            "compress_type": row["compress_type"],
            "crc32": row["crc32"],
            "header_offset": row["header_offset"],
        }
        for row in rows
    ]

    return {
        "status": status,
        "policy": STRICT_CANDIDATE_POLICY,
        "cache_identity": build_candidate_manifest_identity(
            datasheet,
            files,
            image_join_report,
        ),
        "fruit_count": len(strict_ids),
        "expected_views_per_fruit": EXPECTED_VIEWS_PER_FRUIT,
        "expected_image_count": expected_images,
        "image_count": len(rows),
        "wrong_view_count_fruit_count": len(wrong_counts),
        "wrong_view_counts": wrong_counts,
        "missing_fruit_ids": missing,
        "rows_sha256": _canonical_json_sha256(row_identity),
        "rows": rows,
    }


def write_candidate_manifest(report: dict[str, Any], output: Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
