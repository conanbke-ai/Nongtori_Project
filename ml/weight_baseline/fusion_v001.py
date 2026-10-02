from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .compare_v001 import (
    GEOMETRY_DEFAULT_COLUMN,
    RGB_DEFAULT_COLUMN,
    TARGET_ALIGNMENT_ATOL_G,
    THRESHOLDS,
)

ALPHA_CANDIDATES = tuple(round(index / 10, 1) for index in range(11))
SPLITS = ("train", "validation", "test")
POLICY = "VALIDATION_ONLY_LEXICOGRAPHIC_GRADE_CROSSING_MAE_RMSE"


def _to_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"non-finite {field}: {value!r}")
    return number


def _grade(weight_g: float) -> str:
    if weight_g >= 22:
        return "SP_WEIGHT"
    if weight_g >= 16:
        return "HI_WEIGHT"
    if weight_g >= 12:
        return "MD_WEIGHT"
    return "JM_WEIGHT_CANDIDATE"


def _crossed_thresholds(actual: float, predicted: float) -> tuple[float, ...]:
    return tuple(
        threshold
        for threshold in THRESHOLDS
        if (actual < threshold <= predicted) or (predicted < threshold <= actual)
    )


def _read_rows(
    geometry_csv: Path,
    rgb_csv: Path,
    *,
    geometry_prediction_column: str,
    rgb_prediction_column: str,
) -> list[dict[str, Any]]:
    with Path(geometry_csv).open(encoding="utf-8", newline="") as handle:
        geometry_rows = list(csv.DictReader(handle))
    with Path(rgb_csv).open(encoding="utf-8", newline="") as handle:
        rgb_rows = list(csv.DictReader(handle))
    if not geometry_rows or not rgb_rows:
        raise ValueError("geometry and RGB prediction files must be non-empty")

    geometry_by_id = {
        str(row["fruit_id"]).strip(): row
        for row in geometry_rows
    }
    rgb_by_id = {
        str(row["fruit_id"]).strip(): row
        for row in rgb_rows
    }
    if set(geometry_by_id) != set(rgb_by_id):
        raise ValueError("geometry and RGB fruit_id sets differ")

    rows: list[dict[str, Any]] = []
    for fruit_id in sorted(geometry_by_id):
        geometry = geometry_by_id[fruit_id]
        rgb = rgb_by_id[fruit_id]
        split = str(geometry["split"]).strip()
        if split not in SPLITS or split != str(rgb["split"]).strip():
            raise ValueError(f"split mismatch for {fruit_id}")

        actual_geometry = _to_float(
            geometry["actual_weight_g"],
            "geometry.actual_weight_g",
        )
        actual_rgb = _to_float(
            rgb["actual_weight_g"],
            "rgb.actual_weight_g",
        )
        delta = abs(actual_geometry - actual_rgb)
        if delta > TARGET_ALIGNMENT_ATOL_G:
            raise ValueError(
                f"actual_weight_g mismatch for {fruit_id}: "
                f"geometry={actual_geometry} rgb={actual_rgb} "
                f"delta={delta:.12g}g"
            )

        rows.append(
            {
                "fruit_id": fruit_id,
                "split": split,
                "actual_weight_g": actual_geometry,
                "geometry_pred_g": _to_float(
                    geometry[geometry_prediction_column],
                    f"geometry.{geometry_prediction_column}",
                ),
                "rgb_pred_g": _to_float(
                    rgb[rgb_prediction_column],
                    f"rgb.{rgb_prediction_column}",
                ),
            }
        )
    return rows


def _metrics(rows: list[dict[str, Any]], prediction_key: str) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot evaluate empty rows")

    errors: list[float] = []
    grade_errors = 0
    severe_grade_errors = 0
    crossing_counts: Counter[str] = Counter()
    confusion: Counter[str] = Counter()

    grade_rank = {
        "JM_WEIGHT_CANDIDATE": 0,
        "MD_WEIGHT": 1,
        "HI_WEIGHT": 2,
        "SP_WEIGHT": 3,
    }

    actual_values = [float(row["actual_weight_g"]) for row in rows]
    for row in rows:
        actual = float(row["actual_weight_g"])
        predicted = float(row[prediction_key])
        error = predicted - actual
        errors.append(error)
        actual_grade = _grade(actual)
        predicted_grade = _grade(predicted)
        confusion[f"{actual_grade}->{predicted_grade}"] += 1
        if actual_grade != predicted_grade:
            grade_errors += 1
        if abs(grade_rank[actual_grade] - grade_rank[predicted_grade]) >= 2:
            severe_grade_errors += 1
        for threshold in _crossed_thresholds(actual, predicted):
            crossing_counts[str(int(threshold))] += 1

    abs_errors = [abs(error) for error in errors]
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors))
    actual_mean = sum(actual_values) / len(actual_values)
    ss_total = sum((value - actual_mean) ** 2 for value in actual_values)
    ss_residual = sum(error * error for error in errors)

    return {
        "n_fruits": len(rows),
        "mae_g": sum(abs_errors) / len(abs_errors),
        "rmse_g": rmse,
        "r2": 1.0 - ss_residual / ss_total if ss_total > 1e-12 else 0.0,
        "bias_g": sum(errors) / len(errors),
        "max_abs_error_g": max(abs_errors),
        "grade_accuracy": 1.0 - grade_errors / len(rows),
        "grade_error_count": grade_errors,
        "severe_grade_error_count": severe_grade_errors,
        "threshold_crossing_count": sum(crossing_counts.values()),
        "threshold_crossing_counts": dict(sorted(crossing_counts.items())),
        "grade_confusion": dict(sorted(confusion.items())),
    }


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    metrics = candidate["validation_metrics"]
    return (
        int(metrics["grade_error_count"]),
        int(metrics["threshold_crossing_count"]),
        float(metrics["mae_g"]),
        float(metrics["rmse_g"]),
        abs(float(candidate["alpha_rgb"]) - 0.5),
        float(candidate["alpha_rgb"]),
    )


