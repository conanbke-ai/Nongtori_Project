from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_FOLDS = 5
DEFAULT_SEED = "nongtori-weight-development-cv-v1"
ALLOWED_OFFICIAL_SPLITS = {"train", "validation", "test"}


def _load_official_split_rows(split_csv: Path) -> list[dict[str, str]]:
    split_csv = Path(split_csv)
    if not split_csv.is_file():
        raise FileNotFoundError(f"weight fruit split manifest missing: {split_csv}")

    with split_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("weight fruit split manifest is empty")

    required = {"fruit_id", "split"}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(
            f"weight fruit split manifest missing columns: {sorted(missing)}"
        )

    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for raw in rows:
        fruit_id = str(raw.get("fruit_id") or "").strip()
        split = str(raw.get("split") or "").strip()
        if not fruit_id:
            raise ValueError("weight fruit split row missing fruit_id")
        if fruit_id in seen:
            raise ValueError(f"duplicate fruit_id in official split: {fruit_id}")
        seen.add(fruit_id)
        if split not in ALLOWED_OFFICIAL_SPLITS:
            raise ValueError(
                f"unexpected official split for {fruit_id}: {split!r}"
            )
        normalized.append({"fruit_id": fruit_id, "split": split})
    return normalized


def _balanced_fold_assignments(
    fruit_ids: list[str],
    *,
    folds: int,
    seed: str,
) -> dict[str, int]:
    if folds < 2:
        raise ValueError("folds must be >= 2")
    if len(fruit_ids) < folds:
        raise ValueError(
            f"train fruit count {len(fruit_ids)} is smaller than folds={folds}"
        )

    ordered = sorted(
        fruit_ids,
        key=lambda fruit_id: (
            hashlib.sha256(f"{seed}|{fruit_id}".encode("utf-8")).hexdigest(),
            fruit_id,
        ),
    )
    return {
        fruit_id: index % folds
        for index, fruit_id in enumerate(ordered)
    }


def build_weight_train_cv_manifest(
    split_csv: Path,
    output_dir: Path,
    *,
    folds: int = DEFAULT_FOLDS,
    seed: str = DEFAULT_SEED,
) -> dict[str, Any]:
    rows = _load_official_split_rows(split_csv)
    official_counts = Counter(row["split"] for row in rows)
    train_ids = [
        row["fruit_id"]
        for row in rows
        if row["split"] == "train"
    ]
    assignments = _balanced_fold_assignments(
        train_ids,
        folds=folds,
        seed=seed,
    )

    fold_counts = Counter(assignments.values())
    expected_largest = (len(train_ids) + folds - 1) // folds
    expected_smallest = len(train_ids) // folds
    if max(fold_counts.values()) > expected_largest:
        raise ValueError("development fold assignment is unexpectedly imbalanced")
    if min(fold_counts.values()) < expected_smallest:
        raise ValueError("development fold assignment is unexpectedly imbalanced")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "train_folds.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["fruit_id", "official_split", "cv_fold"],
        )
        writer.writeheader()
        for fruit_id in sorted(assignments):
            writer.writerow(
                {
                    "fruit_id": fruit_id,
                    "official_split": "train",
                    "cv_fold": assignments[fruit_id],
                }
            )

    fold_protocols = []
    for holdout_fold in range(folds):
        development_validation = sorted(
            fruit_id
            for fruit_id, fold in assignments.items()
            if fold == holdout_fold
        )
        development_train = sorted(
            fruit_id
            for fruit_id, fold in assignments.items()
            if fold != holdout_fold
        )
        fold_protocols.append(
            {
                "fold": holdout_fold,
                "development_train_count": len(development_train),
                "development_validation_count": len(development_validation),
            }
        )

    report = {
        "status": "WEIGHT_DEVELOPMENT_CV_FROZEN",
        "contract": "nongtori-weight-development-cv.v1",
        "source_split_manifest": str(split_csv),
        "split_group": "FRUIT_ID",
        "official_split_counts": {
            split: int(official_counts.get(split, 0))
            for split in ("train", "validation", "test")
        },
        "development_pool": "official_train_only",
        "development_pool_count": len(train_ids),
        "folds": folds,
        "seed": seed,
        "fold_counts": {
            str(fold): int(fold_counts.get(fold, 0))
            for fold in range(folds)
        },
        "fold_protocols": fold_protocols,
        "official_validation_policy": (
            "kept outside inner CV; use only after method/hyperparameter "
            "development is frozen"
        ),
        "official_test_policy": (
            "historical locked holdout; never enters successor CV, "
            "hyperparameter selection, aggregation selection, or uncertainty "
            "policy selection"
        ),
        "leakage_guards": {
            "official_validation_in_cv": False,
            "official_test_in_cv": False,
            "same_fruit_cross_cv_fold": False,
        },
        "manifest": str(manifest_path),
    }
    report_path = output_dir / "development_cv.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze deterministic FRUIT_ID-level development CV folds from "
            "the official WEIGHT-DRYAD-V001 train split only"
        )
    )
    parser.add_argument(
        "--split-csv",
        type=Path,
        default=Path("data/snapshots/WEIGHT-DRYAD-V001/fruit-splits.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/development-cv-v1"),
    )
    parser.add_argument("--folds", type=int, default=DEFAULT_FOLDS)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    try:
        report = build_weight_train_cv_manifest(
            args.split_csv,
            args.output_dir,
            folds=int(args.folds),
            seed=str(args.seed),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "WEIGHT_DEVELOPMENT_CV_BLOCKED", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
