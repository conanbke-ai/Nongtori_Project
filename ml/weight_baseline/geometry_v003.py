from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from ml.weight_baseline.geometry_v001 import (
    PRIMARY_MODEL,
    _features,
    _grade,
    _solve_linear_system,
    _to_float,
)
from ml.weight_baseline.geometry_v002 import (
    _evaluate,
    _load_aux_rows,
    _load_cv_assignments,
    _load_strict_rows,
)

AUXILIARY_EFFECTIVE_MASS_RATIOS = (0.25, 0.50, 1.00)
STRICT_ONLY = "STRICT_ONLY"
WEIGHTING_POLICY = "MATCH_AUXILIARY_EFFECTIVE_GRADE_MASS_TO_STRICT_FOLD_TRAIN"


def _weighted_standardizer(
    rows: list[list[float]],
    weights: list[float],
) -> tuple[list[float], list[float]]:
    if not rows or len(rows) != len(weights):
        raise ValueError("weighted standardizer requires aligned non-empty rows/weights")
    if any(weight <= 0 or not math.isfinite(weight) for weight in weights):
        raise ValueError("sample weights must be finite and > 0")
    total_weight = sum(weights)
    columns = len(rows[0])
    means: list[float] = []
    scales: list[float] = []
    for column in range(columns):
        mean = sum(
            weight * row[column]
            for row, weight in zip(rows, weights, strict=True)
        ) / total_weight
        variance = sum(
            weight * ((row[column] - mean) ** 2)
            for row, weight in zip(rows, weights, strict=True)
        ) / total_weight
        means.append(mean)
        scale = math.sqrt(variance)
        scales.append(scale if scale > 1e-12 else 1.0)
    return means, scales


def _fit_weighted_linear(
    rows: list[dict[str, Any]],
    sample_weights: list[float],
    *,
    ridge_alpha: float = 1e-8,
) -> dict[str, Any]:
    x_rows = [_features(row, PRIMARY_MODEL) for row in rows]
    y_values = [float(row["weight_with_calyx_g"]) for row in rows]
    if len(x_rows) != len(sample_weights):
        raise ValueError("weighted fit rows/weights mismatch")

    means, scales = _weighted_standardizer(x_rows, sample_weights)
    standardized = [
        [
            (value - means[index]) / scales[index]
            for index, value in enumerate(row)
        ]
        for row in x_rows
    ]
    design = [[1.0, *row] for row in standardized]
    width = len(design[0])
    xtx = [[0.0 for _ in range(width)] for _ in range(width)]
    xty = [0.0 for _ in range(width)]

    for row, target, weight in zip(
        design, y_values, sample_weights, strict=True
    ):
        for i in range(width):
            xty[i] += weight * row[i] * target
            for j in range(width):
                xtx[i][j] += weight * row[i] * row[j]

    for index in range(1, width):
        xtx[index][index] += ridge_alpha

    return {
        "means": means,
        "scales": scales,
        "coefficients": _solve_linear_system(xtx, xty),
        "ridge_alpha": ridge_alpha,
    }


def _predict(model: dict[str, Any], row: dict[str, Any]) -> float:
    features = _features(row, PRIMARY_MODEL)
    standardized = [
        (value - model["means"][index]) / model["scales"][index]
        for index, value in enumerate(features)
    ]
    values = [1.0, *standardized]
    return sum(
        coefficient * value
        for coefficient, value in zip(
            model["coefficients"], values, strict=True
        )
    )


def _grade_counts(rows: list[dict[str, Any]]) -> Counter[str]:
    return Counter(
        _grade(float(row["weight_with_calyx_g"]))
        for row in rows
    )


def _build_sample_weights(
    strict_train_rows: list[dict[str, Any]],
    auxiliary_rows: list[dict[str, Any]],
    *,
    auxiliary_effective_mass_ratio: float,
) -> tuple[list[dict[str, Any]], list[float], dict[str, Any]]:
    if auxiliary_effective_mass_ratio <= 0:
        raise ValueError("auxiliary_effective_mass_ratio must be > 0")

    strict_counts = _grade_counts(strict_train_rows)
    auxiliary_counts = _grade_counts(auxiliary_rows)
    strict_total = len(strict_train_rows)
    auxiliary_target_mass = strict_total * auxiliary_effective_mass_ratio

    missing_grades = [
        grade
        for grade, count in strict_counts.items()
        if count > 0 and auxiliary_counts.get(grade, 0) == 0
    ]
    if missing_grades:
        raise ValueError(
            f"auxiliary pool lacks strict-train grades: {sorted(missing_grades)}"
        )

    strict_weights = [1.0] * len(strict_train_rows)
    per_grade_aux_weight: dict[str, float] = {}
    effective_grade_mass: dict[str, float] = {}
    for grade, strict_count in strict_counts.items():
        strict_fraction = strict_count / strict_total
        target_mass = auxiliary_target_mass * strict_fraction
        aux_count = auxiliary_counts.get(grade, 0)
        if aux_count <= 0:
            continue
        per_grade_aux_weight[grade] = target_mass / aux_count
        effective_grade_mass[grade] = target_mass

    auxiliary_weights = [
        per_grade_aux_weight[
            _grade(float(row["weight_with_calyx_g"]))
        ]
        for row in auxiliary_rows
    ]
    rows = [*strict_train_rows, *auxiliary_rows]
    weights = [*strict_weights, *auxiliary_weights]

    return rows, weights, {
        "weighting_policy": WEIGHTING_POLICY,
        "strict_training_count": strict_total,
        "auxiliary_row_count": len(auxiliary_rows),
        "auxiliary_effective_mass_ratio": auxiliary_effective_mass_ratio,
        "auxiliary_effective_total_weight": sum(auxiliary_weights),
        "strict_total_weight": sum(strict_weights),
        "strict_grade_counts": dict(sorted(strict_counts.items())),
        "auxiliary_grade_counts": dict(sorted(auxiliary_counts.items())),
        "auxiliary_per_row_weight_by_grade": dict(
            sorted(per_grade_aux_weight.items())
        ),
        "auxiliary_effective_grade_mass": dict(
            sorted(effective_grade_mass.items())
        ),
    }


def _fit_predict_candidate(
    strict_train_rows: list[dict[str, Any]],
    eval_rows: list[dict[str, Any]],
    auxiliary_rows: list[dict[str, Any]],
    *,
    auxiliary_effective_mass_ratio: float | None,
) -> tuple[list[float], dict[str, Any]]:
    if auxiliary_effective_mass_ratio is None:
        rows = list(strict_train_rows)
        weights = [1.0] * len(rows)
        diagnostics = {
            "weighting_policy": "STRICT_ONLY_UNIT_WEIGHT",
            "strict_training_count": len(rows),
            "auxiliary_row_count": 0,
            "auxiliary_effective_mass_ratio": 0.0,
            "auxiliary_effective_total_weight": 0.0,
            "strict_total_weight": float(len(rows)),
        }
    else:
        rows, weights, diagnostics = _build_sample_weights(
            strict_train_rows,
            auxiliary_rows,
            auxiliary_effective_mass_ratio=auxiliary_effective_mass_ratio,
        )

    model = _fit_weighted_linear(rows, weights)
    predicted = [_predict(model, row) for row in eval_rows]
    return predicted, diagnostics


def _candidate_name(ratio: float | None) -> str:
    if ratio is None:
        return STRICT_ONLY
    return f"GRADE_MATCHED_AUX_{int(round(ratio * 100)):03d}"


def _selection_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    metrics = candidate["oof_metrics"]
    ratio = float(candidate["auxiliary_effective_mass_ratio"])
    return (
        int(metrics["grade_error_count"]),
        int(metrics["threshold_crossing_count"]),
        float(metrics["mae_g"]),
        float(metrics["rmse_g"]),
        ratio,
    )


def _oof_candidate(
    strict_train: list[dict[str, Any]],
    auxiliary: list[dict[str, Any]],
    assignments: dict[str, int],
    *,
    ratio: float | None,
) -> dict[str, Any]:
    folds = sorted(set(assignments.values()))
    records: list[dict[str, Any]] = []
    fold_reports: list[dict[str, Any]] = []

    for fold in folds:
        development_validation = [
            row
            for row in strict_train
            if assignments[row["fruit_id"]] == fold
        ]
        development_train = [
            row
            for row in strict_train
            if assignments[row["fruit_id"]] != fold
        ]
        predicted, diagnostics = _fit_predict_candidate(
            development_train,
            development_validation,
            auxiliary,
            auxiliary_effective_mass_ratio=ratio,
        )
        actual = [
            float(row["weight_with_calyx_g"])
            for row in development_validation
        ]
        fold_metrics = _evaluate(actual, predicted)
        fold_reports.append(
            {
                "fold": fold,
                "development_train_count": len(development_train),
                "development_validation_count": len(development_validation),
                "weighting": diagnostics,
                "metrics": fold_metrics,
            }
        )
        for row, prediction in zip(
            development_validation, predicted, strict=True
        ):
            records.append(
                {
                    "fruit_id": row["fruit_id"],
                    "fold": fold,
                    "actual_weight_g": float(row["weight_with_calyx_g"]),
                    "predicted_weight_g": prediction,
                }
            )

    records.sort(key=lambda row: row["fruit_id"])
    if len(records) != len(strict_train):
        raise ValueError("OOF prediction count mismatch")
    if len({row["fruit_id"] for row in records}) != len(records):
        raise ValueError("duplicate OOF fruit")

    metrics = _evaluate(
        [float(row["actual_weight_g"]) for row in records],
        [float(row["predicted_weight_g"]) for row in records],
    )
    return {
        "candidate": _candidate_name(ratio),
        "selection_data": "OFFICIAL_TRAIN_INNER_CV_ONLY",
        "auxiliary_effective_mass_ratio": 0.0 if ratio is None else ratio,
        "oof_metrics": metrics,
        "folds": fold_reports,
        "oof_predictions": records,
    }


