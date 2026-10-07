from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

THRESHOLDS = (12.0, 16.0, 22.0)
DEFAULT_MARGINS_G = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)
GRADE_ORDER = {
    "JM_WEIGHT_CANDIDATE": 0,
    "MD_WEIGHT": 1,
    "HI_WEIGHT": 2,
    "SP_WEIGHT": 3,
}
DEFAULT_TARGET_OBSERVED_PRECISION = 0.99
DEFAULT_MINIMUM_AUTO_COUNT = 20
WILSON_Z_95 = 1.959963984540054


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


def _distance_to_nearest_threshold(predicted_weight_g: float) -> float:
    return min(abs(predicted_weight_g - threshold) for threshold in THRESHOLDS)


def _wilson_lower_bound(successes: int, total: int, z: float = WILSON_Z_95) -> float | None:
    if total <= 0:
        return None
    p = successes / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    centre = p + z2 / (2.0 * total)
    adjusted = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * total)) / total)
    return max(0.0, (centre - adjusted) / denominator)


def _read_predictions(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"fusion prediction file missing: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("fusion prediction file is empty")

    required = {"fruit_id", "split", "actual_weight_g", "fusion_pred_g"}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"fusion prediction file missing columns: {sorted(missing)}")

    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        fruit_id = str(row.get("fruit_id") or "").strip()
        if not fruit_id:
            raise ValueError("fusion prediction row missing fruit_id")
        if fruit_id in seen:
            raise ValueError(f"duplicate fruit_id: {fruit_id}")
        seen.add(fruit_id)

        split = str(row.get("split") or "").strip()
        if split not in {"train", "validation", "test"}:
            raise ValueError(f"unexpected split for {fruit_id}: {split!r}")

        actual = _to_float(row.get("actual_weight_g"), "actual_weight_g")
        predicted = _to_float(row.get("fusion_pred_g"), "fusion_pred_g")
        parsed.append(
            {
                "fruit_id": fruit_id,
                "split": split,
                "actual_weight_g": actual,
                "fusion_pred_g": predicted,
                "actual_grade": _grade(actual),
                "predicted_grade": _grade(predicted),
                "distance_to_nearest_threshold_g": _distance_to_nearest_threshold(predicted),
            }
        )
    return parsed


def _candidate_metrics(rows: list[dict[str, Any]], margin_g: float) -> dict[str, Any]:
    auto = [
        row for row in rows
        if float(row["distance_to_nearest_threshold_g"]) >= margin_g
    ]
    remeasure = len(rows) - len(auto)
    correct = sum(row["actual_grade"] == row["predicted_grade"] for row in auto)
    errors = len(auto) - correct
    severe_errors = sum(
        abs(GRADE_ORDER[row["actual_grade"]] - GRADE_ORDER[row["predicted_grade"]]) >= 2
        for row in auto
    )
    precision = correct / len(auto) if auto else None
    coverage = len(auto) / len(rows) if rows else 0.0
    fallback_rate = remeasure / len(rows) if rows else 0.0

    grade_auto_counts = Counter(row["predicted_grade"] for row in auto)
    grade_error_counts = Counter(
        f"{row['actual_grade']}->{row['predicted_grade']}"
        for row in auto
        if row["actual_grade"] != row["predicted_grade"]
    )

    return {
        "margin_g": margin_g,
        "n_total": len(rows),
        "auto_grade_count": len(auto),
        "remeasure_count": remeasure,
        "coverage": coverage,
        "fallback_rate": fallback_rate,
        "observed_precision": precision,
        "observed_error_count": errors,
        "severe_grade_error_count": severe_errors,
        "precision_wilson_95_lower": _wilson_lower_bound(correct, len(auto)),
        "auto_grade_counts": dict(sorted(grade_auto_counts.items())),
        "grade_error_confusion": dict(sorted(grade_error_counts.items())),
    }


def _select_candidate(
    candidates: list[dict[str, Any]],
    *,
    target_observed_precision: float,
    minimum_auto_count: int,
) -> dict[str, Any] | None:
    eligible = [
        candidate
        for candidate in candidates
        if int(candidate["auto_grade_count"]) >= minimum_auto_count
        and candidate["observed_precision"] is not None
        and float(candidate["observed_precision"]) >= target_observed_precision
    ]
    if not eligible:
        return None

    return max(
        eligible,
        key=lambda candidate: (
            float(candidate["coverage"]),
            float(candidate["precision_wilson_95_lower"] or 0.0),
            -float(candidate["margin_g"]),
        ),
    )


