from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


KGCV_CLASS_NAMES = {
    0: "flower",
    1: "green",
    2: "overripe",
    3: "red",
    4: "small g",
    5: "turning red",
    6: "white",
}

GRADE_THRESHOLDS_G = {
    "SP": 22.0,
    "HI": 16.0,
    "MD": 12.0,
}


@dataclass(frozen=True)
class ObjectMeasurement:
    row_idx: int | None
    category: str
    diameter: float | None
    length: float | None
    decimal_stage: float | None


def _float_or_none(value: Any) -> float | None:
    if value in (None, "", -1, "-1"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _parallel(objects: dict[str, Any], key: str) -> list[Any]:
    value = objects.get(key, [])
    return value if isinstance(value, list) else []


def extract_object_measurements(rows: Iterable[dict[str, Any]]) -> tuple[list[ObjectMeasurement], list[dict[str, Any]]]:
    measurements: list[ObjectMeasurement] = []
    errors: list[dict[str, Any]] = []

    for wrapped in rows:
        row_idx = wrapped.get("row_idx")
        row = wrapped.get("row", wrapped) or {}
        objects = row.get("objects", {}) or {}
        categories = _parallel(objects, "categories")
        diameters = _parallel(objects, "diameter")
        lengths = _parallel(objects, "length")
        stages = _parallel(objects, "decimal_stage")
        sizes = {len(categories), len(diameters), len(lengths), len(stages)}
        if len(sizes) != 1:
            errors.append({
                "row_idx": row_idx,
                "error": "OBJECT_ARRAY_LENGTH_MISMATCH",
                "lengths": {
                    "categories": len(categories),
                    "diameter": len(diameters),
                    "length": len(lengths),
                    "decimal_stage": len(stages),
                },
            })
            continue

        for category_raw, diameter_raw, length_raw, stage_raw in zip(categories, diameters, lengths, stages):
            try:
                category_id = int(category_raw)
            except (TypeError, ValueError):
                errors.append({"row_idx": row_idx, "error": f"INVALID_CLASS_ID:{category_raw}"})
                continue
            category = KGCV_CLASS_NAMES.get(category_id)
            if category is None:
                errors.append({"row_idx": row_idx, "error": f"UNKNOWN_CLASS_ID:{category_id}"})
                continue
            measurements.append(ObjectMeasurement(
                row_idx=row_idx if isinstance(row_idx, int) else None,
                category=category,
                diameter=_float_or_none(diameter_raw),
                length=_float_or_none(length_raw),
                decimal_stage=_float_or_none(stage_raw),
            ))
    return measurements, errors


def summarize_kgcv_quality_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    measurements, errors = extract_object_measurements(rows)
    categories = Counter(item.category for item in measurements)
    diameter_count = sum(item.diameter is not None for item in measurements)
    length_count = sum(item.length is not None for item in measurements)
    stage_count = sum(item.decimal_stage is not None for item in measurements)

    return {
        "annotation_count": len(measurements),
        "class_counts": dict(sorted(categories.items())),
        "availability": {
            "diameter": diameter_count,
            "length": length_count,
            "decimal_stage": stage_count,
            "weight": 0,
        },
        "weight_join_status": "WEIGHT_JOIN_AUDIT_REQUIRED",
        "grade_policy": {
            "thresholds_g": GRADE_THRESHOLDS_G,
            "direct_external_grade_mapping": "PROHIBITED",
            "model_target": "WEIGHT_REGRESSION_THEN_POLICY",
        },
        "errors": errors,
        "status": "AUDITED" if measurements and not errors else "REVIEW_REQUIRED",
    }


def inspect_measurement_manifest(files: Iterable[str]) -> dict[str, Any]:
    normalized = sorted(str(value).strip() for value in files if str(value).strip())
    expected_patterns = {
        "fresh_weight_2022": "data_size_freshWeight_condition_2022_",
        "diameter_2022": "data_taggedFruit_diameter_2022.csv",
        "diameter_2023": "data_taggedFruit_diameter_2023.csv",
        "length_2022": "data_taggedFruit_length_2022.csv",
        "length_2023": "data_taggedFruit_length_2023.csv",
        "fresh_matter_2023": "data_taggedFruit_freshMatter_2023.csv",
    }
    present: dict[str, list[str]] = {}
    for key, pattern in expected_patterns.items():
        present[key] = [name for name in normalized if pattern in name]
    has_weight_file = bool(present["fresh_weight_2022"] or present["fresh_matter_2023"])
    return {
        "files": normalized,
        "recognized": present,
        "has_weight_measurements": has_weight_file,
        "join_key_verified": False,
        "status": "WEIGHT_JOIN_AUDIT_REQUIRED" if has_weight_file else "WEIGHT_MEASUREMENT_FILE_MISSING",
    }


def build_report(rows: Iterable[dict[str, Any]], measurement_files: Iterable[str] = ()) -> dict[str, Any]:
    quality = summarize_kgcv_quality_rows(rows)
    measurement_manifest = inspect_measurement_manifest(measurement_files)
    return {
        "source_id": "DATA-RIP-002",
        "task_family": ["RIPENESS", "DIMENSION", "WEIGHT_FEASIBILITY", "QUALITY_AUXILIARY"],
        "kgcv_hf": quality,
        "zenodo_measurements": measurement_manifest,
        "decision": {
            "dimension_baseline_ready": quality["availability"]["diameter"] > 0 and quality["availability"]["length"] > 0,
            "weight_training_ready": False,
            "next_required_evidence": [
                "measurement_schema",
                "fruit_identity_join_key",
                "image_annotation_to_measurement_join",
                "repeated_measurement_leakage_boundary",
            ],
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--rows-json", type=Path, required=True, help="HF viewer rows JSON fixture/export")
    parser.add_argument("--measurement-files-json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.rows_json.read_text(encoding="utf-8"))
    rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise SystemExit("rows JSON must be a list or contain a 'rows' list")

    files: list[str] = []
    if args.measurement_files_json:
        loaded = json.loads(args.measurement_files_json.read_text(encoding="utf-8"))
        files = loaded if isinstance(loaded, list) else loaded.get("files", [])

    report = build_report(rows, files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["kgcv_hf"]["status"] == "AUDITED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
