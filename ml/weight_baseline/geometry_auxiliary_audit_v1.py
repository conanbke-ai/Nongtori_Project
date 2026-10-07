from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from ml.data_pipeline.dryad_weight_audit import primary_weight_records_from_datasheet


def _is_positive_finite(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _load_strict_split(split_csv: Path) -> dict[str, str]:
    split_csv = Path(split_csv)
    if not split_csv.is_file():
        raise FileNotFoundError(f"strict weight split manifest missing: {split_csv}")
    with split_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("strict weight split manifest is empty")
    result: dict[str, str] = {}
    for row in rows:
        fruit_id = str(row.get("fruit_id") or "").strip()
        split = str(row.get("split") or "").strip()
        if not fruit_id:
            raise ValueError("strict split row missing fruit_id")
        if split not in {"train", "validation", "test"}:
            raise ValueError(f"unexpected strict split for {fruit_id}: {split!r}")
        if fruit_id in result:
            raise ValueError(f"duplicate fruit_id in strict split: {fruit_id}")
        result[fruit_id] = split
    return result


def audit_geometry_auxiliary_candidates(
    datasheet: Path,
    split_csv: Path,
    output_dir: Path,
    *,
    weight_loader: Callable[[Path], dict[str, dict[str, Any]]] = primary_weight_records_from_datasheet,
) -> dict[str, Any]:
    records = weight_loader(Path(datasheet))
    if not records:
        raise ValueError("Dryad weight loader returned no valid primary-weight records")

    strict_split = _load_strict_split(split_csv)
    missing_strict_weights = sorted(set(strict_split) - set(records))
    if missing_strict_weights:
        raise ValueError(
            "strict RGB-weight cohort contains fruit IDs missing from current "
            f"Dryad primary-weight records: {missing_strict_weights[:10]}"
        )

    geometry_valid = {
        fruit_id: record
        for fruit_id, record in records.items()
        if _is_positive_finite(record.get("width_mm"))
        and _is_positive_finite(record.get("height_mm"))
    }
    geometry_invalid_ids = sorted(set(records) - set(geometry_valid))
    strict_ids = set(strict_split)
    strict_geometry_ids = strict_ids & set(geometry_valid)
    auxiliary_ids = sorted(set(geometry_valid) - strict_ids)

    official_counts = Counter(strict_split.values())
    auxiliary_grade_counts: Counter[str] = Counter()
    auxiliary_photo_counts: Counter[str] = Counter()
    auxiliary_variety_counts: Counter[str] = Counter()
    for fruit_id in auxiliary_ids:
        record = geometry_valid[fruit_id]
        weight = float(record["weight_with_calyx_g"])
        if weight >= 22:
            grade = "SP_WEIGHT"
        elif weight >= 16:
            grade = "HI_WEIGHT"
        elif weight >= 12:
            grade = "MD_WEIGHT"
        else:
            grade = "JM_WEIGHT_CANDIDATE"
        auxiliary_grade_counts[grade] += 1
        auxiliary_photo_counts[str(record.get("photo") or "<EMPTY>")] += 1
        auxiliary_variety_counts[str(record.get("variety") or "<EMPTY>")] += 1

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_csv = output_dir / "geometry_auxiliary_train_candidates.csv"
    with candidate_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fruit_id",
                "weight_with_calyx_g",
                "width_mm",
                "height_mm",
                "variety",
                "shape",
                "photo",
                "source_sheet",
                "role",
            ],
        )
        writer.writeheader()
        for fruit_id in auxiliary_ids:
            record = geometry_valid[fruit_id]
            writer.writerow(
                {
                    "fruit_id": fruit_id,
                    "weight_with_calyx_g": record.get("weight_with_calyx_g"),
                    "width_mm": record.get("width_mm"),
                    "height_mm": record.get("height_mm"),
                    "variety": record.get("variety"),
                    "shape": record.get("shape"),
                    "photo": record.get("photo"),
                    "source_sheet": record.get("source_sheet"),
                    "role": "AUXILIARY_GEOMETRY_TRAIN_ONLY_CANDIDATE",
                }
            )

    report = {
        "status": "WEIGHT_GEOMETRY_AUXILIARY_AUDIT_COMPLETE",
        "contract": "nongtori-weight-geometry-auxiliary-audit.v1",
        "source": "DATA-QUAL-002",
        "primary_target": "weight_with_calyx_g",
        "primary_weight_valid_count": len(records),
        "geometry_valid_count": len(geometry_valid),
        "geometry_invalid_or_missing_count": len(geometry_invalid_ids),
        "strict_rgb_weight_count": len(strict_ids),
        "strict_rgb_weight_geometry_valid_count": len(strict_geometry_ids),
        "official_split_counts": {
            split: int(official_counts.get(split, 0))
            for split in ("train", "validation", "test")
        },
        "auxiliary_geometry_train_candidate_count": len(auxiliary_ids),
        "auxiliary_policy": (
            "candidate pool may augment Geometry V2 training only; it must not "
            "alter official validation/test membership and must not be treated "
            "as RGB training data when no approved RGB asset exists"
        ),
        "auxiliary_grade_counts": dict(sorted(auxiliary_grade_counts.items())),
        "auxiliary_photo_counts": dict(sorted(auxiliary_photo_counts.items())),
        "auxiliary_variety_counts": dict(
            sorted(auxiliary_variety_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "leakage_guards": {
            "official_validation_membership_unchanged": True,
            "official_test_membership_unchanged": True,
            "auxiliary_ids_overlap_strict_cohort": False,
            "rgb_availability_inferred": False,
        },
        "candidate_csv": str(candidate_csv),
        "geometry_invalid_or_missing_sample": geometry_invalid_ids[:50],
    }

    (output_dir / "geometry_auxiliary_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Dryad primary-weight fruit that can extend Geometry V2 "
            "training without changing the frozen RGB validation/test cohort"
        )
    )
    parser.add_argument(
        "--datasheet",
        type=Path,
        default=Path("data/raw/dryad/DATA-QUAL-002/datasheet.xlsx"),
    )
    parser.add_argument(
        "--split-csv",
        type=Path,
        default=Path("data/snapshots/WEIGHT-DRYAD-V001/fruit-splits.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/geometry-auxiliary-audit-v1"),
    )
    args = parser.parse_args(argv)

    try:
        report = audit_geometry_auxiliary_candidates(
            args.datasheet,
            args.split_csv,
            args.output_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "WEIGHT_GEOMETRY_AUXILIARY_AUDIT_BLOCKED", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
