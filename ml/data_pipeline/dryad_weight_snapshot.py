from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .dryad_acquisition import DryadAccessError, sha256_file
from .dryad_materialization import MATERIALIZED_STATUS, load_candidate_manifest
from .dryad_weight_audit import (
    EXPECTED_VIEWS_PER_FRUIT,
    primary_weight_records_from_datasheet,
)

SNAPSHOT_SCHEMA_VERSION = 1
DEFAULT_SNAPSHOT_ID = "WEIGHT-DRYAD-V001"
DEFAULT_SPLIT_SEED = "dryad-weight-v1"
SOURCE_ID = "DATA-QUAL-002"


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DryadAccessError(f"Cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DryadAccessError(f"{label} must be a JSON object")
    return payload


def _validate_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    ratios = (train_ratio, val_ratio, test_ratio)
    if min(ratios) < 0 or abs(sum(ratios) - 1.0) > 1e-9:
        raise DryadAccessError("split ratios must be non-negative and sum to 1")


def _split_sizes(
    count: int,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> dict[str, int]:
    _validate_ratios(train_ratio, val_ratio, test_ratio)
    names = ("train", "validation", "test")
    ratios = (train_ratio, val_ratio, test_ratio)
    raw = [count * ratio for ratio in ratios]
    sizes = [int(value) for value in raw]
    remaining = count - sum(sizes)
    order = sorted(
        range(len(names)),
        key=lambda index: (raw[index] - sizes[index], -index),
        reverse=True,
    )
    for index in order[:remaining]:
        sizes[index] += 1
    return dict(zip(names, sizes, strict=True))


def _assign_splits(
    fruit_ids: list[str],
    *,
    seed: str,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> dict[str, str]:
    sizes = _split_sizes(len(fruit_ids), train_ratio, val_ratio, test_ratio)
    ordered = sorted(
        fruit_ids,
        key=lambda fruit_id: (
            hashlib.sha256(f"{seed}|{fruit_id}".encode("utf-8")).hexdigest(),
            fruit_id,
        ),
    )
    train_end = sizes["train"]
    validation_end = train_end + sizes["validation"]
    assignments: dict[str, str] = {}
    for index, fruit_id in enumerate(ordered):
        if index < train_end:
            split = "train"
        elif index < validation_end:
            split = "validation"
        else:
            split = "test"
        assignments[fruit_id] = split
    return assignments


def _safe_asset_path(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(str(relative_path).replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise DryadAccessError(f"Unsafe materialized relative path: {relative_path!r}")
    return Path(root, *relative.parts)


def _weight_grade(weight_g: float) -> str:
    if weight_g >= 22:
        return "SP_WEIGHT"
    if weight_g >= 16:
        return "HI_WEIGHT"
    if weight_g >= 12:
        return "MD_WEIGHT"
    return "JM_WEIGHT_CANDIDATE"


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _canonical_assignment_sha256(assignments: dict[str, str]) -> str:
    payload = "\n".join(
        f"{fruit_id},{assignments[fruit_id]}"
        for fruit_id in sorted(assignments)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_asset_rows_sha256(rows: list[dict[str, Any]]) -> str:
    payload = "\n".join(
        "|".join(
            [
                str(row["fruit_id"]),
                str(row["split"]),
                str(row["relative_path"]),
                str(row["sha256"]),
            ]
        )
        for row in sorted(
            rows,
            key=lambda item: (
                str(item["fruit_id"]),
                str(item["relative_path"]),
            ),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def freeze_dryad_weight_snapshot(
    *,
    candidate_manifest: Path,
    materialized_manifest: Path,
    datasheet: Path,
    snapshot_root: Path,
    snapshot_id: str = DEFAULT_SNAPSHOT_ID,
    seed: str = DEFAULT_SPLIT_SEED,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    weight_loader: Callable[[Path], dict[str, dict[str, Any]]] = primary_weight_records_from_datasheet,
) -> dict[str, Any]:
    candidate_manifest = Path(candidate_manifest)
    materialized_manifest = Path(materialized_manifest)
    datasheet = Path(datasheet)
    snapshot_root = Path(snapshot_root)
    snapshot_dir = snapshot_root / snapshot_id
    temp_dir = snapshot_root / f".{snapshot_id}.tmp"

    if snapshot_dir.exists():
        raise DryadAccessError(
            f"immutable Dryad weight snapshot already exists: {snapshot_dir}"
        )
    if not datasheet.exists():
        raise DryadAccessError(f"Dryad datasheet is missing: {datasheet}")

    candidate = load_candidate_manifest(candidate_manifest)
    materialized = _load_json(materialized_manifest, "materialized asset manifest")
    if materialized.get("status") != MATERIALIZED_STATUS:
        raise DryadAccessError(
            "Dryad weight snapshot requires complete materialization "
            f"({MATERIALIZED_STATUS}); got {materialized.get('status')!r}"
        )
    if materialized.get("candidate_rows_sha256") != candidate.get("rows_sha256"):
        raise DryadAccessError("materialized asset manifest does not match candidate rows")
    expected_images = int(candidate.get("image_count") or 0)
    if int(materialized.get("candidate_image_count") or 0) != expected_images:
        raise DryadAccessError("materialized candidate_image_count does not match candidate")
    files = materialized.get("files")
    if not isinstance(files, list) or len(files) != expected_images:
        raise DryadAccessError("materialized asset file list is incomplete")
    if int(materialized.get("verified_file_count") or 0) != expected_images:
        raise DryadAccessError("materialized verified_file_count is incomplete")

    candidate_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    views_by_fruit: Counter[str] = Counter()
    for row in candidate["rows"]:
        key = (str(row.get("archive_path") or ""), str(row.get("filename") or ""))
        if not all(key):
            raise DryadAccessError("candidate row is missing archive_path or filename")
        if key in candidate_by_key:
            raise DryadAccessError(f"duplicate candidate asset key: {key}")
        fruit_id = str(row.get("fruit_id") or "").strip()
        if not fruit_id:
            raise DryadAccessError("candidate row is missing fruit_id")
        candidate_by_key[key] = row
        views_by_fruit[fruit_id] += 1

    fruit_ids = sorted(views_by_fruit)
    expected_fruits = int(candidate.get("fruit_count") or 0)
    if len(fruit_ids) != expected_fruits:
        raise DryadAccessError(
            f"candidate fruit_count mismatch: {len(fruit_ids)}/{expected_fruits}"
        )
    wrong_views = {
        fruit_id: count
        for fruit_id, count in views_by_fruit.items()
        if count != EXPECTED_VIEWS_PER_FRUIT
    }
    if wrong_views:
        sample = dict(list(sorted(wrong_views.items()))[:10])
        raise DryadAccessError(
            f"strict candidate no longer has {EXPECTED_VIEWS_PER_FRUIT} views per fruit: {sample}"
        )

    materialized_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in files:
        if not isinstance(row, dict):
            raise DryadAccessError("materialized file row is not an object")
        key = (str(row.get("archive_path") or ""), str(row.get("filename") or ""))
        if not all(key):
            raise DryadAccessError("materialized file row is missing archive_path or filename")
        if key in materialized_by_key:
            raise DryadAccessError(f"duplicate materialized asset key: {key}")
        materialized_by_key[key] = row
    if set(materialized_by_key) != set(candidate_by_key):
        missing = sorted(set(candidate_by_key) - set(materialized_by_key))[:10]
        unexpected = sorted(set(materialized_by_key) - set(candidate_by_key))[:10]
        raise DryadAccessError(
            f"candidate/materialized asset identity mismatch; missing={missing}, unexpected={unexpected}"
        )

    weights = weight_loader(datasheet)
    missing_weights = [fruit_id for fruit_id in fruit_ids if fruit_id not in weights]
    if missing_weights:
        raise DryadAccessError(
            f"Dryad datasheet is missing strict-candidate primary weights: {missing_weights[:10]}"
        )

    assignments = _assign_splits(
        fruit_ids,
        seed=seed,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
    )
    split_fruit_counts = Counter(assignments.values())
    expected_split_sizes = _split_sizes(
        len(fruit_ids),
        train_ratio,
        val_ratio,
        test_ratio,
    )
    if dict(split_fruit_counts) != {
        key: value for key, value in expected_split_sizes.items() if value
    }:
        raise DryadAccessError("deterministic FRUIT_ID split count mismatch")

    asset_root_text = str(materialized.get("root") or "").strip()
    if not asset_root_text:
        raise DryadAccessError("materialized asset manifest has no root")
    asset_root = Path(asset_root_text)
    if not asset_root.exists() or not asset_root.is_dir():
        raise DryadAccessError(f"materialized asset root is missing: {asset_root}")

    sample_rows: list[dict[str, Any]] = []
    digest_split: dict[str, str] = {}
    split_image_counts: Counter[str] = Counter()
    for key in sorted(candidate_by_key):
        candidate_row = candidate_by_key[key]
        file_row = materialized_by_key[key]
        candidate_fruit_id = str(candidate_row["fruit_id"])
        materialized_fruit_id = str(file_row.get("fruit_id") or "")
        if materialized_fruit_id != candidate_fruit_id:
            raise DryadAccessError(
                f"fruit_id mismatch for {key}: {materialized_fruit_id!r} != {candidate_fruit_id!r}"
            )
        relative_path = str(file_row.get("relative_path") or "")
        asset_path = _safe_asset_path(asset_root, relative_path)
        if not asset_path.exists() or not asset_path.is_file():
            raise DryadAccessError(f"materialized asset missing: {asset_path}")
        expected_size = int(file_row.get("size") or -1)
        if asset_path.stat().st_size != expected_size:
            raise DryadAccessError(f"materialized asset size changed: {asset_path}")
        expected_sha = str(file_row.get("sha256") or "").lower()
        actual_sha = sha256_file(asset_path)
        if len(expected_sha) != 64 or actual_sha != expected_sha:
            raise DryadAccessError(f"materialized asset SHA-256 changed: {asset_path}")

        split = assignments[candidate_fruit_id]
        previous_split = digest_split.setdefault(actual_sha, split)
        if previous_split != split:
            raise DryadAccessError(
                f"exact duplicate leakage across splits: sha256 {actual_sha}"
            )

        weight_record = weights[candidate_fruit_id]
        primary_weight = float(weight_record["weight_with_calyx_g"])
        if primary_weight <= 0:
            raise DryadAccessError(
                f"invalid primary weight for fruit {candidate_fruit_id}: {primary_weight}"
            )

        sample_rows.append(
            {
                "source_id": SOURCE_ID,
                "fruit_id": candidate_fruit_id,
                "atomic_group": candidate_fruit_id,
                "split": split,
                "weight_with_calyx_g": primary_weight,
                "weight_without_calyx_g": weight_record.get("weight_without_calyx_g", ""),
                "width_mm": weight_record.get("width_mm", ""),
                "height_mm": weight_record.get("height_mm", ""),
                "variety": weight_record.get("variety", ""),
                "shape": weight_record.get("shape", ""),
                "weight_grade": _weight_grade(primary_weight),
                "archive_path": key[0],
                "filename": key[1],
                "relative_path": relative_path,
                "size": expected_size,
                "crc32": str(file_row.get("crc32") or "").lower(),
                "sha256": actual_sha,
            }
        )
        split_image_counts[split] += 1

    split_rows = [
        {
            "source_id": SOURCE_ID,
            "fruit_id": fruit_id,
            "split": assignments[fruit_id],
            "weight_with_calyx_g": float(weights[fruit_id]["weight_with_calyx_g"]),
            "weight_without_calyx_g": weights[fruit_id].get("weight_without_calyx_g", ""),
            "width_mm": weights[fruit_id].get("width_mm", ""),
            "height_mm": weights[fruit_id].get("height_mm", ""),
            "variety": weights[fruit_id].get("variety", ""),
            "shape": weights[fruit_id].get("shape", ""),
        }
        for fruit_id in fruit_ids
    ]

    snapshot_root.mkdir(parents=True, exist_ok=True)
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    try:
        sample_manifest = temp_dir / "sample-manifest.csv"
        split_manifest = temp_dir / "fruit-splits.csv"
        _write_csv(
            sample_manifest,
            sample_rows,
            [
                "source_id",
                "fruit_id",
                "atomic_group",
                "split",
                "weight_with_calyx_g",
                "weight_without_calyx_g",
                "width_mm",
                "height_mm",
                "variety",
                "shape",
                "weight_grade",
                "archive_path",
                "filename",
                "relative_path",
                "size",
                "crc32",
                "sha256",
            ],
        )
        _write_csv(
            split_manifest,
            split_rows,
            [
                "source_id",
                "fruit_id",
                "split",
                "weight_with_calyx_g",
                "weight_without_calyx_g",
                "width_mm",
                "height_mm",
                "variety",
                "shape",
            ],
        )

        descriptor = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "snapshot_type": "TRAINING",
            "task": "STRAWBERRY_WEIGHT_REGRESSION",
            "status": "WEIGHT_SNAPSHOT_FROZEN",
            "source_id": SOURCE_ID,
            "primary_target": "weight_with_calyx_g",
            "auxiliary_target": "weight_without_calyx_g",
            "field_weight_protocol": "WITH_CALYX",
            "split_group": "FRUIT_ID",
            "fruit_count": len(fruit_ids),
            "image_count": len(sample_rows),
            "expected_views_per_fruit": EXPECTED_VIEWS_PER_FRUIT,
            "materialized_asset_root": str(asset_root),
            "candidate_rows_sha256": candidate["rows_sha256"],
            "split_policy": {
                "seed": seed,
                "train_ratio": train_ratio,
                "validation_ratio": val_ratio,
                "test_ratio": test_ratio,
                "fruit_counts": dict(sorted(split_fruit_counts.items())),
                "image_counts": dict(sorted(split_image_counts.items())),
                "assignment_sha256": _canonical_assignment_sha256(assignments),
            },
            "asset_rows_sha256": _canonical_asset_rows_sha256(sample_rows),
            "upstream_artifact_hashes": {
                "candidate_manifest_sha256": sha256_file(candidate_manifest),
                "materialized_manifest_sha256": sha256_file(materialized_manifest),
                "datasheet_sha256": sha256_file(datasheet),
            },
            "artifact_hashes": {
                "sample-manifest.csv": sha256_file(sample_manifest),
                "fruit-splits.csv": sha256_file(split_manifest),
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (temp_dir / "WEIGHT_SNAPSHOT.json").write_text(
            json.dumps(descriptor, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_dir.replace(snapshot_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return {
        **descriptor,
        "snapshot_dir": str(snapshot_dir),
    }
