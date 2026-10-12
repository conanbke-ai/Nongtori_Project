from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .strawberry_detector_data import prepare_strawberry_detector_data


class StrawberryDetectorAcquisitionError(RuntimeError):
    pass


CLASS_NAMES = {
    0: "Green",
    1: "White",
    2: "Early-Turning",
    3: "Turning",
    4: "Late-Turning",
    5: "Red",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize_strawberry_ds_parquet(
    *,
    parquet_path: Path = Path("data/external/DATA-RIP-001/1/data/train-00000-of-00001.parquet"),
    output_root: Path = Path("data/external/DATA-RIP-001/1/materialized"),
    audit_root: Path = Path("data/audit/strawberry-detector-v001"),
) -> dict[str, Any]:
    try:
        from PIL import Image
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise StrawberryDetectorAcquisitionError(
            "Strawberry detector materialization requires Pillow and pyarrow. "
            "Install once with: python -m pip install pillow pyarrow"
        ) from exc
    parquet_path = Path(parquet_path)
    output_root = Path(output_root)
    audit_root = Path(audit_root)

    if not parquet_path.is_file():
        raise StrawberryDetectorAcquisitionError(
            f"Strawberry-DS parquet missing: {parquet_path}"
        )

    images_dir = output_root / "images"
    labels_dir = output_root / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)

    table = pq.read_table(parquet_path)
    rows = table.to_pylist()

    materialized: list[dict[str, Any]] = []
    class_counts: dict[str, int] = {}
    original_split_counts: dict[str, int] = {}
    bbox_total = 0

    for index, row in enumerate(rows):
        image = row.get("image")
        objects = row.get("objects") or {}
        original_split = str(row.get("split") or "unknown")

        if not isinstance(image, dict):
            raise StrawberryDetectorAcquisitionError(
                f"Row {index}: image must be a mapping"
            )

        raw_bytes = image.get("bytes")
        source_name = str(image.get("path") or f"sample-{index:06d}.jpg")
        suffix = Path(source_name).suffix.lower() or ".jpg"
        sample_id = f"sample-{index:06d}"
        image_path = images_dir / f"{sample_id}{suffix}"

        if not raw_bytes:
            raise StrawberryDetectorAcquisitionError(
                f"Row {index}: image bytes are missing"
            )
        image_path.write_bytes(raw_bytes)

        try:
            with Image.open(image_path) as pil:
                width, height = pil.size
        except Exception as exc:
            raise StrawberryDetectorAcquisitionError(
                f"Row {index}: invalid image payload: {exc}"
            ) from exc

        boxes = list(objects.get("bbox") or [])
        categories = list(objects.get("categories") or [])
        if len(boxes) != len(categories):
            raise StrawberryDetectorAcquisitionError(
                f"Row {index}: bbox/category length mismatch "
                f"({len(boxes)} != {len(categories)})"
            )

        label_lines: list[str] = []
        for object_index, (box, category) in enumerate(zip(boxes, categories)):
            if len(box) != 4:
                raise StrawberryDetectorAcquisitionError(
                    f"Row {index} bbox {object_index}: expected 4 values"
                )

            x, y, box_w, box_h = (float(value) for value in box)
            category_id = int(category)

            if category_id not in CLASS_NAMES:
                raise StrawberryDetectorAcquisitionError(
                    f"Row {index} bbox {object_index}: unknown category {category_id}"
                )
            if box_w <= 0 or box_h <= 0:
                raise StrawberryDetectorAcquisitionError(
                    f"Row {index} bbox {object_index}: non-positive bbox"
                )

            x2 = x + box_w
            y2 = y + box_h
            eps = 1e-6
            if x < -eps or y < -eps or x2 > width + eps or y2 > height + eps:
                raise StrawberryDetectorAcquisitionError(
                    f"Row {index} bbox {object_index}: bbox outside image bounds"
                )

            x_center = (x + box_w / 2.0) / width
            y_center = (y + box_h / 2.0) / height
            norm_w = box_w / width
            norm_h = box_h / height

            label_lines.append(
                f"{category_id} {x_center:.10f} {y_center:.10f} "
                f"{norm_w:.10f} {norm_h:.10f}"
            )
            class_name = CLASS_NAMES[category_id]
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
            bbox_total += 1

        label_path = labels_dir / f"{sample_id}.txt"
        label_path.write_text(
            "\n".join(label_lines) + ("\n" if label_lines else ""),
            encoding="utf-8",
        )

        original_split_counts[original_split] = (
            original_split_counts.get(original_split, 0) + 1
        )

        materialized.append(
            {
                "sample_id": sample_id,
                "source_row_index": index,
                "source_image_name": source_name,
                "original_split": original_split,
                "image_width": width,
                "image_height": height,
                "bbox_count": len(boxes),
                "image_sha256": _sha256(image_path),
                "label_sha256": _sha256(label_path),
            }
        )

    manifest_path = audit_root / "hf-materialization-manifest.json"
    manifest_path.write_text(
        json.dumps(materialized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    detector_report = prepare_strawberry_detector_data(
        source_root=output_root,
        audit_root=audit_root,
    )

    report = {
        "status": "STRAWBERRY_DETECTOR_ACQUISITION_COMPLETE",
        "source_id": "DATA-RIP-001",
        "parquet_path": str(parquet_path),
        "materialized_root": str(output_root),
        "image_count": len(materialized),
        "bbox_count": bbox_total,
        "original_class_counts": dict(sorted(class_counts.items())),
        "original_split_counts": dict(sorted(original_split_counts.items())),
        "materialization_manifest": str(manifest_path),
        "detector_audit_status": detector_report["status"],
        "detector_eligible_image_count": detector_report["eligible_image_count"],
        "detector_eligible_object_count": detector_report["eligible_object_count"],
        "detector_split_counts": detector_report["split_counts"],
    }

    (audit_root / "acquisition-summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def acquire_and_materialize_strawberry_ds(
    *,
    download_root: Path = Path("data/external/DATA-RIP-001/1"),
    audit_root: Path = Path("data/audit/strawberry-detector-v001"),
) -> dict[str, Any]:
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as exc:
        raise StrawberryDetectorAcquisitionError(
            "Automatic Strawberry-DS download requires huggingface_hub. "
            "Install once with: python -m pip install huggingface_hub"
        ) from exc

    download_root = Path(download_root)
    try:
        info = HfApi().dataset_info(
            "Project-AgML/Strawberry-DS_strawberry_detection"
        )
        revision = str(info.sha)
        snapshot_download(
            repo_id="Project-AgML/Strawberry-DS_strawberry_detection",
            repo_type="dataset",
            revision=revision,
            local_dir=download_root,
        )
    except Exception as exc:
        raise StrawberryDetectorAcquisitionError(
            f"Automatic Hugging Face acquisition failed: {exc}"
        ) from exc

    parquet_path = download_root / "data" / "train-00000-of-00001.parquet"
    report = materialize_strawberry_ds_parquet(
        parquet_path=parquet_path,
        output_root=download_root / "materialized",
        audit_root=audit_root,
    )
    report["acquisition"] = {
        "provider": "Hugging Face",
        "repo_id": "Project-AgML/Strawberry-DS_strawberry_detection",
        "revision": revision,
        "canonical_origin": "Mendeley Strawberry-DS / DATA-RIP-001",
    }
    (Path(audit_root) / "acquisition-summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
