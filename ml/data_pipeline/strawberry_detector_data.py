from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from .annotation_audit import STRAWBERRY_DS_CLASSES
class StrawberryDetectorDataError(RuntimeError):
    pass


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
DETECTOR_CLASS_NAME = "strawberry"
BOUNDARY_EPSILON = 1e-8
DEFAULT_SOURCE_ROOT = Path("data/external/strawberry-ds")
DEFAULT_AUDIT_ROOT = Path("data/audit/strawberry-detector-v001")


def _logical_key(path: Path, root: Path, marker: str) -> str:
    rel = path.relative_to(root)
    parts = list(rel.parts)
    lowered = [part.lower() for part in parts]
    if marker in lowered:
        idx = lowered.index(marker)
        logical = PurePosixPath(*parts[idx + 1 :]).with_suffix("")
    else:
        logical = PurePosixPath(*parts).with_suffix("")
    return logical.as_posix()


def _index_paths(root: Path) -> tuple[dict[str, Path], dict[str, Path], dict[str, list[str]]]:
    image_candidates: dict[str, list[Path]] = defaultdict(list)
    label_candidates: dict[str, list[Path]] = defaultdict(list)

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            image_candidates[_logical_key(path, root, "images")].append(path)
        elif suffix == ".txt":
            label_candidates[_logical_key(path, root, "labels")].append(path)

    ambiguous: dict[str, list[str]] = {}
    images: dict[str, Path] = {}
    labels: dict[str, Path] = {}

    for key, paths in image_candidates.items():
        if len(paths) == 1:
            images[key] = paths[0]
        else:
            ambiguous[f"image:{key}"] = [str(path.relative_to(root)) for path in paths]
    for key, paths in label_candidates.items():
        if len(paths) == 1:
            labels[key] = paths[0]
        else:
            ambiguous[f"label:{key}"] = [str(path.relative_to(root)) for path in paths]

    return images, labels, ambiguous


