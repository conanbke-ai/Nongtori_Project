from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

THRESHOLDS = (12.0, 16.0, 22.0)
GEOMETRY_DEFAULT_COLUMN = "linear_width_height_area_pred_g"
RGB_DEFAULT_COLUMN = "predicted_weight_g"
SPLITS = ("train", "validation", "test")
GRADE_ORDER = {
    "JM_WEIGHT_CANDIDATE": 0,
    "MD_WEIGHT": 1,
    "HI_WEIGHT": 2,
    "SP_WEIGHT": 3,
}


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


def _distance_band(distance: float) -> str:
    if distance <= 0.5:
        return "<=0.5g"
    if distance <= 1.0:
        return "<=1.0g"
    if distance <= 2.0:
        return "<=2.0g"
    if distance <= 3.0:
        return "<=3.0g"
    return ">3.0g"


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (a - left_mean) * (b - right_mean)
        for a, b in zip(left, right, strict=True)
    )
    left_ss = sum((value - left_mean) ** 2 for value in left)
    right_ss = sum((value - right_mean) ** 2 for value in right)
    if left_ss <= 1e-15 or right_ss <= 1e-15:
        return None
    return numerator / math.sqrt(left_ss * right_ss)


def _regression_metrics(
    actual: list[float],
    predicted: list[float],
) -> dict[str, float]:
    if not actual or len(actual) != len(predicted):
        raise ValueError("metrics require aligned non-empty values")
    errors = [
        pred - target
        for target, pred in zip(actual, predicted, strict=True)
    ]
    abs_errors = [abs(error) for error in errors]
    mean_actual = sum(actual) / len(actual)
    ss_total = sum((value - mean_actual) ** 2 for value in actual)
    ss_residual = sum(error * error for error in errors)
    return {
        "mae_g": sum(abs_errors) / len(abs_errors),
        "rmse_g": math.sqrt(ss_residual / len(errors)),
        "r2": 1.0 - ss_residual / ss_total if ss_total > 1e-12 else 0.0,
        "bias_g": sum(errors) / len(errors),
        "max_abs_error_g": max(abs_errors),
    }