def run_geometry_v003(
    split_csv: Path,
    aux_csv: Path,
    cv_csv: Path,
    output_dir: Path,
) -> dict[str, Any]:
    strict_rows = _load_strict_rows(split_csv)
    strict_ids = {row["fruit_id"] for row in strict_rows}
    strict_train = [row for row in strict_rows if row["split"] == "train"]
    official_validation = [
        row for row in strict_rows if row["split"] == "validation"
    ]
    test_count = sum(row["split"] == "test" for row in strict_rows)

    auxiliary = _load_aux_rows(aux_csv, strict_ids)
    assignments = _load_cv_assignments(
        cv_csv,
        {row["fruit_id"] for row in strict_train},
    )

    ratios: list[float | None] = [
        None,
        *AUXILIARY_EFFECTIVE_MASS_RATIOS,
    ]
    candidates = [
        _oof_candidate(
            strict_train,
            auxiliary,
            assignments,
            ratio=ratio,
        )
        for ratio in ratios
    ]
    selected = min(candidates, key=_selection_key)

    selected_ratio = float(selected["auxiliary_effective_mass_ratio"])
    final_ratio = None if selected["candidate"] == STRICT_ONLY else selected_ratio
    validation_predicted, final_weighting = _fit_predict_candidate(
        strict_train,
        official_validation,
        auxiliary,
        auxiliary_effective_mass_ratio=final_ratio,
    )
    validation_actual = [
        float(row["weight_with_calyx_g"])
        for row in official_validation
    ]
    validation_metrics = _evaluate(
        validation_actual,
        validation_predicted,
    )

    strict_validation_predicted, _ = _fit_predict_candidate(
        strict_train,
        official_validation,
        auxiliary,
        auxiliary_effective_mass_ratio=None,
    )
    strict_validation_metrics = _evaluate(
        validation_actual,
        strict_validation_predicted,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    oof_path = output_dir / "development_oof_predictions.csv"
    with oof_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "candidate",
                "fruit_id",
                "fold",
                "actual_weight_g",
                "predicted_weight_g",
            ],
        )
        writer.writeheader()
        for candidate in candidates:
            for row in candidate["oof_predictions"]:
                writer.writerow(
                    {
                        "candidate": candidate["candidate"],
                        **row,
                    }
                )

    validation_path = output_dir / "validation_predictions.csv"
    with validation_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fruit_id",
                "split",
                "actual_weight_g",
                "selected_candidate",
                "selected_predicted_weight_g",
                "strict_reference_predicted_weight_g",
            ],
        )
        writer.writeheader()
        for row, selected_prediction, strict_prediction in zip(
            official_validation,
            validation_predicted,
            strict_validation_predicted,
            strict=True,
        ):
            writer.writerow(
                {
                    "fruit_id": row["fruit_id"],
                    "split": "validation",
                    "actual_weight_g": row["weight_with_calyx_g"],
                    "selected_candidate": selected["candidate"],
                    "selected_predicted_weight_g": selected_prediction,
                    "strict_reference_predicted_weight_g": strict_prediction,
                }
            )

    serializable_candidates = []
    for candidate in candidates:
        serializable_candidates.append(
            {
                key: value
                for key, value in candidate.items()
                if key != "oof_predictions"
            }
        )

    report = {
        "status": "WEIGHT_GEOMETRY_V003_DEVELOPMENT_COMPLETE",
        "contract": "nongtori-weight-geometry-v003.v1",
        "model": PRIMARY_MODEL,
        "candidate_policy": {
            "strict_only": True,
            "auxiliary_weighting": WEIGHTING_POLICY,
            "auxiliary_effective_mass_ratios": list(
                AUXILIARY_EFFECTIVE_MASS_RATIOS
            ),
        },
        "selection_policy": (
            "OFFICIAL_TRAIN_5FOLD_OOF_LEXICOGRAPHIC_"
            "GRADE_ERRORS_CROSSINGS_MAE_RMSE_LOW_AUX_MASS"
        ),
        "official_counts": {
            "train": len(strict_train),
            "validation": len(official_validation),
            "test_locked": test_count,
        },
        "auxiliary_row_count": len(auxiliary),
        "candidate_results": serializable_candidates,
        "selected_candidate": selected["candidate"],
        "selected_auxiliary_effective_mass_ratio": selected_ratio,
        "official_validation_confirmation": {
            "selected_candidate_metrics": validation_metrics,
            "strict_only_reference_metrics": strict_validation_metrics,
            "selection_uses_official_validation": False,
            "final_weighting": final_weighting,
        },
        "test_policy": "LOCKED_NOT_EVALUATED",
        "test_predictions_written": False,
        "development_oof_predictions": str(oof_path),
        "validation_predictions": str(validation_path),
    }
    (output_dir / "geometry_v003_development.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate grade-matched auxiliary weighting for Geometry V3 "
            "using official-train inner CV only"
        )
    )
    parser.add_argument(
        "--split-csv",
        type=Path,
        default=Path("data/snapshots/WEIGHT-DRYAD-V001/fruit-splits.csv"),
    )
    parser.add_argument(
        "--aux-csv",
        type=Path,
        default=Path(
            "artifacts/weight/geometry-auxiliary-audit-v1/"
            "geometry_auxiliary_train_candidates.csv"
        ),
    )
    parser.add_argument(
        "--cv-csv",
        type=Path,
        default=Path("artifacts/weight/development-cv-v1/train_folds.csv"),
    )
    parser.add_argument(
        "--allow-after-compatibility-review",
        action="store_true",
        help=(
            "Explicitly acknowledge that cohort compatibility was reviewed. "
            "Geometry V3 is HOLD by default and must not run before that review."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/geometry-v003"),
    )
    args = parser.parse_args(argv)

    if not args.allow_after_compatibility_review:
        print(
            json.dumps(
                {
                    "status": "WEIGHT_GEOMETRY_V003_HOLD",
                    "reason": (
                        "Cohort compatibility review is required before any "
                        "auxiliary reweighting experiment. Run "
                        "geometry_cohort_compatibility_audit_v1 first and only "
                        "proceed after explicit review."
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 4

    try:
        report = run_geometry_v003(
            args.split_csv,
            args.aux_csv,
            args.cv_csv,
            args.output_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "WEIGHT_GEOMETRY_V003_BLOCKED", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
