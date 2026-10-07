from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from ml.weight_baseline.geometry_v001 import (
    PRIMARY_MODEL,
    _features,
    _fit_linear_model,
    _grade,
    _grade_metrics,
    _metrics,
    _predict_linear,
    _to_float,
)

THRESHOLDS = (12.0, 16.0, 22.0)
REGIME_STRICT_ONLY = "STRICT_ONLY"
REGIME_STRICT_PLUS_AUX = "STRICT_PLUS_AUXILIARY"
REGIME_ORDER = (REGIME_STRICT_ONLY, REGIME_STRICT_PLUS_AUX)


def _read_csv(path: Path, label: str) -> list[dict[str, str]]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{label} is empty")
    return rows


def _crossed_thresholds(actual: float, predicted: float) -> list[float]:
    return [
        threshold
        for threshold in THRESHOLDS
        if (actual < threshold <= predicted) or (predicted < threshold <= actual)
    ]


def _evaluate(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    report: dict[str, Any] = _metrics(actual, predicted)
    report.update(_grade_metrics(actual, predicted))
    actual_grades = [_grade(value) for value in actual]
    predicted_grades = [_grade(value) for value in predicted]
    report["grade_error_count"] = sum(
        expected != observed
        for expected, observed in zip(actual_grades, predicted_grades, strict=True)
    )
    crossing_counts: Counter[str] = Counter()
    for expected, observed in zip(actual, predicted, strict=True):
        for threshold in _crossed_thresholds(expected, observed):
            crossing_counts[str(int(threshold))] += 1
    report["threshold_crossing_count"] = sum(crossing_counts.values())
    report["threshold_crossing_counts"] = dict(sorted(crossing_counts.items()))
    report["n_fruits"] = len(actual)
    return report


def _load_strict_rows(split_csv: Path) -> list[dict[str, Any]]:
    rows = _read_csv(split_csv, "official weight split manifest")
    required = {
        "fruit_id",
        "split",
        "weight_with_calyx_g",
        "width_mm",
        "height_mm",
    }
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"official split manifest missing columns: {sorted(missing)}")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        fruit_id = str(row.get("fruit_id") or "").strip()
        split = str(row.get("split") or "").strip()
        if not fruit_id:
            raise ValueError("official split row missing fruit_id")
        if fruit_id in seen:
            raise ValueError(f"duplicate official fruit_id: {fruit_id}")
        seen.add(fruit_id)
        if split not in {"train", "validation", "test"}:
            raise ValueError(f"unexpected official split: {split!r}")
        normalized.append(
            {
                "fruit_id": fruit_id,
                "split": split,
                "weight_with_calyx_g": _to_float(
                    row.get("weight_with_calyx_g"), "weight_with_calyx_g"
                ),
                "width_mm": _to_float(row.get("width_mm"), "width_mm"),
                "height_mm": _to_float(row.get("height_mm"), "height_mm"),
                "role": "STRICT_RGB_WEIGHT",
            }
        )
    return normalized


def _load_aux_rows(aux_csv: Path, strict_ids: set[str]) -> list[dict[str, Any]]:
    rows = _read_csv(aux_csv, "geometry auxiliary candidate CSV")
    required = {
        "fruit_id",
        "weight_with_calyx_g",
        "width_mm",
        "height_mm",
        "role",
    }
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"auxiliary candidate CSV missing columns: {sorted(missing)}")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        fruit_id = str(row.get("fruit_id") or "").strip()
        if not fruit_id:
            raise ValueError("auxiliary row missing fruit_id")
        if fruit_id in strict_ids:
            raise ValueError(f"auxiliary fruit overlaps strict cohort: {fruit_id}")
        if fruit_id in seen:
            raise ValueError(f"duplicate auxiliary fruit_id: {fruit_id}")
        seen.add(fruit_id)
        if str(row.get("role") or "") != "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE":
            raise ValueError(f"unexpected auxiliary role for {fruit_id}")
        normalized.append(
            {
                "fruit_id": fruit_id,
                "split": "auxiliary_train_only",
                "weight_with_calyx_g": _to_float(
                    row.get("weight_with_calyx_g"), "weight_with_calyx_g"
                ),
                "width_mm": _to_float(row.get("width_mm"), "width_mm"),
                "height_mm": _to_float(row.get("height_mm"), "height_mm"),
                "role": "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
            }
        )
    return normalized