def select_alpha(validation_rows: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    if not validation_rows:
        raise ValueError("validation split is empty")

    candidates: list[dict[str, Any]] = []
    for alpha in ALPHA_CANDIDATES:
        candidate_rows: list[dict[str, Any]] = []
        for row in validation_rows:
            fused = (
                alpha * float(row["rgb_pred_g"])
                + (1.0 - alpha) * float(row["geometry_pred_g"])
            )
            candidate_rows.append({**row, "fusion_pred_g": fused})
        candidates.append(
            {
                "alpha_rgb": alpha,
                "alpha_geometry": round(1.0 - alpha, 1),
                "validation_metrics": _metrics(candidate_rows, "fusion_pred_g"),
            }
        )

    selected = min(candidates, key=_candidate_key)
    return float(selected["alpha_rgb"]), candidates


def run_fusion(
    geometry_csv: Path,
    rgb_csv: Path,
    output_dir: Path,
    *,
    geometry_prediction_column: str = GEOMETRY_DEFAULT_COLUMN,
    rgb_prediction_column: str = RGB_DEFAULT_COLUMN,
) -> dict[str, Any]:
    rows = _read_rows(
        geometry_csv,
        rgb_csv,
        geometry_prediction_column=geometry_prediction_column,
        rgb_prediction_column=rgb_prediction_column,
    )
    by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_split[row["split"]].append(row)

    selected_alpha, candidates = select_alpha(by_split["validation"])
    alpha_geometry = 1.0 - selected_alpha

    fused_rows: list[dict[str, Any]] = []
    for row in rows:
        fusion_pred = (
            selected_alpha * float(row["rgb_pred_g"])
            + alpha_geometry * float(row["geometry_pred_g"])
        )
        actual = float(row["actual_weight_g"])
        fused_rows.append(
            {
                **row,
                "fusion_pred_g": fusion_pred,
                "fusion_error_g": fusion_pred - actual,
                "fusion_abs_error_g": abs(fusion_pred - actual),
                "actual_grade": _grade(actual),
                "fusion_grade": _grade(fusion_pred),
            }
        )

    fused_by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in fused_rows:
        fused_by_split[row["split"]].append(row)

    metrics = {
        split: {
            "geometry": _metrics(fused_by_split[split], "geometry_pred_g"),
            "rgb": _metrics(fused_by_split[split], "rgb_pred_g"),
            "fusion": _metrics(fused_by_split[split], "fusion_pred_g"),
        }
        for split in SPLITS
        if fused_by_split.get(split)
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "fusion_baseline.json"
    prediction_path = output_dir / "fusion_predictions.csv"
    if report_path.exists():
        raise FileExistsError(f"immutable fusion result already exists: {report_path}")

    with prediction_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "fruit_id",
            "split",
            "actual_weight_g",
            "geometry_pred_g",
            "rgb_pred_g",
            "fusion_pred_g",
            "fusion_error_g",
            "fusion_abs_error_g",
            "actual_grade",
            "fusion_grade",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in fused_rows:
            writer.writerow({key: row[key] for key in fieldnames})

    report = {
        "status": "WEIGHT_FUSION_V001_COMPLETE",
        "model": "CONVEX_GEOMETRY_RGB_BLEND",
        "geometry_prediction_column": geometry_prediction_column,
        "rgb_prediction_column": rgb_prediction_column,
        "candidate_alpha_rgb": list(ALPHA_CANDIDATES),
        "selection_split": "validation",
        "selection_policy": POLICY,
        "selection_order": [
            "grade_error_count",
            "threshold_crossing_count",
            "mae_g",
            "rmse_g",
            "distance_to_equal_blend",
            "alpha_rgb",
        ],
        "selected_alpha_rgb": selected_alpha,
        "selected_alpha_geometry": alpha_geometry,
        "validation_candidates": candidates,
        "metrics": metrics,
        "test_policy": "REPORT_ONCE_NO_TEST_TUNING",
        "prediction_file": str(prediction_path),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validation-selected convex Geometry + RGB weight fusion V001"
    )
    parser.add_argument(
        "--geometry",
        type=Path,
        default=Path("artifacts/weight/geometry-v001/geometry_predictions.csv"),
    )
    parser.add_argument(
        "--rgb",
        type=Path,
        default=Path("artifacts/weight/rgb-v001/rgb_fruit_predictions.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/fusion-v001"),
    )
    args = parser.parse_args(argv)

    try:
        report = run_fusion(args.geometry, args.rgb, args.output_dir)
    except (FileNotFoundError, FileExistsError, KeyError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "WEIGHT_FUSION_V001_BLOCKED", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
