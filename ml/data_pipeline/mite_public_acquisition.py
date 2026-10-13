from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .downloader import DatasetDownloader
from .models import SourceRecord
from .registry import DatasetRegistry


SOURCES = ("DATA-PEST-001", "DATA-PEST-002")
SPLIT_ALIASES = {"train": "train", "valid": "validation", "val": "validation", "validation": "validation", "test": "test"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
RF_SUFFIX_RE = re.compile(r"\.rf\.[0-9a-fA-F]+$")


class MitePublicAcquisitionError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _origin_key(path: Path) -> str:
    stem = path.stem
    stem = RF_SUFFIX_RE.sub("", stem)
    return stem


def _find_data_yaml(root: Path) -> Path | None:
    candidates = sorted(root.rglob("data.yaml"))
    return candidates[0] if candidates else None


def _parse_names(data_yaml: Path | None) -> dict[int, str]:
    if data_yaml is None:
        return {}
    text = data_yaml.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("names:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                try:
                    parsed = ast.literal_eval(value)
                    if isinstance(parsed, list):
                        return {i: str(name) for i, name in enumerate(parsed)}
                    if isinstance(parsed, dict):
                        return {int(k): str(v) for k, v in parsed.items()}
                except Exception:
                    pass
            names: dict[int, str] = {}
            for child in lines[idx + 1 :]:
                if not child.startswith((" ", "\t")):
                    break
                item = child.strip()
                if ":" not in item:
                    continue
                key, val = item.split(":", 1)
                try:
                    names[int(key.strip())] = val.strip().strip("'\"")
                except ValueError:
                    continue
            return names
    return {}


def _split_dirs(root: Path) -> dict[str, tuple[Path, Path]]:
    found: dict[str, tuple[Path, Path]] = {}
    for candidate in root.rglob("images"):
        if not candidate.is_dir():
            continue
        parent = candidate.parent
        split_name = SPLIT_ALIASES.get(parent.name.lower())
        if not split_name:
            continue
        labels = parent / "labels"
        if labels.is_dir():
            found[split_name] = (candidate, labels)
    return found


def audit_roboflow_yolo_dataset(
    source: SourceRecord,
    root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    root = Path(root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    split_dirs = _split_dirs(root)
    if not split_dirs:
        raise MitePublicAcquisitionError(
            f"{source.source_id}: no Roboflow YOLO train/valid/test structure found under {root}"
        )

    names = _parse_names(_find_data_yaml(root))
    expected_labels = set(source.original_labels)

    rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    split_image_counts: Counter[str] = Counter()
    split_box_counts: Counter[str] = Counter()
    parse_errors: list[dict[str, Any]] = []
    missing_labels: list[str] = []
    image_hash_splits: defaultdict[str, set[str]] = defaultdict(set)
    origin_splits: defaultdict[str, set[str]] = defaultdict(set)
    origin_counts: Counter[str] = Counter()

    for split, (images_dir, labels_dir) in sorted(split_dirs.items()):
        images = sorted(
            path for path in images_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        split_image_counts[split] = len(images)

        for image_path in images:
            label_path = labels_dir / f"{image_path.stem}.txt"
            if not label_path.is_file():
                missing_labels.append(str(image_path.relative_to(root)))
                continue

            image_sha = _sha256(image_path)
            image_hash_splits[image_sha].add(split)
            origin = _origin_key(image_path)
            origin_splits[origin].add(split)
            origin_counts[origin] += 1

            box_count = 0
            for line_no, raw in enumerate(
                label_path.read_text(encoding="utf-8-sig").splitlines(), 1
            ):
                line = raw.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) != 5:
                    parse_errors.append({
                        "label": str(label_path.relative_to(root)),
                        "line": line_no,
                        "error": "YOLO_FIELD_COUNT",
                    })
                    continue
                try:
                    class_id = int(parts[0])
                    coords = [float(v) for v in parts[1:]]
                except ValueError:
                    parse_errors.append({
                        "label": str(label_path.relative_to(root)),
                        "line": line_no,
                        "error": "YOLO_PARSE_ERROR",
                    })
                    continue
                if any(v < 0.0 or v > 1.0 for v in coords) or coords[2] <= 0 or coords[3] <= 0:
                    parse_errors.append({
                        "label": str(label_path.relative_to(root)),
                        "line": line_no,
                        "error": "INVALID_NORMALIZED_BOX",
                    })
                    continue
                class_name = names.get(class_id, f"CLASS_{class_id}")
                class_counts[class_name] += 1
                box_count += 1

            split_box_counts[split] += box_count
            rows.append({
                "split": split,
                "image": str(image_path.relative_to(root)).replace("\\", "/"),
                "label": str(label_path.relative_to(root)).replace("\\", "/"),
                "image_sha256": image_sha,
                "origin_key": origin,
                "bbox_count": box_count,
            })

    cross_split_exact = sorted(
        sha for sha, splits in image_hash_splits.items() if len(splits) > 1
    )
    cross_split_origin = sorted(
        key for key, splits in origin_splits.items() if len(splits) > 1
    )
    augmented_origin_groups = sum(1 for count in origin_counts.values() if count > 1)

    observed_labels = set(class_counts)
    label_match = not names or observed_labels.issubset(set(names.values()))
    expected_coverage = expected_labels.issubset(set(names.values())) if names else False

    status = "MITE_PUBLIC_DATASET_AUDITED"
    if missing_labels or parse_errors or cross_split_exact or cross_split_origin:
        status = "MITE_PUBLIC_DATASET_REVIEW_REQUIRED"

    manifest_path = output_dir / "image-manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["split", "image", "label", "image_sha256", "origin_key", "bbox_count"],
        )
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "status": status,
        "source_id": source.source_id,
        "version_or_revision": source.version_or_revision,
        "role": source.nongtori_mapping.get("role"),
        "dataset_root": str(root),
        "class_names": names,
        "class_counts": dict(sorted(class_counts.items())),
        "expected_labels": source.original_labels,
        "expected_labels_present_in_yaml": expected_coverage,
        "observed_labels_valid_against_yaml": label_match,
        "split_image_counts": dict(sorted(split_image_counts.items())),
        "split_box_counts": dict(sorted(split_box_counts.items())),
        "image_count": sum(split_image_counts.values()),
        "bbox_count": sum(split_box_counts.values()),
        "missing_label_count": len(missing_labels),
        "parse_error_count": len(parse_errors),
        "exact_cross_split_duplicate_count": len(cross_split_exact),
        "origin_key_cross_split_count": len(cross_split_origin),
        "augmented_or_reexported_origin_group_count": augmented_origin_groups,
        "exceptions": {
            "missing_label_examples": missing_labels[:30],
            "parse_error_examples": parse_errors[:30],
            "cross_split_exact_sha256_examples": cross_split_exact[:30],
            "cross_split_origin_key_examples": cross_split_origin[:30],
        },
        "manifest": str(manifest_path),
    }
    (output_dir / "audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def acquire_and_audit_mite_public_sources(
    *,
    source_dir: Path,
    raw_root: Path = Path("data/external"),
    audit_root: Path = Path("data/audit/mite-public-v001"),
) -> dict[str, Any]:
    registry = DatasetRegistry(source_dir)
    downloader = DatasetDownloader()
    reports: dict[str, Any] = {}

    for source_id in SOURCES:
        source = registry.get(source_id)
        try:
            result = downloader.download(source, raw_root)
        except Exception as exc:
            raise MitePublicAcquisitionError(
                f"{source_id} acquisition failed: {exc}"
            ) from exc

        report = audit_roboflow_yolo_dataset(
            source,
            result.output_dir,
            Path(audit_root) / source_id,
        )
        report["acquisition"] = result.metadata
        reports[source_id] = report

    statuses = {r["status"] for r in reports.values()}
    overall = (
        "MITE_PUBLIC_ACQUISITION_AUDIT_COMPLETE"
        if statuses == {"MITE_PUBLIC_DATASET_AUDITED"}
        else "MITE_PUBLIC_ACQUISITION_REVIEW_REQUIRED"
    )
    payload = {
        "status": overall,
        "sources": reports,
        "policy": {
            "do_not_merge_source_roles_yet": True,
            "do_not_use_public_test_for_field_claim": True,
            "next_gate": "Review exact class/split/duplicate/augmentation audit before snapshot freeze.",
        },
    }
    Path(audit_root).mkdir(parents=True, exist_ok=True)
    (Path(audit_root) / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload
