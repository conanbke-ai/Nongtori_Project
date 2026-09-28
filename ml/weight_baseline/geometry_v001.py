from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

SNAPSHOT_STATUS = "WEIGHT_SNAPSHOT_FROZEN"
PRIMARY_MODEL = "LINEAR_WIDTH_HEIGHT_AREA"
MODEL_ORDER = (
    "TRAIN_MEAN",
    "LINEAR_WIDTH_HEIGHT",
    PRIMARY_MODEL,
)


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


def _features(row: dict[str, Any], model_name: str) -> list[float]:
    width = _to_float(row.get("width_mm"), "width_mm")
    height = _to_float(row.get("height_mm"), "height_mm")
    if width <= 0 or height <= 0:
        raise ValueError(
            f"geometry must be positive for fruit {row.get('fruit_id')!r}"
        )
    if model_name == "LINEAR_WIDTH_HEIGHT":
        return [width, height]
    if model_name == PRIMARY_MODEL:
        return [width, height, width * height]
    raise ValueError(f"unsupported geometry model: {model_name}")


def _fit_standardizer(rows: list[list[float]]) -> tuple[list[float], list[float]]:
    if not rows:
        raise ValueError("cannot fit standardizer on empty rows")
    columns = len(rows[0])
    means: list[float] = []
    scales: list[float] = []
    for col in range(columns):
        values = [row[col] for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        scale = math.sqrt(variance)
        means.append(mean)
        scales.append(scale if scale > 1e-12 else 1.0)
    return means, scales


def _apply_standardizer(
    row: list[float],
    means: list[float],
    scales: list[float],
) -> list[float]:
    return [
        (value - means[index]) / scales[index]
        for index, value in enumerate(row)
    ]


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    augmented = [list(matrix[row]) + [vector[row]] for row in range(n)]
    for pivot in range(n):
        best = max(range(pivot, n), key=lambda row: abs(augmented[row][pivot]))
        if abs(augmented[best][pivot]) < 1e-12:
            raise ValueError("singular linear system")
        if best != pivot:
            augmented[pivot], augmented[best] = augmented[best], augmented[pivot]
        divisor = augmented[pivot][pivot]
        augmented[pivot] = [value / divisor for value in augmented[pivot]]
        for row in range(n):
            if row == pivot:
                continue
            factor = augmented[row][pivot]
            if factor == 0:
                continue
            augmented[row] = [
                augmented[row][col] - factor * augmented[pivot][col]
                for col in range(n + 1)
            ]
    return [augmented[row][-1] for row in range(n)]


def _fit_linear_model(
    x_rows: list[list[float]],
    y_values: list[float],
    *,
    ridge_alpha: float = 1e-8,
) -> dict[str, Any]:
    means, scales = _fit_standardizer(x_rows)
    standardized = [_apply_standardizer(row, means, scales) for row in x_rows]
    design = [[1.0, *row] for row in standardized]
    width = len(design[0])
    xtx = [[0.0 for _ in range(width)] for _ in range(width)]
    xty = [0.0 for _ in range(width)]
    for row, target in zip(design, y_values, strict=True):
        for i in range(width):
            xty[i] += row[i] * target
            for j in range(width):
                xtx[i][j] += row[i] * row[j]
    for index in range(1, width):
        xtx[index][index] += ridge_alpha
    coefficients = _solve_linear_system(xtx, xty)
    return {
        "means": means,
        "scales": scales,
        "coefficients": coefficients,
        "ridge_alpha": ridge_alpha,
    }


def _predict_linear(model: dict[str, Any], row: list[float]) -> float:
    standardized = _apply_standardizer(
        row,
        list(model["means"]),
        list(model["scales"]),
    )
    values = [1.0, *standardized]
    return sum(
        coefficient * value
        for coefficient, value in zip(model["coefficients"], values, strict=True)
    )


def _metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    if not actual:
        raise ValueError("cannot evaluate empty split")
    errors = [prediction - target for target, prediction in zip(actual, predicted, strict=True)]
    abs_errors = [abs(error) for error in errors]
    squared_errors = [error * error for error in errors]
    mean_actual = sum(actual) / len(actual)
    ss_total = sum((value - mean_actual) ** 2 for value in actual)
    ss_residual = sum(squared_errors)
    r2 = 1.0 - (ss_residual / ss_total) if ss_total > 1e-12 else 0.0
    return {
        "mae_g": sum(abs_errors) / len(abs_errors),
        "rmse_g": math.sqrt(sum(squared_errors) / len(squared_errors)),
        "r2": r2,
        "bias_g": sum(errors) / len(errors),
        "max_abs_error_g": max(abs_errors),
    }


def _grade_metrics(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    actual_grades = [_grade(value) for value in actual]
    predicted_grades = [_grade(value) for value in predicted]
    correct = sum(
        expected == observed
        for expected, observed in zip(actual_grades, predicted_grades, strict=True)
    )
    confusion: Counter[str] = Counter(
        f"{expected}->{observed}"
        for expected, observed in zip(actual_grades, predicted_grades, strict=True)
    )
    return {
        "grade_accuracy": correct / len(actual_grades),
        "grade_confusion": dict(sorted(confusion.items())),
    }


def _read_snapshot(snapshot_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    descriptor_path = snapshot_dir / "WEIGHT_SNAPSHOT.json"
    split_path = snapshot_dir / "fruit-splits.csv"
    if not descriptor_path.exists():
        raise FileNotFoundError(f"weight snapshot descriptor missing: {descriptor_path}")
    if not split_path.exists():
        raise FileNotFoundError(f"weight fruit split manifest missing: {split_path}")
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    if descriptor.get("status") != SNAPSHOT_STATUS:
        raise ValueError(
            f"weight snapshot is not frozen: {descriptor.get('status')!r}"
        )
    if descriptor.get("split_group") != "FRUIT_ID":
        raise ValueError("weight baseline requires FRUIT_ID atomic split")
    if descriptor.get("primary_target") != "weight_with_calyx_g":
        raise ValueError("unexpected weight target contract")

    with split_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != int(descriptor.get("fruit_count") or 0):
        raise ValueError("fruit split manifest count does not match descriptor")
    seen: set[str] = set()
    for row in rows:
        fruit_id = str(row.get("fruit_id") or "").strip()
        if not fruit_id:
            raise ValueError("fruit split row missing fruit_id")
        if fruit_id in seen:
            raise ValueError(f"duplicate fruit_id in split manifest: {fruit_id}")
        seen.add(fruit_id)
        if row.get("split") not in {"train", "validation", "test"}:
            raise ValueError(f"unexpected split for fruit {fruit_id}: {row.get('split')!r}")
    return descriptor, rows


def run_geometry_baseline(
    snapshot_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    snapshot_dir = Path(snapshot_dir)
    output_dir = Path(output_dir)
    descriptor, rows = _read_snapshot(snapshot_dir)

    split_rows = {
        split: [row for row in rows if row["split"] == split]
        for split in ("train", "validation", "test")
    }
    for split, items in split_rows.items():
        if not items:
            raise ValueError(f"weight snapshot has empty {split} split")

    targets = {
        split: [_to_float(row["weight_with_calyx_g"], "weight_with_calyx_g") for row in items]
        for split, items in split_rows.items()
    }

    train_mean = sum(targets["train"]) / len(targets["train"])
    model_results: dict[str, Any] = {}
    predictions_by_model: dict[str, dict[str, list[float]]] = {}

    for model_name in MODEL_ORDER:
        predictions_by_model[model_name] = {}
        if model_name == "TRAIN_MEAN":
            fit_payload = {"train_mean_g": train_mean}
            for split in ("train", "validation", "test"):
                predictions_by_model[model_name][split] = [
                    train_mean for _ in split_rows[split]
                ]
        else:
            train_x = [_features(row, model_name) for row in split_rows["train"]]
            fit_payload = _fit_linear_model(train_x, targets["train"])
            fit_payload["feature_names"] = (
                ["width_mm", "height_mm"]
                if model_name == "LINEAR_WIDTH_HEIGHT"
                else ["width_mm", "height_mm", "width_x_height"]
            )
            for split in ("train", "validation", "test"):
                predictions_by_model[model_name][split] = [
                    _predict_linear(fit_payload, _features(row, model_name))
                    for row in split_rows[split]
                ]

        evaluations: dict[str, Any] = {}
        for split in ("train", "validation", "test"):
            base = _metrics(targets[split], predictions_by_model[model_name][split])
            base.update(_grade_metrics(targets[split], predictions_by_model[model_name][split]))
            base["n_fruits"] = len(split_rows[split])
            evaluations[split] = base
        model_results[model_name] = {
            "fit": fit_payload,
            "metrics": evaluations,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = output_dir / "geometry_predictions.csv"
    with prediction_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "fruit_id",
            "split",
            "width_mm",
            "height_mm",
            "actual_weight_g",
            *[f"{name.lower()}_pred_g" for name in MODEL_ORDER],
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for split in ("train", "validation", "test"):
            for index, row in enumerate(split_rows[split]):
                writer.writerow(
                    {
                        "fruit_id": row["fruit_id"],
                        "split": split,
                        "width_mm": row["width_mm"],
                        "height_mm": row["height_mm"],
                        "actual_weight_g": targets[split][index],
                        **{
                            f"{name.lower()}_pred_g": predictions_by_model[name][split][index]
                            for name in MODEL_ORDER
                        },
                    }
                )

    report = {
        "status": "GEOMETRY_BASELINE_COMPLETE",
        "snapshot_id": descriptor.get("snapshot_id"),
        "task": "STRAWBERRY_WEIGHT_REGRESSION",
        "unit_of_analysis": "FRUIT_ID",
        "primary_target": "weight_with_calyx_g",
        "models": model_results,
        "primary_model": PRIMARY_MODEL,
        "selection_policy": "PRIMARY_MODEL_PREDECLARED_NO_VALIDATION_SELECTION",
        "test_policy": "REPORT_ONCE_NO_TEST_TUNING",
        "split_counts": {
            split: len(items) for split, items in split_rows.items()
        },
        "prediction_file": str(prediction_path),
    }
    (output_dir / "geometry_baseline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run fixed geometry-only WEIGHT-DRYAD-V001 baselines"
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=Path("data/snapshots/WEIGHT-DRYAD-V001"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/geometry-v001"),
    )
    args = parser.parse_args(argv)
    try:
        report = run_geometry_baseline(args.snapshot_dir, args.output_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"status": "GEOMETRY_BASELINE_BLOCKED", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
