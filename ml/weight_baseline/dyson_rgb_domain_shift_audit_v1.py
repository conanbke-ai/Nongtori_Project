from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


THRESHOLDS = (12.0, 16.0, 22.0)


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


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("cannot compute quantile of empty values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        raise ValueError("distribution requires non-empty values")
    ordered = sorted(values)
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    grades = Counter(_grade(value) for value in values)
    return {
        "count": len(values),
        "min_g": ordered[0],
        "q05_g": _quantile(ordered, 0.05),
        "q25_g": _quantile(ordered, 0.25),
        "median_g": _quantile(ordered, 0.50),
        "q75_g": _quantile(ordered, 0.75),
        "q95_g": _quantile(ordered, 0.95),
        "max_g": ordered[-1],
        "mean_g": mean,
        "std_g": math.sqrt(variance),
        "grade_counts": dict(sorted(grades.items())),
        "grade_proportions": {
            grade: grades.get(grade, 0) / len(values)
            for grade in (
                "JM_WEIGHT_CANDIDATE",
                "MD_WEIGHT",
                "HI_WEIGHT",
                "SP_WEIGHT",
            )
        },
    }


def _total_variation(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    return 0.5 * sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys)


def _prediction_metrics(rows: list[dict[str, float]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("prediction metrics require non-empty rows")
    errors = [row["predicted"] - row["actual"] for row in rows]
    abs_errors = [abs(value) for value in errors]
    squared = [value * value for value in errors]
    mean_actual = sum(row["actual"] for row in rows) / len(rows)
    ss_total = sum((row["actual"] - mean_actual) ** 2 for row in rows)
    ss_residual = sum(squared)
    return {
        "count": len(rows),
        "mae_g": sum(abs_errors) / len(abs_errors),
        "rmse_g": math.sqrt(sum(squared) / len(squared)),
        "bias_g": sum(errors) / len(errors),
        "r2": 1.0 - ss_residual / ss_total if ss_total > 1e-12 else 0.0,
        "max_abs_error_g": max(abs_errors),
    }


def _weight_bands(rows: list[dict[str, float]]) -> list[dict[str, Any]]:
    bands = [
        ("LT_12G", float("-inf"), 12.0),
        ("12_TO_LT_16G", 12.0, 16.0),
        ("16_TO_LT_22G", 16.0, 22.0),
        ("GE_22G", 22.0, float("inf")),
    ]
    output: list[dict[str, Any]] = []
    for name, lower, upper in bands:
        subset = [
            row for row in rows
            if row["actual"] >= lower and row["actual"] < upper
        ]
        if not subset:
            output.append({"band": name, "count": 0})
            continue
        metrics = _prediction_metrics(subset)
        output.append({"band": name, **metrics})
    return output


def run_domain_shift_audit(
    *,
    dryad_snapshot_dir: Path,
    dyson_predictions_csv: Path,
    output_dir: Path,
) -> dict[str, Any]:
    dryad_snapshot_dir = Path(dryad_snapshot_dir)
    dyson_predictions_csv = Path(dyson_predictions_csv)
    output_dir = Path(output_dir)

    split_path = dryad_snapshot_dir / "fruit-splits.csv"
    if not split_path.is_file():
        raise FileNotFoundError(f"Dryad fruit split manifest missing: {split_path}")
    if not dyson_predictions_csv.is_file():
        raise FileNotFoundError(f"Dyson berry predictions missing: {dyson_predictions_csv}")

    with split_path.open(encoding="utf-8", newline="") as handle:
        dryad_rows = list(csv.DictReader(handle))
    dryad_test = [
        _to_float(row["weight_with_calyx_g"], "weight_with_calyx_g")
        for row in dryad_rows
        if row.get("split") == "test"
    ]
    if not dryad_test:
        raise ValueError("Dryad test split is empty")

    with dyson_predictions_csv.open(encoding="utf-8", newline="") as handle:
        raw_dyson = list(csv.DictReader(handle))
    dyson_rows = [
        {
            "actual": _to_float(row["actual_weight_g"], "actual_weight_g"),
            "predicted": _to_float(row["predicted_weight_g"], "predicted_weight_g"),
        }
        for row in raw_dyson
    ]
    if not dyson_rows:
        raise ValueError("Dyson prediction file is empty")

    dyson_actual = [row["actual"] for row in dyson_rows]
    dryad_dist = _distribution(dryad_test)
    dyson_dist = _distribution(dyson_actual)
    grade_tv = _total_variation(
        dryad_dist["grade_proportions"],
        dyson_dist["grade_proportions"],
    )

    report = {
        "status": "DYSON_RGB_DOMAIN_SHIFT_AUDIT_COMPLETE",
        "comparison": "DRYAD_TEST_VS_DYSON_EXTERNAL_REFERENCE",
        "dryad_test_distribution": dryad_dist,
        "dyson_distribution": dyson_dist,
        "distribution_shift": {
            "mean_weight_delta_g": dyson_dist["mean_g"] - dryad_dist["mean_g"],
            "median_weight_delta_g": dyson_dist["median_g"] - dryad_dist["median_g"],
            "std_delta_g": dyson_dist["std_g"] - dryad_dist["std_g"],
            "grade_total_variation": grade_tv,
        },
        "dyson_model_metrics": _prediction_metrics(dyson_rows),
        "dyson_actual_weight_bands": _weight_bands(dyson_rows),
        "interpretation_guard": (
            "This audit quantifies target-distribution shift and error structure only. "
            "It does not prove causality and must not be used to retune the frozen RGB V001 model."
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "dyson_rgb_domain_shift_audit.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report["artifact"] = str(output_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit Dryad-vs-Dyson target distribution shift for RGB V001"
    )
    parser.add_argument(
        "--dryad-snapshot-dir",
        type=Path,
        default=Path("data/snapshots/WEIGHT-DRYAD-V001"),
    )
    parser.add_argument(
        "--dyson-predictions-csv",
        type=Path,
        default=Path("artifacts/weight/dyson-external-rgb-v001/dyson_rgb_berry_predictions.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/dyson-external-rgb-v001"),
    )
    args = parser.parse_args(argv)

    try:
        report = run_domain_shift_audit(
            dryad_snapshot_dir=args.dryad_snapshot_dir,
            dyson_predictions_csv=args.dyson_predictions_csv,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"status":"DYSON_RGB_DOMAIN_SHIFT_AUDIT_BLOCKED","error":str(exc)}, ensure_ascii=False, indent=2))
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