def evaluate_selective_auto_grade(
    prediction_csv: Path,
    output_json: Path,
    *,
    target_observed_precision: float = DEFAULT_TARGET_OBSERVED_PRECISION,
    minimum_auto_count: int = DEFAULT_MINIMUM_AUTO_COUNT,
    margins_g: tuple[float, ...] = DEFAULT_MARGINS_G,
) -> dict[str, Any]:
    if not 0 < target_observed_precision <= 1:
        raise ValueError("target_observed_precision must be in (0, 1]")
    if minimum_auto_count < 1:
        raise ValueError("minimum_auto_count must be >= 1")
    if not margins_g or any(margin < 0 for margin in margins_g):
        raise ValueError("margins_g must contain non-negative values")

    rows = _read_predictions(prediction_csv)
    validation = [row for row in rows if row["split"] == "validation"]
    train = [row for row in rows if row["split"] == "train"]
    test_count = sum(row["split"] == "test" for row in rows)
    if not validation:
        raise ValueError("validation split is empty")

    validation_candidates = [
        _candidate_metrics(validation, margin)
        for margin in margins_g
    ]
    selected = _select_candidate(
        validation_candidates,
        target_observed_precision=target_observed_precision,
        minimum_auto_count=minimum_auto_count,
    )

    train_candidates = [
        _candidate_metrics(train, margin)
        for margin in margins_g
    ] if train else []

    if selected is None:
        status = "SELECTIVE_AUTO_GRADE_TARGET_NOT_MET"
        selected_policy = None
    else:
        status = "SELECTIVE_AUTO_GRADE_POLICY_CANDIDATE"
        selected_margin = float(selected["margin_g"])
        selected_train = next(
            (
                candidate for candidate in train_candidates
                if math.isclose(float(candidate["margin_g"]), selected_margin)
            ),
            None,
        )
        selected_policy = {
            "decision_rule": (
                "AUTO_GRADE when predicted distance to nearest fixed "
                "12/16/22g threshold is >= selected_margin_g; otherwise "
                "RE_MEASURE_REQUIRED"
            ),
            "selected_margin_g": selected_margin,
            "selected_from_split": "validation",
            "validation_metrics": selected,
            "train_metrics": selected_train,
        }

    report = {
        "status": status,
        "contract": "nongtori-weight-selective-auto-grade.v1",
        "input_prediction": str(prediction_csv),
        "prediction_model": "FUSION_V001",
        "thresholds_g": list(THRESHOLDS),
        "candidate_margins_g": list(margins_g),
        "selection_policy": (
            "VALIDATION_ONLY_MAX_COVERAGE_SUBJECT_TO_OBSERVED_PRECISION_TARGET"
        ),
        "target_observed_precision": target_observed_precision,
        "minimum_auto_count": minimum_auto_count,
        "validation_candidates": validation_candidates,
        "selected_policy": selected_policy,
        "statistical_note": (
            "Observed precision is not a production reliability guarantee. "
            "Wilson 95% lower bounds are reported because the validation "
            "sample is small; a 99% population-reliability claim requires "
            "substantially more independent field data."
        ),
        "test_policy": "LOCKED_NOT_EVALUATED_FOR_SUCCESSOR_POLICY",
        "test_rows_present_but_not_evaluated": test_count,
        "runtime_source_fallback": (
            "RE_MEASURE_REQUIRED -> SENSOR_MEASURED preferred -> "
            "MANUAL_MEASURED only when sensor measurement is unavailable"
        ),
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate validation-only precision/coverage trade-offs for "
            "Fusion V001 selective auto-grading"
        )
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("artifacts/weight/fusion-v001/fusion_predictions.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/weight/fusion-v001/selective_auto_grade_v001.json"),
    )
    parser.add_argument(
        "--target-observed-precision",
        type=float,
        default=DEFAULT_TARGET_OBSERVED_PRECISION,
    )
    parser.add_argument(
        "--minimum-auto-count",
        type=int,
        default=DEFAULT_MINIMUM_AUTO_COUNT,
    )
    args = parser.parse_args(argv)

    try:
        report = evaluate_selective_auto_grade(
            args.predictions,
            args.output,
            target_observed_precision=float(args.target_observed_precision),
            minimum_auto_count=int(args.minimum_auto_count),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "SELECTIVE_AUTO_GRADE_BLOCKED", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