def _load_cv_assignments(cv_csv: Path, train_ids: set[str]) -> dict[str, int]:
    rows = _read_csv(cv_csv, "development CV manifest")
    required = {"fruit_id", "official_split", "cv_fold"}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"development CV manifest missing columns: {sorted(missing)}")

    assignments: dict[str, int] = {}
    for row in rows:
        fruit_id = str(row.get("fruit_id") or "").strip()
        if str(row.get("official_split") or "") != "train":
            raise ValueError(f"non-train row in development CV: {fruit_id}")
        if fruit_id not in train_ids:
            raise ValueError(f"development CV contains non-official-train fruit: {fruit_id}")
        if fruit_id in assignments:
            raise ValueError(f"duplicate fruit in development CV: {fruit_id}")
        try:
            fold = int(row.get("cv_fold") or "")
        except ValueError as exc:
            raise ValueError(f"invalid cv_fold for {fruit_id}") from exc
        if fold < 0:
            raise ValueError(f"negative cv_fold for {fruit_id}")
        assignments[fruit_id] = fold

    if set(assignments) != train_ids:
        missing_ids = sorted(train_ids - set(assignments))[:10]
        extra_ids = sorted(set(assignments) - train_ids)[:10]
        raise ValueError(
            f"development CV does not match official train IDs; "
            f"missing={missing_ids}, extra={extra_ids}"
        )
    return assignments


def _fit_predict(
    train_rows: list[dict[str, Any]],
    eval_rows: list[dict[str, Any]],
) -> list[float]:
    x_train = [_features(row, PRIMARY_MODEL) for row in train_rows]
    y_train = [float(row["weight_with_calyx_g"]) for row in train_rows]
    model = _fit_linear_model(x_train, y_train)
    return [
        _predict_linear(model, _features(row, PRIMARY_MODEL))
        for row in eval_rows
    ]


