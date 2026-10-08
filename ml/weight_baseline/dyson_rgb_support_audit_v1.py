from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


def _to_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"non-finite {field}: {value!r}")
    return number


def _metrics(rows: list[dict[str, float]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0}
    errors = [row["predicted"] - row["actual"] for row in rows]
    abs_errors = [abs(e) for e in errors]
    sq = [e * e for e in errors]
    mean_actual = sum(row["actual"] for row in rows) / len(rows)
    ss_total = sum((row["actual"] - mean_actual) ** 2 for row in rows)
    ss_residual = sum(sq)
    return {
        "count": len(rows),
        "mae_g": sum(abs_errors) / len(abs_errors),
        "rmse_g": math.sqrt(sum(sq) / len(sq)),
        "bias_g": sum(errors) / len(errors),
        "r2": 1.0 - ss_residual / ss_total if ss_total > 1e-12 else 0.0,
        "max_abs_error_g": max(abs_errors),
    }


def run_support_audit(
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
        dryad = list(csv.DictReader(handle))

    dryad_train = [
        _to_float(row["weight_with_calyx_g"], "weight_with_calyx_g")
        for row in dryad
        if row.get("split") == "train"
    ]
    if not dryad_train:
        raise ValueError("Dryad train split is empty")

    train_min = min(dryad_train)
    train_max = max(dryad_train)

    with dyson_predictions_csv.open(encoding="utf-8", newline="") as handle:
        raw = list(csv.DictReader(handle))

    rows = [
        {
            "actual": _to_float(row["actual_weight_g"], "actual_weight_g"),
            "predicted": _to_float(row["predicted_weight_g"], "predicted_weight_g"),
        }
        for row in raw
    ]
    if not rows:
        raise ValueError("Dyson prediction file is empty")

    below = [row for row in rows if row["actual"] < train_min]
    inside = [row for row in rows if train_min <= row["actual"] <= train_max]
    above = [row for row in rows if row["actual"] > train_max]

    report = {
        "status": "DYSON_RGB_SUPPORT_AUDIT_COMPLETE",
        "dryad_train_support": {
            "count": len(dryad_train),
            "min_g": train_min,
            "max_g": train_max,
        },
        "dyson_support_overlap": {
            "count": len(rows),
            "below_train_min_count": len(below),
            "in_train_support_count": len(inside),
            "above_train_max_count": len(above),
            "below_train_min_rate": len(below) / len(rows),
            "in_train_support_rate": len(inside) / len(rows),
            "above_train_max_rate": len(above) / len(rows),
        },
        "error_by_support": {
            "below_train_min": _metrics(below),
            "in_train_support": _metrics(inside),
            "above_train_max": _metrics(above),
        },
        "interpretation_guard": (
            "This audit separates target-support mismatch from in-support error. "
            "It does not isolate image-domain shift causally and must not be used to retune RGB V001."
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "dyson_rgb_support_audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["artifact"] = str(output)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit Dryad-train weight support versus Dyson external RGB errors"
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
        report = run_support_audit(
            dryad_snapshot_dir=args.dryad_snapshot_dir,
            dyson_predictions_csv=args.dyson_predictions_csv,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"status":"DYSON_RGB_SUPPORT_AUDIT_BLOCKED","error":str(exc)}, ensure_ascii=False, indent=2))
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
