from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

THRESHOLDS = (12.0, 16.0, 22.0)
DEFAULT_PREDICTION_COLUMN = "linear_width_height_area_pred_g"


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


def _crossed_thresholds(actual: float, predicted: float) -> list[float]:
    crossed: list[float] = []
    for threshold in THRESHOLDS:
        if (actual < threshold <= predicted) or (predicted < threshold <= actual):
            crossed.append(threshold)
    return crossed


def _band_key(distance: float) -> str:
    if distance <= 0.5:
        return "<=0.5g"
    if distance <= 1.0:
        return "<=1.0g"
    if distance <= 2.0:
        return "<=2.0g"
    if distance <= 3.0:
        return "<=3.0g"
    return ">3.0g"


def audit_threshold_residuals(
    prediction_csv: Path,
    output_json: Path,
    *,
    prediction_column: str = DEFAULT_PREDICTION_COLUMN,
) -> dict[str, Any]:
    prediction_csv = Path(prediction_csv)
    output_json = Path(output_json)
    if not prediction_csv.exists():
        raise FileNotFoundError(f"geometry prediction file missing: {prediction_csv}")

    with prediction_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("geometry prediction file is empty")
    if prediction_column not in rows[0]:
        raise ValueError(f"prediction column missing: {prediction_column}")

    split_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    detailed: list[dict[str, Any]] = []
    for row in rows:
        split = str(row.get("split") or "").strip()
        if split not in {"train", "validation", "test"}:
            raise ValueError(f"unexpected split: {split!r}")
        fruit_id = str(row.get("fruit_id") or "").strip()
        if not fruit_id:
            raise ValueError("prediction row missing fruit_id")
        actual = _to_float(row.get("actual_weight_g"), "actual_weight_g")
        predicted = _to_float(row.get(prediction_column), prediction_column)
        error = predicted - actual
        actual_grade = _grade(actual)
        predicted_grade = _grade(predicted)
        nearest_threshold = min(THRESHOLDS, key=lambda threshold: abs(actual - threshold))
        distance = abs(actual - nearest_threshold)
        crossed = _crossed_thresholds(actual, predicted)
        item = {
            "fruit_id": fruit_id,
            "split": split,
            "actual_weight_g": actual,
            "predicted_weight_g": predicted,
            "error_g": error,
            "abs_error_g": abs(error),
            "actual_grade": actual_grade,
            "predicted_grade": predicted_grade,
            "grade_correct": actual_grade == predicted_grade,
            "nearest_threshold_g": nearest_threshold,
            "distance_to_nearest_threshold_g": distance,
            "distance_band": _band_key(distance),
            "crossed_thresholds_g": crossed,
        }
        detailed.append(item)
        split_rows[split].append(item)

    split_reports: dict[str, Any] = {}
    for split in ("train", "validation", "test"):
        items = split_rows.get(split, [])
        if not items:
            continue
        grade_errors = [item for item in items if not item["grade_correct"]]
        crossing_counts = Counter(
            str(int(threshold))
            for item in items
            for threshold in item["crossed_thresholds_g"]
        )
        band_counts = Counter(item["distance_band"] for item in items)
        band_grade_errors = Counter(
            item["distance_band"] for item in grade_errors
        )
        threshold_reports: dict[str, Any] = {}
        for threshold in THRESHOLDS:
            key = str(int(threshold))
            near = [
                item for item in items
                if abs(item["actual_weight_g"] - threshold) <= 2.0
            ]
            near_grade_errors = [item for item in near if not item["grade_correct"]]
            threshold_reports[key] = {
                "within_2g_count": len(near),
                "within_2g_grade_error_count": len(near_grade_errors),
                "within_2g_grade_error_rate": (
                    len(near_grade_errors) / len(near) if near else 0.0
                ),
                "crossing_count": crossing_counts.get(key, 0),
            }

        split_reports[split] = {
            "n_fruits": len(items),
            "grade_error_count": len(grade_errors),
            "grade_error_rate": len(grade_errors) / len(items),
            "mean_abs_error_g": sum(item["abs_error_g"] for item in items) / len(items),
            "threshold_crossing_counts": dict(sorted(crossing_counts.items())),
            "distance_band_counts": dict(sorted(band_counts.items())),
            "distance_band_grade_error_counts": dict(sorted(band_grade_errors.items())),
            "thresholds": threshold_reports,
            "top_abs_errors": sorted(
                (
                    {
                        "fruit_id": item["fruit_id"],
                        "actual_weight_g": item["actual_weight_g"],
                        "predicted_weight_g": item["predicted_weight_g"],
                        "abs_error_g": item["abs_error_g"],
                        "actual_grade": item["actual_grade"],
                        "predicted_grade": item["predicted_grade"],
                    }
                    for item in items
                ),
                key=lambda item: item["abs_error_g"],
                reverse=True,
            )[:20],
        }

    report = {
        "status": "WEIGHT_THRESHOLD_RESIDUAL_AUDIT_COMPLETE",
        "prediction_column": prediction_column,
        "thresholds_g": list(THRESHOLDS),
        "policy": "ANALYZE_ONLY_NO_THRESHOLD_TUNING",
        "splits": split_reports,
        "grade_error_fruits": [
            item for item in detailed if not item["grade_correct"]
        ],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit 12/16/22g boundary residuals from the geometry baseline"
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("artifacts/weight/geometry-v001/geometry_predictions.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/weight/geometry-v001/threshold_residual_audit.json"),
    )
    parser.add_argument(
        "--prediction-column",
        default=DEFAULT_PREDICTION_COLUMN,
    )
    args = parser.parse_args(argv)
    try:
        report = audit_threshold_residuals(
            args.predictions,
            args.output,
            prediction_column=args.prediction_column,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"status": "WEIGHT_THRESHOLD_RESIDUAL_AUDIT_BLOCKED", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
