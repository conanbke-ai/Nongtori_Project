from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from .dyson_weight_reference import DATASET_ROLE, DysonPipelineError


DEFAULT_SNAPSHOT_DIR = Path("data/snapshots/DYSON-REFERENCE-V001")
DEFAULT_ANNOTATION_ROOT = Path("data/external/icra-dyson-annotations/extracted")
DEFAULT_AUDIT_ROOT = Path("data/audit/icra-dyson-annotations")

JOIN_COLUMNS = [
    "berry_key",
    "scene_id",
    "berry_instance_id",
    "view_index",
    "rgb_path",
    "source_center_x",
    "source_center_y",
    "annotation_json_path",
    "annotation_index",
    "join_status",
    "bbox_x1",
    "bbox_y1",
    "bbox_x2",
    "bbox_y2",
    "bbox_mode",
    "category_id",
    "candidate_hit_count",
    "bounds_check_status",
    "segmentation_bbox_consistent",
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


def _normalize_source_center(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _parse_xyxy_bbox(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
        return None
    if not (x2 > x1 and y2 > y1):
        return None
    return x1, y1, x2, y2


def _center_inside_bbox(x: float, y: float, bbox: tuple[float, float, float, float]) -> bool:
    x1, y1, x2, y2 = bbox
    return x1 <= x <= x2 and y1 <= y <= y2


def _segmentation_extent(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list):
        return None

    coordinates: list[float] = []
    for polygon in value:
        if not isinstance(polygon, list):
            continue
        for raw in polygon:
            try:
                number = float(raw)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(number):
                return None
            coordinates.append(number)

    if len(coordinates) < 4 or len(coordinates) % 2:
        return None

    xs = coordinates[0::2]
    ys = coordinates[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def _segmentation_bbox_consistent(annotation: dict[str, Any], bbox: tuple[float, float, float, float]) -> str:
    extent = _segmentation_extent(annotation.get("segmentation"))
    if extent is None:
        return "NOT_CHECKED"
    x1, y1, x2, y2 = bbox
    sx1, sy1, sx2, sy2 = extent
    tolerance = 2.0
    consistent = (
        sx1 >= x1 - tolerance
        and sy1 >= y1 - tolerance
        and sx2 <= x2 + tolerance
        and sy2 <= y2 + tolerance
    )
    return "CONSISTENT" if consistent else "OUTSIDE_BBOX"


def annotation_path_from_rgb(rgb_path: str, annotation_root: Path) -> Path:
    normalized = PurePosixPath(str(rgb_path).replace("\\", "/"))
    parts = normalized.parts

    if len(parts) < 5 or parts[0] != "extracted":
        raise DysonPipelineError(f"unexpected Dyson RGB path: {rgb_path!r}")

    filename = parts[-1]
    if not filename.endswith("_rgb.png"):
        raise DysonPipelineError(f"unexpected Dyson RGB filename: {filename!r}")

    # Raw weight assets are stored as:
    # extracted/<archive>/<partition>/<scene>/<stem>_<view>_rgb.png
    # Official keypoint JSON is stored as:
    # dyson_annotations/<partition>/<scene>/<stem>_<view>_keypoint.json
    relative_parts = parts[2:-1]
    stem = filename.removesuffix("_rgb.png")
    return Path(annotation_root) / "dyson_annotations" / Path(*relative_parts) / f"{stem}_keypoint.json"


def _validate_snapshot(snapshot_dir: Path) -> tuple[dict[str, Any], Path]:
    descriptor_path = snapshot_dir / "REFERENCE_SNAPSHOT.json"
    manifest_path = snapshot_dir / "physical-berry-manifest.csv"

    if not descriptor_path.is_file():
        raise DysonPipelineError(f"missing Dyson reference descriptor: {descriptor_path}")
    if not manifest_path.is_file():
        raise DysonPipelineError(f"missing frozen physical berry manifest: {manifest_path}")

    descriptor = _load_json_object(descriptor_path, "Dyson reference descriptor")
    if descriptor.get("status") != "DYSON_REFERENCE_SNAPSHOT_FROZEN":
        raise DysonPipelineError(
            f"Dyson reference snapshot is not frozen: {descriptor.get('status')!r}"
        )
    if descriptor.get("dataset_role") != DATASET_ROLE:
        raise DysonPipelineError("Dyson reference dataset role drifted")
    if descriptor.get("commercial_training_ready") is not False:
        raise DysonPipelineError("Dyson commercial training guard must remain false")

    return descriptor, manifest_path


def _candidate_record(
    annotation: dict[str, Any],
    index: int,
) -> tuple[dict[str, Any] | None, bool]:
    bbox = _parse_xyxy_bbox(annotation.get("bbox"))
    if bbox is None:
        return None, True
    x1, y1, x2, y2 = bbox
    return {
        "annotation_index": index,
        "bbox": bbox,
        "bbox_mode": annotation.get("bbox_mode"),
        "category_id": annotation.get("category_id"),
        "segmentation_bbox_consistent": _segmentation_bbox_consistent(annotation, bbox),
    }, False


def audit_dyson_annotation_join(
    *,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    annotation_root: Path = DEFAULT_ANNOTATION_ROOT,
    audit_root: Path = DEFAULT_AUDIT_ROOT,
) -> dict[str, Any]:
    snapshot_dir = Path(snapshot_dir)
    annotation_root = Path(annotation_root)
    audit_root = Path(audit_root)

    descriptor, manifest_path = _validate_snapshot(snapshot_dir)

    with manifest_path.open(encoding="utf-8", newline="") as handle:
        berries = list(csv.DictReader(handle))

    expected_berry_count = int(descriptor.get("strict_berry_count") or 0)
    if len(berries) != expected_berry_count:
        raise DysonPipelineError(
            f"frozen berry manifest row count drifted: {len(berries)}/{expected_berry_count}"
        )

    audit_root.mkdir(parents=True, exist_ok=True)

    join_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    berry_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "available": 0,
            "unique": 0,
        }
    )

    loaded_annotations: dict[Path, list[dict[str, Any]]] = {}
    unique_object_count = 0
    unique_invalid_bbox_object_count = 0
    bbox_mode_counts: Counter[str] = Counter()
    category_id_counts: Counter[str] = Counter()

    missing_annotation_examples: list[dict[str, Any]] = []
    no_object_examples: list[dict[str, Any]] = []
    ambiguous_examples: list[dict[str, Any]] = []
    invalid_bbox_examples: list[dict[str, Any]] = []

    for berry in berries:
        berry_key = str(berry.get("berry_key") or "").strip()
        if not berry_key:
            raise DysonPipelineError("frozen berry row is missing berry_key")
        if berry.get("dataset_role") != DATASET_ROLE:
            raise DysonPipelineError(f"dataset role drifted in {berry_key}")
        if str(berry.get("commercial_training_ready")) != "False":
            raise DysonPipelineError(f"commercial training guard drifted in {berry_key}")

        for view in (1, 2, 3):
            rgb_path = str(berry.get(f"view_{view}_rgb_path") or "").strip()
            if not rgb_path:
                continue

            berry_stats[berry_key]["available"] += 1
            source_x = _normalize_source_center(berry.get(f"view_{view}_x"))
            source_y = _normalize_source_center(berry.get(f"view_{view}_y"))

            base_row: dict[str, Any] = {
                "berry_key": berry_key,
                "scene_id": str(berry.get("scene_id") or ""),
                "berry_instance_id": str(berry.get("berry_instance_id") or ""),
                "view_index": view,
                "rgb_path": rgb_path,
                "source_center_x": "" if source_x is None else source_x,
                "source_center_y": "" if source_y is None else source_y,
                "annotation_json_path": "",
                "annotation_index": "",
                "join_status": "",
                "bbox_x1": "",
                "bbox_y1": "",
                "bbox_x2": "",
                "bbox_y2": "",
                "bbox_mode": "",
                "category_id": "",
                "candidate_hit_count": 0,
                "bounds_check_status": "NOT_CHECKED_NO_IMAGE_DIMENSIONS",
                "segmentation_bbox_consistent": "",
                "dataset_role": DATASET_ROLE,
                "commercial_training_ready": False,
            }

            if source_x is None or source_y is None:
                base_row["join_status"] = "INVALID_SOURCE_CENTER"
                status_counts["INVALID_SOURCE_CENTER"] += 1
                join_rows.append(base_row)
                continue

            annotation_path = annotation_path_from_rgb(rgb_path, annotation_root)
            try:
                relative_annotation_path = annotation_path.relative_to(annotation_root).as_posix()
            except ValueError:
                relative_annotation_path = annotation_path.as_posix()
            base_row["annotation_json_path"] = relative_annotation_path

            if not annotation_path.is_file():
                base_row["join_status"] = "NO_ANNOTATION_IMAGE"
                status_counts["NO_ANNOTATION_IMAGE"] += 1
                if len(missing_annotation_examples) < 30:
                    missing_annotation_examples.append(
                        {
                            "berry_key": berry_key,
                            "view_index": view,
                            "rgb_path": rgb_path,
                            "expected_annotation_json": relative_annotation_path,
                        }
                    )
                join_rows.append(base_row)
                continue

            if annotation_path not in loaded_annotations:
                payload = _load_json_object(annotation_path, "Dyson annotation JSON")
                raw_annotations = payload.get("annotations")
                if not isinstance(raw_annotations, list):
                    raise DysonPipelineError(
                        f"annotation JSON must contain an annotations list: {annotation_path}"
                    )
                annotations: list[dict[str, Any]] = []
                for index, raw in enumerate(raw_annotations):
                    if not isinstance(raw, dict):
                        raise DysonPipelineError(
                            f"annotation object must be a JSON object: {annotation_path}#{index}"
                        )
                    annotations.append(raw)
                    unique_object_count += 1
                    bbox_mode_counts[str(raw.get("bbox_mode"))] += 1
                    category_id_counts[str(raw.get("category_id"))] += 1
                    if _parse_xyxy_bbox(raw.get("bbox")) is None:
                        unique_invalid_bbox_object_count += 1
                loaded_annotations[annotation_path] = annotations

            annotations = loaded_annotations[annotation_path]
            valid_candidates: list[dict[str, Any]] = []
            invalid_bbox_count_in_file = 0
            for index, annotation in enumerate(annotations):
                candidate, invalid = _candidate_record(annotation, index)
                if invalid:
                    invalid_bbox_count_in_file += 1
                    continue
                assert candidate is not None
                if _center_inside_bbox(source_x, source_y, candidate["bbox"]):
                    valid_candidates.append(candidate)

            base_row["candidate_hit_count"] = len(valid_candidates)

            if len(valid_candidates) == 1:
                candidate = valid_candidates[0]
                x1, y1, x2, y2 = candidate["bbox"]
                base_row.update(
                    {
                        "annotation_index": candidate["annotation_index"],
                        "join_status": "UNIQUE_GEOMETRIC_MATCH",
                        "bbox_x1": x1,
                        "bbox_y1": y1,
                        "bbox_x2": x2,
                        "bbox_y2": y2,
                        "bbox_mode": candidate["bbox_mode"],
                        "category_id": candidate["category_id"],
                        "segmentation_bbox_consistent": candidate[
                            "segmentation_bbox_consistent"
                        ],
                    }
                )
                status_counts["UNIQUE_GEOMETRIC_MATCH"] += 1
                berry_stats[berry_key]["unique"] += 1
            elif len(valid_candidates) > 1:
                base_row["join_status"] = "AMBIGUOUS_MATCH"
                status_counts["AMBIGUOUS_MATCH"] += 1
                if len(ambiguous_examples) < 30:
                    ambiguous_examples.append(
                        {
                            "berry_key": berry_key,
                            "berry_instance_id": base_row["berry_instance_id"],
                            "view_index": view,
                            "source_center": [source_x, source_y],
                            "annotation_json_path": relative_annotation_path,
                            "candidate_hits": [
                                {
                                    "annotation_index": candidate["annotation_index"],
                                    "bbox": list(candidate["bbox"]),
                                    "bbox_mode": candidate["bbox_mode"],
                                    "category_id": candidate["category_id"],
                                }
                                for candidate in valid_candidates
                            ],
                        }
                    )
            elif invalid_bbox_count_in_file and invalid_bbox_count_in_file == len(annotations):
                base_row["join_status"] = "INVALID_BBOX"
                status_counts["INVALID_BBOX"] += 1
                if len(invalid_bbox_examples) < 30:
                    invalid_bbox_examples.append(
                        {
                            "berry_key": berry_key,
                            "view_index": view,
                            "annotation_json_path": relative_annotation_path,
                            "invalid_bbox_object_count": invalid_bbox_count_in_file,
                        }
                    )
            else:
                base_row["join_status"] = "NO_OBJECT_MATCH"
                status_counts["NO_OBJECT_MATCH"] += 1
                if len(no_object_examples) < 30:
                    no_object_examples.append(
                        {
                            "berry_key": berry_key,
                            "berry_instance_id": base_row["berry_instance_id"],
                            "view_index": view,
                            "source_center": [source_x, source_y],
                            "annotation_json_path": relative_annotation_path,
                            "annotation_count": len(annotations),
                            "invalid_bbox_object_count": invalid_bbox_count_in_file,
                        }
                    )

            join_rows.append(base_row)

    expected_berry_view_count = len(join_rows)
    unique_berry_count_with_at_least_one_bbox = sum(
        1 for stats in berry_stats.values() if stats["unique"] > 0
    )
    berries_with_all_available_views_joined = sum(
        1
        for stats in berry_stats.values()
        if stats["available"] > 0 and stats["unique"] == stats["available"]
    )

    csv_path = audit_root / "berry-annotation-join.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=JOIN_COLUMNS)
        writer.writeheader()
        writer.writerows(join_rows)

    exception_count = (
        status_counts["NO_OBJECT_MATCH"]
        + status_counts["AMBIGUOUS_MATCH"]
        + status_counts["NO_ANNOTATION_IMAGE"]
        + status_counts["INVALID_SOURCE_CENTER"]
        + status_counts["INVALID_BBOX"]
    )
    report = {
        "status": (
            "DYSON_ANNOTATION_JOIN_AUDIT_COMPLETE"
            if exception_count == 0
            else "DYSON_ANNOTATION_JOIN_AUDIT_COMPLETE_WITH_EXCEPTIONS"
        ),
        "contract": "nongtori-dyson-annotation-join-audit.v1",
        "dataset_role": DATASET_ROLE,
        "commercial_training_ready": False,
        "strict_berry_count": len(berries),
        "expected_berry_view_count": expected_berry_view_count,
        "annotation_file_resolved_count": (
            expected_berry_view_count - status_counts["NO_ANNOTATION_IMAGE"]
        ),
        "unique_geometric_match_count": status_counts["UNIQUE_GEOMETRIC_MATCH"],
        "no_object_match_count": status_counts["NO_OBJECT_MATCH"],
        "ambiguous_match_count": status_counts["AMBIGUOUS_MATCH"],
        "no_annotation_image_count": status_counts["NO_ANNOTATION_IMAGE"],
        "invalid_source_center_count": status_counts["INVALID_SOURCE_CENTER"],
        "invalid_bbox_count": status_counts["INVALID_BBOX"],
        "unique_berry_count_with_at_least_one_bbox": unique_berry_count_with_at_least_one_bbox,
        "berries_with_all_available_views_joined": berries_with_all_available_views_joined,
        "unique_annotation_json_count": len(loaded_annotations),
        "unique_annotation_object_count": unique_object_count,
        "unique_invalid_bbox_object_count": unique_invalid_bbox_object_count,
        "bbox_mode_counts": dict(sorted(bbox_mode_counts.items())),
        "category_id_counts": dict(sorted(category_id_counts.items())),
        "annotation_path_mapping_rule": (
            "extracted/<archive>/<partition>/<scene>/<stem>_<view>_rgb.png "
            "-> dyson_annotations/<partition>/<scene>/<stem>_<view>_keypoint.json"
        ),
        "identity_rule": (
            "A frozen berry/view source center is joined only when it falls inside exactly "
            "one valid absolute-XYXY bbox. Annotation list order is never treated as berry identity."
        ),
        "bounds_check_policy": (
            "Image dimensions are not embedded in the frozen snapshot; bbox bounds are therefore "
            "reported as NOT_CHECKED_NO_IMAGE_DIMENSIONS in this audit."
        ),
        "missing_annotation_examples": missing_annotation_examples,
        "no_object_match_examples": no_object_examples,
        "ambiguous_match_examples": ambiguous_examples,
        "invalid_bbox_examples": invalid_bbox_examples,
        "artifacts": {
            "join_csv": str(csv_path),
            "join_audit": str(audit_root / "berry-annotation-join-audit.json"),
        },
        "next_gate": (
            "dyson-materialize-berry-crops may consume only UNIQUE_GEOMETRIC_MATCH rows "
            "after this audit is reviewed."
        ),
    }

    json_path = audit_root / "berry-annotation-join-audit.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
