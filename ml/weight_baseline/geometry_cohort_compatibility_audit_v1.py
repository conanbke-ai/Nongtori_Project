from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from ml.data_pipeline.dryad_weight_audit import primary_weight_records_from_datasheet
from ml.weight_baseline.geometry_v001 import (
    PRIMARY_MODEL,
    _features,
    _fit_linear_model,
    _grade,
    _predict_linear,
)
from ml.weight_baseline.geometry_v002 import (
    _evaluate,
    _load_cv_assignments,
)

NUMERIC_FIELDS = ("weight_with_calyx_g", "width_mm", "height_mm")
MIN_SHARED_VARIETY_COUNT = 3


def _read_csv(path: Path, label: str) -> list[dict[str, str]]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{label} is empty")
    return rows


def _number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"non-finite {field}: {value!r}")
    return number


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires values")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _numeric_stats(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("numeric stats require values")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {
        "count": len(values),
        "mean": mean,
        "std": math.sqrt(variance),
        "min": min(values),
        "p10": _quantile(values, 0.10),
        "p25": _quantile(values, 0.25),
        "median": _quantile(values, 0.50),
        "p75": _quantile(values, 0.75),
        "p90": _quantile(values, 0.90),
        "max": max(values),
    }


def _pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) != len(y) or len(x) < 2:
        return None
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    dx = [value - mean_x for value in x]
    dy = [value - mean_y for value in y]
    denom = math.sqrt(
        sum(value * value for value in dx)
        * sum(value * value for value in dy)
    )
    if denom <= 1e-12:
        return None
    return sum(a * b for a, b in zip(dx, dy, strict=True)) / denom


def _grade_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(
        _grade(_number(row["weight_with_calyx_g"], "weight_with_calyx_g"))
        for row in rows
    )
    return {
        grade: int(counts.get(grade, 0))
        for grade in (
            "JM_WEIGHT_CANDIDATE",
            "MD_WEIGHT",
            "HI_WEIGHT",
            "SP_WEIGHT",
        )
    }


def _categorical_counts(
    rows: list[dict[str, Any]],
    field: str,
) -> dict[str, int]:
    counts = Counter(str(row.get(field) or "<EMPTY>") for row in rows)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _total_variation(
    left_counts: dict[str, int],
    right_counts: dict[str, int],
) -> float:
    left_total = sum(left_counts.values())
    right_total = sum(right_counts.values())
    if not left_total or not right_total:
        return 0.0
    keys = set(left_counts) | set(right_counts)
    return 0.5 * sum(
        abs(
            left_counts.get(key, 0) / left_total
            - right_counts.get(key, 0) / right_total
        )
        for key in keys
    )


def _cohort_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    weight = [
        _number(row["weight_with_calyx_g"], "weight_with_calyx_g")
        for row in rows
    ]
    width = [_number(row["width_mm"], "width_mm") for row in rows]
    height = [_number(row["height_mm"], "height_mm") for row in rows]
    area = [
        width_value * height_value
        for width_value, height_value in zip(width, height, strict=True)
    ]
    return {
        "count": len(rows),
        "numeric": {
            "weight_with_calyx_g": _numeric_stats(weight),
            "width_mm": _numeric_stats(width),
            "height_mm": _numeric_stats(height),
            "width_x_height_mm2": _numeric_stats(area),
        },
        "grades": _grade_counts(rows),
        "variety_counts": _categorical_counts(rows, "variety"),
        "source_sheet_counts": _categorical_counts(rows, "source_sheet"),
        "photo_counts": _categorical_counts(rows, "photo"),
        "area_weight_pearson": _pearson(area, weight),
    }


def _fit_primary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    x_rows = [_features(row, PRIMARY_MODEL) for row in rows]
    y_values = [
        _number(row["weight_with_calyx_g"], "weight_with_calyx_g")
        for row in rows
    ]
    return _fit_linear_model(x_rows, y_values)