def _read_csv(path: Path, prediction_column: str, label: str) -> dict[str, dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{label} prediction file missing: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{label} prediction file is empty")
    required = {"fruit_id", "split", "actual_weight_g", prediction_column}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(
            f"{label} prediction file missing columns: {sorted(missing)}"
        )

    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        fruit_id = str(row.get("fruit_id") or "").strip()
        if not fruit_id:
            raise ValueError(f"{label} prediction row missing fruit_id")
        if fruit_id in indexed:
            raise ValueError(f"{label} duplicate fruit_id: {fruit_id}")
        split = str(row.get("split") or "").strip()
        if split not in SPLITS:
            raise ValueError(f"{label} unexpected split for {fruit_id}: {split!r}")
        indexed[fruit_id] = {
            "fruit_id": fruit_id,
            "split": split,
            "actual_weight_g": _to_float(
                row.get("actual_weight_g"),
                f"{label}.actual_weight_g",
            ),
            "predicted_weight_g": _to_float(
                row.get(prediction_column),
                f"{label}.{prediction_column}",
            ),
        }
    return indexed


def _grade_distance(actual_grade: str, predicted_grade: str) -> int:
    return abs(GRADE_ORDER[actual_grade] - GRADE_ORDER[predicted_grade])


def _split_report(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {}

    actual = [float(item["actual_weight_g"]) for item in items]
    geometry_pred = [float(item["geometry_pred_g"]) for item in items]
    rgb_pred = [float(item["rgb_pred_g"]) for item in items]
    geometry_errors = [float(item["geometry_error_g"]) for item in items]
    rgb_errors = [float(item["rgb_error_g"]) for item in items]
    geometry_abs = [float(item["geometry_abs_error_g"]) for item in items]
    rgb_abs = [float(item["rgb_abs_error_g"]) for item in items]

    winner_counts = Counter(item["abs_error_winner"] for item in items)
    grade_outcomes = Counter(item["grade_outcome"] for item in items)

    geometry_crossings = Counter(
        str(int(threshold))
        for item in items
        for threshold in item["geometry_crossed_thresholds_g"]
    )
    rgb_crossings = Counter(
        str(int(threshold))
        for item in items
        for threshold in item["rgb_crossed_thresholds_g"]
    )

    geometry_crossing_set = {
        (item["fruit_id"], threshold)
        for item in items
        for threshold in item["geometry_crossed_thresholds_g"]
    }
    rgb_crossing_set = {
        (item["fruit_id"], threshold)
        for item in items
        for threshold in item["rgb_crossed_thresholds_g"]
    }

    boundary_bands: dict[str, Any] = {}
    for band in ("<=0.5g", "<=1.0g", "<=2.0g", "<=3.0g", ">3.0g"):
        band_items = [item for item in items if item["distance_band"] == band]
        if not band_items:
            boundary_bands[band] = {
                "n_fruits": 0,
                "geometry_mae_g": None,
                "rgb_mae_g": None,
                "geometry_grade_error_rate": None,
                "rgb_grade_error_rate": None,
            }
            continue
        boundary_bands[band] = {
            "n_fruits": len(band_items),
            "geometry_mae_g": sum(
                float(item["geometry_abs_error_g"]) for item in band_items
            ) / len(band_items),
            "rgb_mae_g": sum(
                float(item["rgb_abs_error_g"]) for item in band_items
            ) / len(band_items),
            "geometry_grade_error_rate": sum(
                not bool(item["geometry_grade_correct"]) for item in band_items
            ) / len(band_items),
            "rgb_grade_error_rate": sum(
                not bool(item["rgb_grade_correct"]) for item in band_items
            ) / len(band_items),
        }

    geometry_grade_correct = sum(
        bool(item["geometry_grade_correct"]) for item in items
    )
    rgb_grade_correct = sum(bool(item["rgb_grade_correct"]) for item in items)
    geometry_severe = sum(
        _grade_distance(item["actual_grade"], item["geometry_grade"]) >= 2
        for item in items
    )
    rgb_severe = sum(
        _grade_distance(item["actual_grade"], item["rgb_grade"]) >= 2
        for item in items
    )

    oracle_abs = [
        min(geometry_value, rgb_value)
        for geometry_value, rgb_value in zip(geometry_abs, rgb_abs, strict=True)
    ]

    return {
        "n_fruits": len(items),
        "geometry": {
            **_regression_metrics(actual, geometry_pred),
            "grade_accuracy": geometry_grade_correct / len(items),
            "grade_error_count": len(items) - geometry_grade_correct,
            "severe_grade_error_count": geometry_severe,
            "threshold_crossing_counts": dict(sorted(geometry_crossings.items())),
        },
        "rgb": {
            **_regression_metrics(actual, rgb_pred),
            "grade_accuracy": rgb_grade_correct / len(items),
            "grade_error_count": len(items) - rgb_grade_correct,
            "severe_grade_error_count": rgb_severe,
            "threshold_crossing_counts": dict(sorted(rgb_crossings.items())),
        },
        "paired": {
            "rgb_minus_geometry_mae_g": (
                sum(rgb_abs) - sum(geometry_abs)
            ) / len(items),
            "rgb_better_abs_error_count": winner_counts.get("RGB", 0),
            "geometry_better_abs_error_count": winner_counts.get("GEOMETRY", 0),
            "exact_tie_count": winner_counts.get("TIE", 0),
            "grade_outcomes": dict(sorted(grade_outcomes.items())),
            "rgb_resolved_geometry_grade_error_count": grade_outcomes.get(
                "RGB_ONLY_CORRECT", 0
            ),
            "rgb_introduced_grade_error_count": grade_outcomes.get(
                "GEOMETRY_ONLY_CORRECT", 0
            ),
            "geometry_crossings_resolved_by_rgb": len(
                geometry_crossing_set - rgb_crossing_set
            ),
            "rgb_crossings_introduced_vs_geometry": len(
                rgb_crossing_set - geometry_crossing_set
            ),
            "shared_threshold_crossings": len(
                geometry_crossing_set & rgb_crossing_set
            ),
            "signed_error_pearson": _pearson(geometry_errors, rgb_errors),
            "absolute_error_pearson": _pearson(geometry_abs, rgb_abs),
            "oracle_lower_bound_mae_g": sum(oracle_abs) / len(oracle_abs),
            "oracle_diagnostic_only": True,
        },
        "boundary_distance_bands": boundary_bands,
        "largest_rgb_improvements": sorted(
            (
                {
                    "fruit_id": item["fruit_id"],
                    "actual_weight_g": item["actual_weight_g"],
                    "geometry_pred_g": item["geometry_pred_g"],
                    "rgb_pred_g": item["rgb_pred_g"],
                    "geometry_abs_error_g": item["geometry_abs_error_g"],
                    "rgb_abs_error_g": item["rgb_abs_error_g"],
                    "improvement_g": (
                        item["geometry_abs_error_g"] - item["rgb_abs_error_g"]
                    ),
                    "actual_grade": item["actual_grade"],
                    "geometry_grade": item["geometry_grade"],
                    "rgb_grade": item["rgb_grade"],
                }
                for item in items
            ),
            key=lambda row: row["improvement_g"],
            reverse=True,
        )[:20],
        "largest_rgb_regressions": sorted(
            (
                {
                    "fruit_id": item["fruit_id"],
                    "actual_weight_g": item["actual_weight_g"],
                    "geometry_pred_g": item["geometry_pred_g"],
                    "rgb_pred_g": item["rgb_pred_g"],
                    "geometry_abs_error_g": item["geometry_abs_error_g"],
                    "rgb_abs_error_g": item["rgb_abs_error_g"],
                    "regression_g": (
                        item["rgb_abs_error_g"] - item["geometry_abs_error_g"]
                    ),
                    "actual_grade": item["actual_grade"],
                    "geometry_grade": item["geometry_grade"],
                    "rgb_grade": item["rgb_grade"],
                }
                for item in items
            ),
            key=lambda row: row["regression_g"],
            reverse=True,
        )[:20],
    }


def compare_weight_predictions(
    geometry_csv: Path,
    rgb_csv: Path,
    output_json: Path,
    output_csv: Path,
    *,
    geometry_prediction_column: str = GEOMETRY_DEFAULT_COLUMN,
    rgb_prediction_column: str = RGB_DEFAULT_COLUMN,
) -> dict[str, Any]:
    geometry = _read_csv(
        geometry_csv,
        geometry_prediction_column,
        "geometry",
    )
    rgb = _read_csv(rgb_csv, rgb_prediction_column, "rgb")

    geometry_ids = set(geometry)
    rgb_ids = set(rgb)
    if geometry_ids != rgb_ids:
        missing_rgb = sorted(geometry_ids - rgb_ids)
        missing_geometry = sorted(rgb_ids - geometry_ids)
        raise ValueError(
            "prediction fruit_id sets differ: "
            f"missing_rgb={missing_rgb[:10]}, "
            f"missing_geometry={missing_geometry[:10]}"
        )

    detailed: list[dict[str, Any]] = []
    for fruit_id in sorted(geometry_ids):
        geometry_row = geometry[fruit_id]
        rgb_row = rgb[fruit_id]
        if geometry_row["split"] != rgb_row["split"]:
            raise ValueError(
                f"split mismatch for {fruit_id}: "
                f"geometry={geometry_row['split']} rgb={rgb_row['split']}"
            )
        actual_geometry = float(geometry_row["actual_weight_g"])
        actual_rgb = float(rgb_row["actual_weight_g"])
        if not math.isclose(actual_geometry, actual_rgb, rel_tol=0, abs_tol=1e-7):
            raise ValueError(
                f"actual_weight_g mismatch for {fruit_id}: "
                f"geometry={actual_geometry} rgb={actual_rgb}"
            )

        actual = actual_geometry
        geometry_pred = float(geometry_row["predicted_weight_g"])
        rgb_pred = float(rgb_row["predicted_weight_g"])
        geometry_error = geometry_pred - actual
        rgb_error = rgb_pred - actual
        geometry_abs = abs(geometry_error)
        rgb_abs = abs(rgb_error)

        if rgb_abs < geometry_abs:
            winner = "RGB"
        elif geometry_abs < rgb_abs:
            winner = "GEOMETRY"
        else:
            winner = "TIE"

        actual_grade = _grade(actual)
        geometry_grade = _grade(geometry_pred)
        rgb_grade = _grade(rgb_pred)
        geometry_correct = geometry_grade == actual_grade
        rgb_correct = rgb_grade == actual_grade
        if geometry_correct and rgb_correct:
            grade_outcome = "BOTH_CORRECT"
        elif geometry_correct:
            grade_outcome = "GEOMETRY_ONLY_CORRECT"
        elif rgb_correct:
            grade_outcome = "RGB_ONLY_CORRECT"
        else:
            grade_outcome = "BOTH_WRONG"

        nearest_threshold = min(
            THRESHOLDS,
            key=lambda threshold: abs(actual - threshold),
        )
        distance = abs(actual - nearest_threshold)
        detailed.append(
            {
                "fruit_id": fruit_id,
                "split": geometry_row["split"],
                "actual_weight_g": actual,
                "geometry_pred_g": geometry_pred,
                "rgb_pred_g": rgb_pred,
                "geometry_error_g": geometry_error,
                "rgb_error_g": rgb_error,
                "geometry_abs_error_g": geometry_abs,
                "rgb_abs_error_g": rgb_abs,
                "rgb_minus_geometry_abs_error_g": rgb_abs - geometry_abs,
                "abs_error_winner": winner,
                "actual_grade": actual_grade,
                "geometry_grade": geometry_grade,
                "rgb_grade": rgb_grade,
                "geometry_grade_correct": geometry_correct,
                "rgb_grade_correct": rgb_correct,
                "grade_outcome": grade_outcome,
                "nearest_threshold_g": nearest_threshold,
                "distance_to_nearest_threshold_g": distance,
                "distance_band": _distance_band(distance),
                "geometry_crossed_thresholds_g": _crossed_thresholds(
                    actual,
                    geometry_pred,
                ),
                "rgb_crossed_thresholds_g": _crossed_thresholds(
                    actual,
                    rgb_pred,
                ),
            }
        )

    split_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in detailed:
        split_rows[row["split"]].append(row)

    report = {
        "status": "WEIGHT_PAIRED_RESIDUAL_AUDIT_COMPLETE",
        "geometry_prediction_column": geometry_prediction_column,
        "rgb_prediction_column": rgb_prediction_column,
        "thresholds_g": list(THRESHOLDS),
        "policy": "ANALYZE_ONLY_NO_TEST_TUNING_NO_FUSION_SELECTION",
        "interpretation": (
            "Paired diagnostics measure complementarity on the frozen split. "
            "Test results must not be used to choose fusion weights or thresholds."
        ),
        "splits": {
            split: _split_report(split_rows[split])
            for split in SPLITS
            if split_rows.get(split)
        },
    }

    output_json = Path(output_json)
    output_csv = Path(output_csv)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fieldnames = [
        "fruit_id",
        "split",
        "actual_weight_g",
        "geometry_pred_g",
        "rgb_pred_g",
        "geometry_error_g",
        "rgb_error_g",
        "geometry_abs_error_g",
        "rgb_abs_error_g",
        "rgb_minus_geometry_abs_error_g",
        "abs_error_winner",
        "actual_grade",
        "geometry_grade",
        "rgb_grade",
        "geometry_grade_correct",
        "rgb_grade_correct",
        "grade_outcome",
        "nearest_threshold_g",
        "distance_to_nearest_threshold_g",
        "distance_band",
        "geometry_crossed_thresholds_g",
        "rgb_crossed_thresholds_g",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in detailed:
            csv_row = dict(row)
            csv_row["geometry_crossed_thresholds_g"] = ",".join(
                str(int(value)) for value in row["geometry_crossed_thresholds_g"]
            )
            csv_row["rgb_crossed_thresholds_g"] = ",".join(
                str(int(value)) for value in row["rgb_crossed_thresholds_g"]
            )
            writer.writerow(csv_row)

    report["paired_csv"] = str(output_csv)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Paired residual audit for Geometry V001 and RGB V001 on identical FRUIT_IDs"
        )
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
        "--output-json",
        type=Path,
        default=Path("artifacts/weight/paired-v001/paired_residual_audit.json"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("artifacts/weight/paired-v001/paired_residuals.csv"),
    )
    parser.add_argument(
        "--geometry-prediction-column",
        default=GEOMETRY_DEFAULT_COLUMN,
    )
    parser.add_argument(
        "--rgb-prediction-column",
        default=RGB_DEFAULT_COLUMN,
    )
    args = parser.parse_args(argv)

    try:
        report = compare_weight_predictions(
            args.geometry,
            args.rgb,
            args.output_json,
            args.output_csv,
            geometry_prediction_column=args.geometry_prediction_column,
            rgb_prediction_column=args.rgb_prediction_column,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "WEIGHT_PAIRED_RESIDUAL_AUDIT_BLOCKED",
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
