from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

STRAWBERRY_DS_CLASSES = {
    0: "Green",
    1: "White",
    2: "Early-Turning",
    3: "Turning",
    4: "Late-Turning",
    5: "Red",
}

KGCV_MAIN_STAGES = ["flower", "small g", "green", "white", "turning red", "red", "overripe"]


def audit_strawberry_ds_yolo(labels_dir: Path) -> dict[str, Any]:
    labels_dir = Path(labels_dir)
    files = sorted(labels_dir.rglob("*.txt"))
    class_counts: Counter[str] = Counter()
    errors: list[dict[str, str]] = []
    annotation_count = 0
    empty_files = 0
    for path in files:
        lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        if not lines:
            empty_files += 1
        for line_no, line in enumerate(lines, 1):
            parts = line.split()
            if len(parts) != 5:
                errors.append({"file": str(path), "line": str(line_no), "error": "YOLO_FIELD_COUNT"})
                continue
            try:
                class_id = int(parts[0]); coords = [float(x) for x in parts[1:]]
            except ValueError:
                errors.append({"file": str(path), "line": str(line_no), "error": "YOLO_PARSE_ERROR"})
                continue
            if class_id not in STRAWBERRY_DS_CLASSES:
                errors.append({"file": str(path), "line": str(line_no), "error": "UNKNOWN_CLASS_ID"})
                continue
            if any(v < 0 or v > 1 for v in coords) or coords[2] <= 0 or coords[3] <= 0:
                errors.append({"file": str(path), "line": str(line_no), "error": "INVALID_NORMALIZED_BOX"})
                continue
            class_counts[STRAWBERRY_DS_CLASSES[class_id]] += 1
            annotation_count += 1
    return {
        "source_id": "DATA-RIP-001",
        "format": "YOLO_TXT",
        "label_files": len(files),
        "annotation_count": annotation_count,
        "class_counts": dict(class_counts),
        "empty_label_files": empty_files,
        "errors": errors,
        "status": "AUDITED" if files and not errors else "REVIEW_REQUIRED",
    }


def _parse_kgcv_shape_label(label: str) -> tuple[str, float | None, float | None, float | None]:
    parts = [p.strip() for p in label.split(",")]
    stage = parts[0].lower() if parts else ""
    diameter = length = decimal_stage = None
    if len(parts) >= 2 and parts[1] not in {"", "-1"}: diameter = float(parts[1])
    if len(parts) >= 3 and parts[2] not in {"", "-1"}: length = float(parts[2])
    if len(parts) >= 4 and parts[3] not in {"", "-1"}: decimal_stage = float(parts[3])
    return stage, diameter, length, decimal_stage


def audit_kgcv_json(root: Path) -> dict[str, Any]:
    root = Path(root)
    files = sorted(root.rglob("*.json"))
    class_counts: Counter[str] = Counter()
    decimal_values: dict[str, list[float]] = defaultdict(list)
    errors: list[dict[str, str]] = []
    annotation_count = 0
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            errors.append({"file": str(path), "error": "JSON_PARSE_ERROR"}); continue
        for shape in data.get("shapes", []):
            raw = str(shape.get("label", "")).strip()
            if not raw or raw.startswith("-1"):
                continue
            try:
                stage, diameter, length, decimal_stage = _parse_kgcv_shape_label(raw)
            except ValueError:
                errors.append({"file": str(path), "error": "LABEL_PARSE_ERROR"}); continue
            if stage not in KGCV_MAIN_STAGES:
                errors.append({"file": str(path), "error": f"UNKNOWN_STAGE:{stage}"}); continue
            if diameter is not None and diameter < 0 or length is not None and length < 0:
                errors.append({"file": str(path), "error": "NEGATIVE_SIZE"}); continue
            if decimal_stage is not None and not (0.0 <= decimal_stage <= 1.0):
                errors.append({"file": str(path), "error": "DECIMAL_STAGE_OUT_OF_RANGE"}); continue
            class_counts[stage] += 1
            annotation_count += 1
            if decimal_stage is not None:
                decimal_values[stage].append(decimal_stage)
    decimal_summary = {}
    for stage, values in decimal_values.items():
        ordered = sorted(values)
        n = len(ordered)
        decimal_summary[stage] = {
            "count": n,
            "min": ordered[0],
            "max": ordered[-1],
            "mean": sum(ordered) / n,
            "median": ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2,
        }
    turning = decimal_summary.get("turning red")
    return {
        "source_id": "DATA-RIP-002",
        "format": "LABELME_JSON",
        "json_files": len(files),
        "annotation_count": annotation_count,
        "class_counts": dict(class_counts),
        "decimal_stage_summary": decimal_summary,
        "turning_red_calibration": {
            "status": "READY_FOR_EMPIRICAL_CALIBRATION" if turning and turning["count"] > 0 else "AWAIT_DATA",
            "policy": "DO_NOT_INVENT_THRESHOLD",
            "note": "decimal_stage is within-main-stage progress (DS-0..DS-10 equivalent); derive Nongtori Maturity 2/3 threshold only from observed distribution + field calibration.",
        },
        "errors": errors,
        "status": "AUDITED" if files and not errors else "REVIEW_REQUIRED",
    }


def write_audit_report(report: dict[str, Any], output: Path) -> Path:
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