def _predict_primary(
    model: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[float]:
    return [
        _predict_linear(model, _features(row, PRIMARY_MODEL))
        for row in rows
    ]


def _strict_oof(
    strict_train: list[dict[str, Any]],
    assignments: dict[str, int],
) -> tuple[list[float], dict[str, Any]]:
    predictions_by_id: dict[str, float] = {}
    for fold in sorted(set(assignments.values())):
        fit_rows = [
            row
            for row in strict_train
            if assignments[row["fruit_id"]] != fold
        ]
        holdout = [
            row
            for row in strict_train
            if assignments[row["fruit_id"]] == fold
        ]
        model = _fit_primary(fit_rows)
        predicted = _predict_primary(model, holdout)
        for row, prediction in zip(holdout, predicted, strict=True):
            predictions_by_id[row["fruit_id"]] = prediction

    if set(predictions_by_id) != {
        row["fruit_id"] for row in strict_train
    }:
        raise ValueError("strict OOF predictions do not cover official train")

    predicted = [
        predictions_by_id[row["fruit_id"]]
        for row in strict_train
    ]
    actual = [
        _number(row["weight_with_calyx_g"], "weight_with_calyx_g")
        for row in strict_train
    ]
    return predicted, _evaluate(actual, predicted)


def _integrity_check_auxiliary(
    auxiliary_rows: list[dict[str, str]],
    source_records: dict[str, dict[str, Any]],
    strict_all_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in auxiliary_rows:
        fruit_id = str(raw.get("fruit_id") or "").strip()
        if not fruit_id:
            raise ValueError("auxiliary row missing fruit_id")
        if fruit_id in seen:
            raise ValueError(f"duplicate auxiliary fruit_id: {fruit_id}")
        seen.add(fruit_id)
        if fruit_id in strict_all_ids:
            raise ValueError(f"auxiliary fruit overlaps strict cohort: {fruit_id}")
        if str(raw.get("role") or "") != "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE":
            raise ValueError(f"unexpected auxiliary role for {fruit_id}")
        source = source_records.get(fruit_id)
        if source is None:
            raise ValueError(f"auxiliary fruit missing from source datasheet: {fruit_id}")

        for field in NUMERIC_FIELDS:
            csv_value = _number(raw.get(field), field)
            source_value = _number(source.get(field), field)
            if abs(csv_value - source_value) > 1e-9:
                raise ValueError(
                    f"auxiliary source value changed for {fruit_id} {field}: "
                    f"{csv_value} != {source_value}"
                )

        for field in ("variety", "source_sheet", "photo"):
            csv_value = str(raw.get(field) or "")
            source_value = str(source.get(field) or "")
            if csv_value != source_value:
                raise ValueError(
                    f"auxiliary source metadata changed for {fruit_id} {field}: "
                    f"{csv_value!r} != {source_value!r}"
                )

        normalized.append(
            {
                "fruit_id": fruit_id,
                "weight_with_calyx_g": _number(
                    source["weight_with_calyx_g"],
                    "weight_with_calyx_g",
                ),
                "width_mm": _number(source["width_mm"], "width_mm"),
                "height_mm": _number(source["height_mm"], "height_mm"),
                "variety": str(source.get("variety") or ""),
                "source_sheet": str(source.get("source_sheet") or ""),
                "photo": str(source.get("photo") or ""),
            }
        )

    return normalized, {
        "verified": True,
        "checked_rows": len(normalized),
        "numeric_fields": list(NUMERIC_FIELDS),
        "metadata_fields": ["variety", "source_sheet", "photo"],
        "source_values_modified": False,
    }


def _strict_train_rows(
    split_rows: list[dict[str, str]],
    source_records: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str], dict[str, int]]:
    official_counts = Counter(str(row.get("split") or "") for row in split_rows)
    strict_all_ids: set[str] = set()
    train_rows: list[dict[str, Any]] = []
    for row in split_rows:
        fruit_id = str(row.get("fruit_id") or "").strip()
        split = str(row.get("split") or "").strip()
        if not fruit_id:
            raise ValueError("official split row missing fruit_id")
        if fruit_id in strict_all_ids:
            raise ValueError(f"duplicate official fruit_id: {fruit_id}")
        strict_all_ids.add(fruit_id)
        if split not in {"train", "validation", "test"}:
            raise ValueError(f"unexpected official split: {split!r}")
        if fruit_id not in source_records:
            raise ValueError(f"official fruit missing from source datasheet: {fruit_id}")
        if split == "train":
            source = source_records[fruit_id]
            train_rows.append(
                {
                    "fruit_id": fruit_id,
                    "weight_with_calyx_g": _number(
                        source["weight_with_calyx_g"],
                        "weight_with_calyx_g",
                    ),
                    "width_mm": _number(source["width_mm"], "width_mm"),
                    "height_mm": _number(source["height_mm"], "height_mm"),
                    "variety": str(source.get("variety") or ""),
                    "source_sheet": str(source.get("source_sheet") or ""),
                    "photo": str(source.get("photo") or ""),
                }
            )

    return train_rows, strict_all_ids, {
        split: int(official_counts.get(split, 0))
        for split in ("train", "validation", "test")
    }


def _shared_variety_analysis(
    strict_rows: list[dict[str, Any]],
    auxiliary_rows: list[dict[str, Any]],
    strict_predictions_from_aux: list[float],
    auxiliary_predictions_from_strict: list[float],
) -> list[dict[str, Any]]:
    strict_by_variety: dict[str, list[int]] = {}
    aux_by_variety: dict[str, list[int]] = {}
    for index, row in enumerate(strict_rows):
        strict_by_variety.setdefault(
            str(row.get("variety") or "<EMPTY>"),
            [],
        ).append(index)
    for index, row in enumerate(auxiliary_rows):
        aux_by_variety.setdefault(
            str(row.get("variety") or "<EMPTY>"),
            [],
        ).append(index)

    results: list[dict[str, Any]] = []
    for variety in sorted(set(strict_by_variety) & set(aux_by_variety)):
        strict_indexes = strict_by_variety[variety]
        aux_indexes = aux_by_variety[variety]
        if (
            len(strict_indexes) < MIN_SHARED_VARIETY_COUNT
            or len(aux_indexes) < MIN_SHARED_VARIETY_COUNT
        ):
            continue

        strict_subset = [strict_rows[index] for index in strict_indexes]
        aux_subset = [auxiliary_rows[index] for index in aux_indexes]
        strict_actual = [
            float(row["weight_with_calyx_g"]) for row in strict_subset
        ]
        aux_actual = [
            float(row["weight_with_calyx_g"]) for row in aux_subset
        ]
        strict_transfer_pred = [
            strict_predictions_from_aux[index]
            for index in strict_indexes
        ]
        aux_transfer_pred = [
            auxiliary_predictions_from_strict[index]
            for index in aux_indexes
        ]
        results.append(
            {
                "variety": variety,
                "strict_count": len(strict_subset),
                "auxiliary_count": len(aux_subset),
                "strict_summary": {
                    "weight_mean_g": sum(strict_actual) / len(strict_actual),
                    "width_mean_mm": sum(
                        float(row["width_mm"]) for row in strict_subset
                    ) / len(strict_subset),
                    "height_mean_mm": sum(
                        float(row["height_mm"]) for row in strict_subset
                    ) / len(strict_subset),
                },
                "auxiliary_summary": {
                    "weight_mean_g": sum(aux_actual) / len(aux_actual),
                    "width_mean_mm": sum(
                        float(row["width_mm"]) for row in aux_subset
                    ) / len(aux_subset),
                    "height_mean_mm": sum(
                        float(row["height_mm"]) for row in aux_subset
                    ) / len(aux_subset),
                },
                "aux_model_to_strict_metrics": _evaluate(
                    strict_actual,
                    strict_transfer_pred,
                ),
                "strict_model_to_auxiliary_metrics": _evaluate(
                    aux_actual,
                    aux_transfer_pred,
                ),
            }
        )
    return results


def audit_geometry_cohort_compatibility(
    datasheet: Path,
    official_split_csv: Path,
    auxiliary_csv: Path,
    cv_csv: Path,
    output_json: Path,
) -> dict[str, Any]:
    source_records = primary_weight_records_from_datasheet(Path(datasheet))
    if not source_records:
        raise ValueError("Dryad source contains no primary weight records")

    split_rows = _read_csv(official_split_csv, "official split CSV")
    strict_train, strict_all_ids, official_counts = _strict_train_rows(
        split_rows,
        source_records,
    )
    if not strict_train:
        raise ValueError("official train split is empty")

    auxiliary_raw = _read_csv(auxiliary_csv, "auxiliary candidate CSV")
    auxiliary_rows, integrity = _integrity_check_auxiliary(
        auxiliary_raw,
        source_records,
        strict_all_ids,
    )
    if not auxiliary_rows:
        raise ValueError("auxiliary cohort is empty")

    assignments = _load_cv_assignments(
        cv_csv,
        {row["fruit_id"] for row in strict_train},
    )

    strict_oof_pred, strict_oof_metrics = _strict_oof(
        strict_train,
        assignments,
    )

    strict_model = _fit_primary(strict_train)
    aux_model = _fit_primary(auxiliary_rows)

    auxiliary_pred_from_strict = _predict_primary(
        strict_model,
        auxiliary_rows,
    )
    strict_pred_from_aux = _predict_primary(
        aux_model,
        strict_train,
    )

    strict_actual = [
        float(row["weight_with_calyx_g"]) for row in strict_train
    ]
    auxiliary_actual = [
        float(row["weight_with_calyx_g"]) for row in auxiliary_rows
    ]

    strict_summary = _cohort_summary(strict_train)
    auxiliary_summary = _cohort_summary(auxiliary_rows)

    shared_varieties = _shared_variety_analysis(
        strict_train,
        auxiliary_rows,
        strict_pred_from_aux,
        auxiliary_pred_from_strict,
    )

    report = {
        "status": "WEIGHT_GEOMETRY_COHORT_COMPATIBILITY_AUDIT_COMPLETE",
        "contract": "nongtori-weight-geometry-cohort-compatibility.v1",
        "source": "DATA-QUAL-002",
        "primary_target": "weight_with_calyx_g",
        "official_counts": {
            "train_used_for_compatibility": official_counts["train"],
            "validation_locked": official_counts["validation"],
            "test_locked": official_counts["test"],
            "strict_cohort_total": sum(official_counts.values()),
        },
        "auxiliary_count": len(auxiliary_rows),
        "source_value_integrity": integrity,
        "strict_train": strict_summary,
        "auxiliary": auxiliary_summary,
        "distribution_shift": {
            "grade_total_variation": _total_variation(
                strict_summary["grades"],
                auxiliary_summary["grades"],
            ),
            "variety_total_variation": _total_variation(
                strict_summary["variety_counts"],
                auxiliary_summary["variety_counts"],
            ),
            "source_sheet_total_variation": _total_variation(
                strict_summary["source_sheet_counts"],
                auxiliary_summary["source_sheet_counts"],
            ),
            "photo_total_variation": _total_variation(
                strict_summary["photo_counts"],
                auxiliary_summary["photo_counts"],
            ),
            "aux_minus_strict_means": {
                field: (
                    auxiliary_summary["numeric"][field]["mean"]
                    - strict_summary["numeric"][field]["mean"]
                )
                for field in (
                    "weight_with_calyx_g",
                    "width_mm",
                    "height_mm",
                    "width_x_height_mm2",
                )
            },
        },
        "geometry_weight_relation": {
            "strict_train_5fold_oof_metrics": strict_oof_metrics,
            "auxiliary_model_to_strict_train_metrics": _evaluate(
                strict_actual,
                strict_pred_from_aux,
            ),
            "strict_model_to_auxiliary_metrics": _evaluate(
                auxiliary_actual,
                auxiliary_pred_from_strict,
            ),
            "strict_area_weight_pearson": strict_summary[
                "area_weight_pearson"
            ],
            "auxiliary_area_weight_pearson": auxiliary_summary[
                "area_weight_pearson"
            ],
            "note": (
                "Cross-domain metrics test whether geometry->weight relations "
                "transfer between cohorts. They do not alter source labels."
            ),
        },
        "shared_variety_analysis": shared_varieties,
        "decision_gate": {
            "geometry_v003_policy": "HOLD_PENDING_MANUAL_COMPATIBILITY_REVIEW",
            "automatic_reweighting_approved": False,
            "required_review": [
                "variety/source-sheet/photo selection differences",
                "cross-domain geometry-to-weight transfer metrics",
                "shared-variety residual behavior",
            ],
            "reason": (
                "Distribution balancing alone is not evidence that cohorts are "
                "exchangeable. Reweighting stays on hold until compatibility "
                "is reviewed from source-preserving diagnostics."
            ),
        },
        "leakage_guards": {
            "official_validation_used_for_statistics": False,
            "official_test_used_for_statistics": False,
            "strict_auxiliary_overlap": False,
            "source_weight_values_modified": False,
        },
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
            "Audit strict-vs-auxiliary Dryad cohort compatibility before "
            "any geometry reweighting or resampling experiment"
        )
    )
    parser.add_argument(
        "--datasheet",
        type=Path,
        default=Path("data/raw/dryad/DATA-QUAL-002/datasheet.xlsx"),
    )
    parser.add_argument(
        "--official-split",
        type=Path,
        default=Path("data/snapshots/WEIGHT-DRYAD-V001/fruit-splits.csv"),
    )
    parser.add_argument(
        "--auxiliary",
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
        "--output",
        type=Path,
        default=Path(
            "artifacts/weight/geometry-auxiliary-audit-v1/"
            "geometry_cohort_compatibility_audit.json"
        ),
    )
    args = parser.parse_args(argv)

    try:
        report = audit_geometry_cohort_compatibility(
            args.datasheet,
            args.official_split,
            args.auxiliary,
            args.cv_csv,
            args.output,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "WEIGHT_GEOMETRY_COHORT_COMPATIBILITY_AUDIT_BLOCKED",
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