def _parse_label_file(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    objects: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            errors.append({"line": line_no, "error": "YOLO_FIELD_COUNT", "raw": line})
            continue
        try:
            class_id = int(parts[0])
            x_center, y_center, width, height = (float(item) for item in parts[1:])
        except ValueError:
            errors.append({"line": line_no, "error": "YOLO_PARSE_ERROR", "raw": line})
            continue

        if class_id not in STRAWBERRY_DS_CLASSES:
            errors.append({"line": line_no, "error": "UNKNOWN_CLASS_ID", "raw": line})
            continue
        if not (
            0.0 <= x_center <= 1.0
            and 0.0 <= y_center <= 1.0
            and 0.0 < width <= 1.0
            and 0.0 < height <= 1.0
        ):
            errors.append({"line": line_no, "error": "INVALID_NORMALIZED_BOX", "raw": line})
            continue

        x1 = x_center - width / 2.0
        y1 = y_center - height / 2.0
        x2 = x_center + width / 2.0
        y2 = y_center + height / 2.0
        if (
            x1 < -BOUNDARY_EPSILON
            or y1 < -BOUNDARY_EPSILON
            or x2 > 1.0 + BOUNDARY_EPSILON
            or y2 > 1.0 + BOUNDARY_EPSILON
        ):
            errors.append({"line": line_no, "error": "BOX_EXTENDS_OUTSIDE_IMAGE", "raw": line})
            continue

        objects.append(
            {
                "source_line": line_no,
                "original_class_id": class_id,
                "original_class_name": STRAWBERRY_DS_CLASSES[class_id],
                "detector_class_id": 0,
                "detector_class_name": DETECTOR_CLASS_NAME,
                "x_center": x_center,
                "y_center": y_center,
                "width": width,
                "height": height,
            }
        )

    return objects, errors


def _assign_split(key: str, seed: str, train_ratio: float, val_ratio: float) -> str:
    prefix = key.split("/", 1)[0].lower()
    if prefix == "train":
        return "train"
    if prefix in {"valid", "validation", "val"}:
        return "validation"
    if prefix == "test":
        return "test"

    digest = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") / float(2**64)
    if value < train_ratio:
        return "train"
    if value < train_ratio + val_ratio:
        return "validation"
    return "test"


def prepare_strawberry_detector_data(
    *,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    audit_root: Path = DEFAULT_AUDIT_ROOT,
    seed: str = "strawberry-detector-v001",
    train_ratio: float = 0.80,
    val_ratio: float = 0.10,
    test_ratio: float = 0.10,
) -> dict[str, Any]:
    source_root = Path(source_root)
    audit_root = Path(audit_root)

    if not source_root.is_dir():
        raise StrawberryDetectorDataError(f"Strawberry-DS root missing: {source_root}")
    if abs((train_ratio + val_ratio + test_ratio) - 1.0) > 1e-9:
        raise StrawberryDetectorDataError("train/validation/test ratios must sum to 1")
    if min(train_ratio, val_ratio, test_ratio) <= 0:
        raise StrawberryDetectorDataError("all split ratios must be positive")

    images, labels, ambiguous = _index_paths(source_root)
    all_keys = sorted(set(images) | set(labels))

    image_rows: list[dict[str, Any]] = []
    object_rows: list[dict[str, Any]] = []
    missing_image: list[str] = []
    missing_label: list[str] = []
    parse_errors: list[dict[str, Any]] = []
    split_counts: Counter[str] = Counter()
    original_class_counts: Counter[str] = Counter()

    for key in all_keys:
        image = images.get(key)
        label = labels.get(key)
        if image is None:
            missing_image.append(key)
            continue
        if label is None:
            missing_label.append(key)
            continue

        objects, errors = _parse_label_file(label)
        if errors:
            parse_errors.extend(
                {
                    "image_key": key,
                    "label_path": str(label.relative_to(source_root)),
                    **error,
                }
                for error in errors
            )

        split = _assign_split(key, seed, train_ratio, val_ratio)
        if not objects:
            image_rows.append(
                {
                    "image_key": key,
                    "image_path": str(image.relative_to(source_root)).replace("\\", "/"),
                    "label_path": str(label.relative_to(source_root)).replace("\\", "/"),
                    "split": split,
                    "annotation_count": 0,
                    "eligible": False,
                    "exclusion_reason": "NO_VALID_BOX",
                }
            )
            continue

        split_counts[split] += 1
        image_rows.append(
            {
                "image_key": key,
                "image_path": str(image.relative_to(source_root)).replace("\\", "/"),
                "label_path": str(label.relative_to(source_root)).replace("\\", "/"),
                "split": split,
                "annotation_count": len(objects),
                "eligible": True,
                "exclusion_reason": "",
            }
        )
        for object_index, obj in enumerate(objects):
            original_class_counts[obj["original_class_name"]] += 1
            object_rows.append(
                {
                    "image_key": key,
                    "split": split,
                    "object_index": object_index,
                    **obj,
                }
            )

    audit_root.mkdir(parents=True, exist_ok=True)

    image_manifest = audit_root / "detector-image-manifest.csv"
    with image_manifest.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "image_key",
            "image_path",
            "label_path",
            "split",
            "annotation_count",
            "eligible",
            "exclusion_reason",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(image_rows)

    object_manifest = audit_root / "detector-object-manifest.csv"
    with object_manifest.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "image_key",
            "split",
            "object_index",
            "source_line",
            "original_class_id",
            "original_class_name",
            "detector_class_id",
            "detector_class_name",
            "x_center",
            "y_center",
            "width",
            "height",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(object_rows)

    eligible_images = [row for row in image_rows if row["eligible"]]
    status = (
        "STRAWBERRY_DETECTOR_DATA_READY"
        if eligible_images and not ambiguous and not missing_image and not missing_label and not parse_errors
        else "STRAWBERRY_DETECTOR_DATA_READY_WITH_EXCEPTIONS"
        if eligible_images
        else "STRAWBERRY_DETECTOR_DATA_BLOCKED"
    )

    report = {
        "status": status,
        "contract": "nongtori-strawberry-detector-data.v1",
        "source_id": "DATA-RIP-001",
        "source_role": "PUBLIC_DETECTION_SUPERVISION",
        "license": "CC-BY-4.0",
        "detector_label_policy": {
            "source_classes_preserved_in_audit": list(STRAWBERRY_DS_CLASSES.values()),
            "training_class_count": 1,
            "training_class_names": [DETECTOR_CLASS_NAME],
            "policy": "COLLAPSE_ALL_RIPENESS_CLASSES_TO_STRAWBERRY_FOR_DETECTION_ONLY",
        },
        "split_policy": {
            "unit": "IMAGE_KEY",
            "source_split_preserved_when_present": True,
            "fallback_seed": seed,
            "fallback_train_ratio": train_ratio,
            "fallback_validation_ratio": val_ratio,
            "fallback_test_ratio": test_ratio,
        },
        "discovered_image_count": len(images),
        "discovered_label_count": len(labels),
        "paired_key_count": len(set(images) & set(labels)),
        "eligible_image_count": len(eligible_images),
        "eligible_object_count": len(object_rows),
        "split_counts": dict(sorted(split_counts.items())),
        "original_class_counts": dict(sorted(original_class_counts.items())),
        "ambiguous_path_count": len(ambiguous),
        "missing_image_count": len(missing_image),
        "missing_label_count": len(missing_label),
        "parse_error_count": len(parse_errors),
        "ambiguous_paths": ambiguous,
        "missing_image_examples": missing_image[:30],
        "missing_label_examples": missing_label[:30],
        "parse_error_examples": parse_errors[:30],
        "artifacts": {
            "image_manifest": str(image_manifest),
            "object_manifest": str(object_manifest),
            "audit": str(audit_root / "detector-data-audit.json"),
        },
        "next_gate": (
            "Train one fixed detector baseline only after reviewing this audit. "
            "Do not use ripeness class IDs as detector classes."
        ),
    }
    (audit_root / "detector-data-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
