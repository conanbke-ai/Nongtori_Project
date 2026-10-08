from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .dyson_weight_reference import DATASET_ROLE, DysonPipelineError, sha256_file


DEFAULT_SNAPSHOT_DIR = Path("data/snapshots/DYSON-REFERENCE-V001")
DEFAULT_RAW_ROOT = Path("data/external/icra-dyson")
DEFAULT_JOIN_AUDIT_ROOT = Path("data/audit/icra-dyson-annotations")
DEFAULT_OUTPUT_ROOT = Path("data/external/icra-dyson-berry-crops")
DEFAULT_AUDIT_ROOT = Path("data/audit/icra-dyson-berry-crops")

CROP_COLUMNS = [
    "berry_key",
    "scene_id",
    "berry_instance_id",
    "view_index",
    "weight_g",
    "dimension_1",
    "dimension_2",
    "dimension_3",
    "source_rgb_path",
    "source_rgb_sha256",
    "source_center_x",
    "source_center_y",
    "bbox_x1",
    "bbox_y1",
    "bbox_x2",
    "bbox_y2",
    "pixel_left",
    "pixel_top",
    "pixel_right",
    "pixel_bottom",
    "crop_width",
    "crop_height",
    "bbox_mode",
    "category_id",
    "crop_relative_path",
    "crop_sha256",
    "materialization_status",
    "dataset_role",
    "commercial_training_ready",
]


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DysonPipelineError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DysonPipelineError(f"{label} must be a JSON object: {path}")
    return payload