def _oof_for_regime(
    strict_train: list[dict[str, Any]],
    auxiliary: list[dict[str, Any]],
    assignments: dict[str, int],
    *,
    include_auxiliary: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    folds = sorted(set(assignments.values()))
    oof: list[dict[str, Any]] = []
    fold_reports: list[dict[str, Any]] = []

    for fold in folds:
        holdout = [
            row for row in strict_train
            if assignments[row["fruit_id"]] == fold
        ]
        train = [
            row for row in strict_train
            if assignments[row["fruit_id"]] != fold
        ]
        strict_training_count = len(train)
        if include_auxiliary:
            train = [*train, *auxiliary]
        predicted = _fit_predict(train, holdout)
        actual = [float(row["weight_with_calyx_g"]) for row in holdout]
        metrics = _evaluate(actual, predicted)
        fold_reports.append(
            {
                "fold": fold,
                "training_count": len(train),
                "strict_training_count": strict_training_count,
                "auxiliary_training_count": len(auxiliary) if include_auxiliary else 0,
                "holdout_count": len(holdout),
                "metrics": metrics,
            }
        )
        for row, prediction in zip(holdout, predicted, strict=True):
            oof.append(
                {
                    "fruit_id": row["fruit_id"],
                    "fold": fold,
                    "actual_weight_g": float(row["weight_with_calyx_g"]),
                    "predicted_weight_g": prediction,
                }
            )

    if len(oof) != len(strict_train):
        raise ValueError("OOF prediction count does not match official train count")
    if len({row["fruit_id"] for row in oof}) != len(oof):
        raise ValueError("duplicate FRUIT_ID in OOF predictions")
    return sorted(oof, key=lambda row: row["fruit_id"]), fold_reports


def _selection_key(item: dict[str, Any]) -> tuple[Any, ...]:
    metrics = item["oof_metrics"]
    simpler = 0 if item["regime"] == REGIME_STRICT_ONLY else 1
    return (
        int(metrics["grade_error_count"]),
        int(metrics["threshold_crossing_count"]),
        float(metrics["mae_g"]),
        float(metrics["rmse_g"]),
        simpler,
    )


def run_geometry_v002(
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
    if not strict_train or not official_validation or test_count == 0:
        raise ValueError("official train/validation/test split must all be non-empty")

    auxiliary = _load_aux_rows(aux_csv, strict_ids)
    assignments = _load_cv_assignments(
        cv_csv,
        {row["fruit_id"] for row in strict_train},
    )

    regime_results: list[dict[str, Any]] = []
    oof_by_regime: dict[str, list[dict[str, Any]]] = {}
    for regime in REGIME_ORDER:
        include_auxiliary = regime == REGIME_STRICT_PLUS_AUX
        oof, folds = _oof_for_regime(
            strict_train,
            auxiliary,
            assignments,
            include_auxiliary=include_auxiliary,
        )
        actual = [float(row["actual_weight_g"]) for row in oof]
        predicted = [float(row["predicted_weight_g"]) for row in oof]
        metrics = _evaluate(actual, predicted)
        regime_results.append(
            {
                "regime": regime,
                "selection_data": "OFFICIAL_TRAIN_INNER_CV_ONLY",
                "oof_metrics": metrics,
                "folds": folds,
            }
        )
        oof_by_regime[regime] = oof

    selected = min(regime_results, key=_selection_key)
    selected_regime = str(selected["regime"])
    selected_training = list(strict_train)
    if selected_regime == REGIME_STRICT_PLUS_AUX:
        selected_training.extend(auxiliary)

    validation_predicted = _fit_predict(selected_training, official_validation)
    validation_actual = [
        float(row["weight_with_calyx_g"]) for row in official_validation
    ]
    validation_metrics = _evaluate(validation_actual, validation_predicted)

    strict_reference_predicted = _fit_predict(strict_train, official_validation)
    strict_reference_metrics = _evaluate(
        validation_actual,
        strict_reference_predicted,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    oof_path = output_dir / "development_oof_predictions.csv"
    with oof_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fruit_id",
                "fold",
                "regime",
                "actual_weight_g",
                "predicted_weight_g",
            ],
        )
        writer.writeheader()
        for regime in REGIME_ORDER:
            for row in oof_by_regime[regime]:
                writer.writerow({**row, "regime": regime})

    validation_path = output_dir / "validation_predictions.csv"
    with validation_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fruit_id",
                "split",
                "actual_weight_g",
                "selected_regime",
                "selected_predicted_weight_g",
                "strict_reference_predicted_weight_g",
            ],
        )
        writer.writeheader()
        for row, selected_prediction, strict_prediction in zip(
            official_validation,
            validation_predicted,
            strict_reference_predicted,
            strict=True,
        ):
            writer.writerow(
                {
                    "fruit_id": row["fruit_id"],
                    "split": "validation",
                    "actual_weight_g": row["weight_with_calyx_g"],
                    "selected_regime": selected_regime,
                    "selected_predicted_weight_g": selected_prediction,
                    "strict_reference_predicted_weight_g": strict_prediction,
                }
            )

    report = {
        "status": "WEIGHT_GEOMETRY_V002_DEVELOPMENT_COMPLETE",
        "contract": "nongtori-weight-geometry-v002.v1",
        "model": PRIMARY_MODEL,
        "selection_policy": (
            "OFFICIAL_TRAIN_5FOLD_OOF_LEXICOGRAPHIC_"
            "GRADE_ERRORS_CROSSINGS_MAE_RMSE"
        ),
        "official_counts": {
            "train": len(strict_train),
            "validation": len(official_validation),
            "test_locked": test_count,
        },
        "auxiliary_training_count": len(auxiliary),
        "regime_candidates": regime_results,
        "selected_regime": selected_regime,
        "selected_training_count": len(selected_training),
        "official_validation_confirmation": {
            "selected_regime_metrics": validation_metrics,
            "strict_only_reference_metrics": strict_reference_metrics,
            "selection_uses_official_validation": False,
        },
        "test_policy": "LOCKED_NOT_EVALUATED",
        "test_predictions_written": False,
        "leakage_guards": {
            "official_validation_in_inner_cv": False,
            "official_test_in_inner_cv": False,
            "official_test_evaluated": False,
            "auxiliary_overlap_strict_cohort": False,
        },
        "development_oof_predictions": str(oof_path),
        "validation_predictions": str(validation_path),
    }
    (output_dir / "geometry_v002_development.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare strict-only vs strict+auxiliary Geometry V2 training "
            "using train-only FRUIT_ID CV, then confirm once on official validation"
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
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/geometry-v002"),
    )
    args = parser.parse_args(argv)

    try:
        report = run_geometry_v002(
            args.split_csv,
            args.aux_csv,
            args.cv_csv,
            args.output_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "WEIGHT_GEOMETRY_V002_BLOCKED", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
