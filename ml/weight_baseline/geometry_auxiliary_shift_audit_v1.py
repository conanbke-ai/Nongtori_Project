from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

NUMERIC_FIELDS = ("weight_with_calyx_g", "width_mm", "height_mm")
GRADE_ORDER = ("JM_WEIGHT_CANDIDATE", "MD_WEIGHT", "HI_WEIGHT", "SP_WEIGHT")


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


def _grade(weight_g: float) -> str:
    if weight_g >= 22:
        return "SP_WEIGHT"
    if weight_g >= 16:
        return "HI_WEIGHT"
    if weight_g >= 12:
        return "MD_WEIGHT"
    return "JM_WEIGHT_CANDIDATE"


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


def _numeric_stats(rows: list[dict[str, Any]], field: str) -> dict[str, float]:
    values = [_number(row[field], field) for row in rows]
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


def _grade_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(_grade(_number(row["weight_with_calyx_g"], "weight_with_calyx_g")) for row in rows)
    total = len(rows)
    return {
        "counts": {grade: int(counts.get(grade, 0)) for grade in GRADE_ORDER},
        "fractions": {
            grade: (counts.get(grade, 0) / total if total else 0.0)
            for grade in GRADE_ORDER
        },
    }


def _categorical_counts(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(row.get(field) or "<EMPTY>") for row in rows)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _normalized_l1(left: dict[str, int], right: dict[str, int]) -> float:
    left_total = sum(left.values())
    right_total = sum(right.values())
    keys = set(left) | set(right)
    if not left_total or not right_total:
        return 0.0
    return 0.5 * sum(
        abs(left.get(key, 0) / left_total - right.get(key, 0) / right_total)
        for key in keys
    )


def audit_geometry_auxiliary_shift(
    official_split_csv: Path,
    auxiliary_csv: Path,
    output_json: Path,
) -> dict[str, Any]:
    official = _read_csv(official_split_csv, "official split CSV")
    required_official = {"fruit_id", "split", *NUMERIC_FIELDS}
    missing = required_official - set(official[0])
    if missing:
        raise ValueError(f"official split CSV missing columns: {sorted(missing)}")

    strict_train = [row for row in official if str(row.get("split") or "") == "train"]
    validation_count = sum(str(row.get("split") or "") == "validation" for row in official)
    test_count = sum(str(row.get("split") or "") == "test" for row in official)
    if not strict_train or not validation_count or not test_count:
        raise ValueError("official train/validation/test must all be non-empty")

    auxiliary = _read_csv(auxiliary_csv, "auxiliary candidate CSV")
    required_aux = {"fruit_id", *NUMERIC_FIELDS, "variety", "source_sheet", "role"}
    missing = required_aux - set(auxiliary[0])
    if missing:
        raise ValueError(f"auxiliary candidate CSV missing columns: {sorted(missing)}")
    if any(
        str(row.get("role") or "") != "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE"
        for row in auxiliary
    ):
        raise ValueError("unexpected role in auxiliary candidate CSV")

    strict_ids = {str(row["fruit_id"]) for row in strict_train}
    aux_ids = {str(row["fruit_id"]) for row in auxiliary}
    overlap = sorted(strict_ids & aux_ids)
    if overlap:
        raise ValueError(f"strict train/auxiliary overlap: {overlap[:10]}")

    strict_grades = _grade_stats(strict_train)
    aux_grades = _grade_stats(auxiliary)
    strict_grade_counts = strict_grades["counts"]
    aux_grade_counts = aux_grades["counts"]

    strict_numeric = {
        field: _numeric_stats(strict_train, field)
        for field in NUMERIC_FIELDS
    }
    aux_numeric = {
        field: _numeric_stats(auxiliary, field)
        for field in NUMERIC_FIELDS
    }

    grade_shift = _normalized_l1(strict_grade_counts, aux_grade_counts)
    numeric_mean_shifts = {
        field: aux_numeric[field]["mean"] - strict_numeric[field]["mean"]
        for field in NUMERIC_FIELDS
    }

    report = {
        "status": "WEIGHT_GEOMETRY_AUXILIARY_SHIFT_AUDIT_COMPLETE",
        "contract": "nongtori-weight-geometry-auxiliary-shift.v1",
        "official_counts": {
            "train": len(strict_train),
            "validation_locked": validation_count,
            "test_locked": test_count,
        },
        "auxiliary_count": len(auxiliary),
        "strict_train": {
            "numeric": strict_numeric,
            "grades": strict_grades,
        },
        "auxiliary": {
            "numeric": aux_numeric,
            "grades": aux_grades,
            "variety_counts": _categorical_counts(auxiliary, "variety"),
            "source_sheet_counts": _categorical_counts(auxiliary, "source_sheet"),
            "photo_counts": _categorical_counts(auxiliary, "photo"),
        },
        "shift_summary": {
            "grade_distribution_total_variation": grade_shift,
            "aux_minus_strict_numeric_means": numeric_mean_shifts,
            "interpretation": (
                "diagnostic only; do not rebalance or select a new model from "
                "official validation/test. Use train-only development CV for any "
                "successor reweighting/resampling experiment."
            ),
        },
        "leakage_guards": {
            "official_validation_read_for_statistics": False,
            "official_test_read_for_statistics": False,
            "strict_train_auxiliary_overlap": False,
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
            "Audit distribution shift between official weight train fruit and "
            "Dryad auxiliary geometry-weight candidates"
        )
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
        "--output",
        type=Path,
        default=Path(
            "artifacts/weight/geometry-auxiliary-audit-v1/"
            "geometry_auxiliary_shift_audit.json"
        ),
    )
    args = parser.parse_args(argv)

    try:
        report = audit_geometry_auxiliary_shift(
            args.official_split,
            args.auxiliary,
            args.output,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "WEIGHT_GEOMETRY_AUXILIARY_SHIFT_AUDIT_BLOCKED",
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
