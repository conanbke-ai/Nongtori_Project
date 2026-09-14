from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from ml.observability import RunLogger
from ml.ripeness_baseline.screen_lr_v002 import train_validation_only
from ml.ripeness_baseline.screen_scheduler_v004 import (
    BASE_LR,
    ETA_MIN,
    train_cosine_validation_only,
)
from ml.ripeness_baseline.train_v001 import (
    EXPECTED_ASSIGNMENT_SHA256,
    EXPECTED_PHYSICAL_IMAGES,
    EXPECTED_SAMPLES,
    EXPECTED_SPLIT_COUNTS,
    build_crop_cache,
)

SEEDS = [20260911, 20260912, 20260913]


def summarize(rows: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    keys = ["macro_f1", "accuracy", "ordinal_mae", "weighted_kappa", "m1_f1"]
    out: dict[str, dict[str, float]] = {}
    for key in keys:
        values = [float(row[key]) for row in rows]
        out[key] = {
            "mean": statistics.mean(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0.0,
        }
    return out


def compact(result: dict[str, Any]) -> dict[str, float]:
    m = result["best_valid_metrics"]
    return {
        "macro_f1": float(m["macro_f1"]),
        "accuracy": float(m["accuracy"]),
        "ordinal_mae": float(m["ordinal_mae"]),
        "weighted_kappa": float(m["weighted_kappa"]),
        "m1_f1": float(m["per_class"]["1"]["f1"]),
        "best_epoch": float(result["best_epoch"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("artifacts/ripeness-v004-cosine-confirmation-local-gpu"),
    )
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--eta-min", type=float, default=ETA_MIN)
    args = parser.parse_args()

    logger = RunLogger(args.workdir, "ripeness_v004_cosine_confirmation")
    try:
        logger.emit(
            "INFO",
            "RUN_STARTED",
            "RIPENESS-V004 paired 3-seed cosine confirmation started",
            phase="INIT",
            experiment_id="RIPENESS-V004-COSINE-CONFIRMATION",
            snapshot_id="KGCV-RIPENESS-V001",
            seeds=SEEDS,
            test_evaluated=False,
        )

        cache = build_crop_cache(args.workdir / "crops", logger)
        if cache["errors"]:
            raise RuntimeError(f"cache errors={len(cache['errors'])}")
        if cache["physical_images"] != EXPECTED_PHYSICAL_IMAGES or cache["samples"] != EXPECTED_SAMPLES:
            raise RuntimeError("snapshot count contract failed")
        if cache["split_counts"] != EXPECTED_SPLIT_COUNTS:
            raise RuntimeError(f"split contract failed: {cache['split_counts']}")
        if cache["assignment_sha256"] != EXPECTED_ASSIGNMENT_SHA256:
            raise RuntimeError("assignment checksum mismatch")

        pairs: list[dict[str, Any]] = []
        baseline_rows: list[dict[str, float]] = []
        cosine_rows: list[dict[str, float]] = []

        for seed in SEEDS:
            logger.emit(
                "INFO",
                "PAIR_STARTED",
                "paired seed comparison started",
                phase="CONFIRMATION",
                seed=seed,
            )
            baseline = train_validation_only(
                cache,
                args.workdir / f"seed-{seed}",
                logger,
                BASE_LR,
                args.epochs,
                seed,
            )
            cosine = train_cosine_validation_only(
                cache,
                args.workdir / f"seed-{seed}",
                logger,
                learning_rate=BASE_LR,
                max_epochs=args.epochs,
                eta_min=args.eta_min,
                seed=seed,
            )
            b = compact(baseline)
            c = compact(cosine)
            baseline_rows.append(b)
            cosine_rows.append(c)
            pairs.append(
                {
                    "seed": seed,
                    "baseline": b,
                    "cosine": c,
                    "delta": {
                        "macro_f1": c["macro_f1"] - b["macro_f1"],
                        "accuracy": c["accuracy"] - b["accuracy"],
                        "ordinal_mae": c["ordinal_mae"] - b["ordinal_mae"],
                        "weighted_kappa": c["weighted_kappa"] - b["weighted_kappa"],
                        "m1_f1": c["m1_f1"] - b["m1_f1"],
                    },
                }
            )

        baseline_summary = summarize(baseline_rows)
        cosine_summary = summarize(cosine_rows)
        mean_delta = {
            key: cosine_summary[key]["mean"] - baseline_summary[key]["mean"]
            for key in baseline_summary
        }

        result = {
            "status": "CONFIRMATION_COMPLETE",
            "test_evaluated": False,
            "seeds": SEEDS,
            "pairs": pairs,
            "baseline_summary": baseline_summary,
            "cosine_summary": cosine_summary,
            "mean_delta": mean_delta,
        }
        (args.workdir / "confirmation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.finish_summary(
            status="SUCCESS",
            summary_path=args.workdir / "summaries" / "run_summary.json",
            final_metrics={
                "baseline": baseline_summary,
                "cosine": cosine_summary,
                "mean_delta": mean_delta,
            },
        )
    except Exception as exc:
        logger.exception("RUN_FAILED", "cosine confirmation failed", exc, phase="FAILED")
        logger.finish_summary(
            status="FAILED",
            summary_path=args.workdir / "summaries" / "run_summary.json",
        )
        raise


if __name__ == "__main__":
    main()