def _safe_relative_path(value: str) -> PurePosixPath:
    relative = PurePosixPath(str(value).replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise DysonPipelineError(f"unsafe relative path: {value!r}")
    return relative


def _safe_join(root: Path, relative: str) -> Path:
    path = _safe_relative_path(relative)
    return Path(root, *path.parts)


def _parse_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DysonPipelineError(f"invalid numeric {label}: {value!r}") from exc
    if not math.isfinite(number):
        raise DysonPipelineError(f"non-finite numeric {label}: {value!r}")
    return number


def _pixel_box(row: dict[str, str]) -> tuple[int, int, int, int]:
    x1 = _parse_float(row.get("bbox_x1"), "bbox_x1")
    y1 = _parse_float(row.get("bbox_y1"), "bbox_y1")
    x2 = _parse_float(row.get("bbox_x2"), "bbox_x2")
    y2 = _parse_float(row.get("bbox_y2"), "bbox_y2")
    if not (x2 > x1 and y2 > y1):
        raise DysonPipelineError(f"invalid XYXY bbox in join row for {row.get('berry_key')}")
    left = math.floor(x1)
    top = math.floor(y1)
    right = math.ceil(x2)
    bottom = math.ceil(y2)
    if not (right > left and bottom > top):
        raise DysonPipelineError(f"invalid integer crop box in join row for {row.get('berry_key')}")
    return left, top, right, bottom


def _crop_relative_path(row: dict[str, str]) -> str:
    berry_key = str(row.get("berry_key") or "")
    scene_id = str(row.get("scene_id") or "")
    berry_instance_id = str(row.get("berry_instance_id") or "")
    view_index = str(row.get("view_index") or "")
    if not all((berry_key, scene_id, berry_instance_id, view_index)):
        raise DysonPipelineError("join row is missing crop identity fields")

    scene_leaf = PurePosixPath(scene_id.replace("\\", "/")).name
    digest = hashlib.sha256(berry_key.encode("utf-8")).hexdigest()[:12]
    return (
        f"{scene_leaf}/berry-{berry_instance_id}-{digest}/"
        f"view-{view_index}.png"
    )


def _default_crop_writer(
    source_path: Path,
    output_path: Path,
    pixel_box: tuple[int, int, int, int],
) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise DysonPipelineError(
            "Pillow is required for Dyson crop materialization. "
            "Install with: python -m pip install pillow"
        ) from exc

    left, top, right, bottom = pixel_box
    try:
        with Image.open(source_path) as image:
            width, height = image.size
            if left < 0 or top < 0 or right > width or bottom > height:
                raise DysonPipelineError(
                    f"bbox outside source image bounds: {source_path} "
                    f"box={pixel_box} image={width}x{height}"
                )
            crop = image.crop((left, top, right, bottom))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            crop.save(output_path, format="PNG", optimize=False, compress_level=9)
            crop.close()
    except DysonPipelineError:
        raise
    except Exception as exc:
        raise DysonPipelineError(f"cannot materialize Dyson crop from {source_path}: {exc}") from exc
    return width, height


def _load_frozen_targets(snapshot_dir: Path) -> dict[str, dict[str, str]]:
    descriptor = _load_json_object(
        snapshot_dir / "REFERENCE_SNAPSHOT.json",
        "Dyson reference descriptor",
    )
    if descriptor.get("status") != "DYSON_REFERENCE_SNAPSHOT_FROZEN":
        raise DysonPipelineError("Dyson reference snapshot is not frozen")
    if descriptor.get("dataset_role") != DATASET_ROLE:
        raise DysonPipelineError("Dyson reference dataset role drifted")
    if descriptor.get("commercial_training_ready") is not False:
        raise DysonPipelineError("Dyson commercial training guard must remain false")

    manifest_path = snapshot_dir / "physical-berry-manifest.csv"
    if not manifest_path.is_file():
        raise DysonPipelineError(f"missing frozen physical berry manifest: {manifest_path}")

    with manifest_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    expected = int(descriptor.get("strict_berry_count") or 0)
    if len(rows) != expected:
        raise DysonPipelineError(f"frozen berry count drifted: {len(rows)}/{expected}")

    targets: dict[str, dict[str, str]] = {}
    for row in rows:
        berry_key = str(row.get("berry_key") or "").strip()
        if not berry_key or berry_key in targets:
            raise DysonPipelineError(f"invalid or duplicate frozen berry_key: {berry_key!r}")
        if row.get("dataset_role") != DATASET_ROLE:
            raise DysonPipelineError(f"dataset role drifted in {berry_key}")
        if str(row.get("commercial_training_ready")) != "False":
            raise DysonPipelineError(f"commercial training guard drifted in {berry_key}")
        targets[berry_key] = row
    return targets


def materialize_dyson_berry_crops(
    *,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    raw_root: Path = DEFAULT_RAW_ROOT,
    join_audit_root: Path = DEFAULT_JOIN_AUDIT_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    audit_root: Path = DEFAULT_AUDIT_ROOT,
    crop_writer: Callable[[Path, Path, tuple[int, int, int, int]], tuple[int, int]] = _default_crop_writer,
) -> dict[str, Any]:
    snapshot_dir = Path(snapshot_dir)
    raw_root = Path(raw_root)
    join_audit_root = Path(join_audit_root)
    output_root = Path(output_root)
    audit_root = Path(audit_root)

    targets = _load_frozen_targets(snapshot_dir)

    join_summary = _load_json_object(
        join_audit_root / "berry-annotation-join-audit.json",
        "Dyson annotation join audit",
    )
    if not str(join_summary.get("status") or "").startswith("DYSON_ANNOTATION_JOIN_AUDIT_COMPLETE"):
        raise DysonPipelineError("Dyson annotation join audit is not complete")
    if join_summary.get("dataset_role") != DATASET_ROLE:
        raise DysonPipelineError("Dyson annotation join dataset role drifted")
    if join_summary.get("commercial_training_ready") is not False:
        raise DysonPipelineError("Dyson annotation join commercial training guard must remain false")

    join_csv = join_audit_root / "berry-annotation-join.csv"
    if not join_csv.is_file():
        raise DysonPipelineError(f"missing Dyson annotation join CSV: {join_csv}")

    with join_csv.open(encoding="utf-8", newline="") as handle:
        all_join_rows = list(csv.DictReader(handle))

    expected_view_count = int(join_summary.get("expected_berry_view_count") or 0)
    if len(all_join_rows) != expected_view_count:
        raise DysonPipelineError(
            f"join row count drifted: {len(all_join_rows)}/{expected_view_count}"
        )

    unique_rows = [
        row
        for row in all_join_rows
        if row.get("join_status") == "UNIQUE_GEOMETRIC_MATCH"
    ]
    expected_unique = int(join_summary.get("unique_geometric_match_count") or 0)
    if len(unique_rows) != expected_unique:
        raise DysonPipelineError(
            f"unique join count drifted: {len(unique_rows)}/{expected_unique}"
        )

    audit_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, Any]] = []
    source_missing_examples: list[dict[str, Any]] = []
    bounds_error_examples: list[dict[str, Any]] = []
    materialized_count = 0
    reused_count = 0
    source_missing_count = 0
    bounds_error_count = 0

    for row in unique_rows:
        berry_key = str(row.get("berry_key") or "")
        target = targets.get(berry_key)
        if target is None:
            raise DysonPipelineError(f"join row berry is not in frozen snapshot: {berry_key}")

        if row.get("dataset_role") != DATASET_ROLE:
            raise DysonPipelineError(f"join row dataset role drifted in {berry_key}")
        if str(row.get("commercial_training_ready")) != "False":
            raise DysonPipelineError(f"join row commercial training guard drifted in {berry_key}")

        source_rgb = str(row.get("rgb_path") or "").strip()
        source_path = _safe_join(raw_root, source_rgb)
        crop_relative = _crop_relative_path(row)
        crop_path = _safe_join(output_root, crop_relative)
        box = _pixel_box(row)
        left, top, right, bottom = box

        base: dict[str, Any] = {
            "berry_key": berry_key,
            "scene_id": row.get("scene_id", ""),
            "berry_instance_id": row.get("berry_instance_id", ""),
            "view_index": row.get("view_index", ""),
            "weight_g": target.get("weight_g", ""),
            "dimension_1": target.get("dimension_1", ""),
            "dimension_2": target.get("dimension_2", ""),
            "dimension_3": target.get("dimension_3", ""),
            "source_rgb_path": source_rgb,
            "source_rgb_sha256": "",
            "source_center_x": row.get("source_center_x", ""),
            "source_center_y": row.get("source_center_y", ""),
            "bbox_x1": row.get("bbox_x1", ""),
            "bbox_y1": row.get("bbox_y1", ""),
            "bbox_x2": row.get("bbox_x2", ""),
            "bbox_y2": row.get("bbox_y2", ""),
            "pixel_left": left,
            "pixel_top": top,
            "pixel_right": right,
            "pixel_bottom": bottom,
            "crop_width": right - left,
            "crop_height": bottom - top,
            "bbox_mode": row.get("bbox_mode", ""),
            "category_id": row.get("category_id", ""),
            "crop_relative_path": crop_relative,
            "crop_sha256": "",
            "materialization_status": "",
            "dataset_role": DATASET_ROLE,
            "commercial_training_ready": False,
        }

        if not source_path.is_file():
            base["materialization_status"] = "SOURCE_RGB_MISSING"
            source_missing_count += 1
            if len(source_missing_examples) < 30:
                source_missing_examples.append(
                    {
                        "berry_key": berry_key,
                        "view_index": row.get("view_index"),
                        "source_rgb_path": source_rgb,
                    }
                )
            manifest_rows.append(base)
            continue

        source_sha = sha256_file(source_path)
        base["source_rgb_sha256"] = source_sha

        if crop_path.is_file():
            base["crop_sha256"] = sha256_file(crop_path)
            base["materialization_status"] = "REUSED_EXISTING_CROP"
            reused_count += 1
            manifest_rows.append(base)
            continue

        try:
            crop_writer(source_path, crop_path, box)
        except DysonPipelineError as exc:
            message = str(exc)
            if "outside source image bounds" in message:
                base["materialization_status"] = "BBOX_OUT_OF_BOUNDS"
                bounds_error_count += 1
                if len(bounds_error_examples) < 30:
                    bounds_error_examples.append(
                        {
                            "berry_key": berry_key,
                            "view_index": row.get("view_index"),
                            "source_rgb_path": source_rgb,
                            "pixel_box": list(box),
                            "error": message,
                        }
                    )
                manifest_rows.append(base)
                continue
            raise

        base["crop_sha256"] = sha256_file(crop_path)
        base["materialization_status"] = "MATERIALIZED"
        materialized_count += 1
        manifest_rows.append(base)

    manifest_path = audit_root / "berry-crop-manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CROP_COLUMNS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    successful = materialized_count + reused_count
    report = {
        "status": (
            "DYSON_BERRY_CROPS_MATERIALIZED"
            if successful == expected_unique and source_missing_count == 0 and bounds_error_count == 0
            else "DYSON_BERRY_CROPS_MATERIALIZED_WITH_EXCEPTIONS"
        ),
        "contract": "nongtori-dyson-berry-crops.v1",
        "dataset_role": DATASET_ROLE,
        "commercial_training_ready": False,
        "strict_berry_count": len(targets),
        "input_join_row_count": len(all_join_rows),
        "eligible_unique_join_count": expected_unique,
        "materialized_count": materialized_count,
        "reused_existing_crop_count": reused_count,
        "successful_crop_count": successful,
        "source_rgb_missing_count": source_missing_count,
        "bbox_out_of_bounds_count": bounds_error_count,
        "excluded_non_unique_join_count": len(all_join_rows) - expected_unique,
        "source_missing_examples": source_missing_examples,
        "bbox_out_of_bounds_examples": bounds_error_examples,
        "crop_rule": (
            "Only UNIQUE_GEOMETRIC_MATCH rows are eligible. "
            "Float XYXY is converted with floor(left/top) and ceil(right/bottom). "
            "Out-of-bounds boxes are never clamped."
        ),
        "artifacts": {
            "crop_root": str(output_root),
            "crop_manifest": str(manifest_path),
            "crop_audit": str(audit_root / "berry-crop-audit.json"),
        },
        "next_gate": (
            "Use successful crop rows only for the external NON_COMMERCIAL_REFERENCE benchmark."
        ),
    }
    (audit_root / "berry-crop-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
