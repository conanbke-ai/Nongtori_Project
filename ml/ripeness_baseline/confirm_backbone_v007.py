from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from ml.observability import RunLogger
from ml.ripeness_baseline.cache_v001 import get_or_build_snapshot_cache
from ml.ripeness_baseline.screen_backbone_v007 import BASE_LR, train_efficientnet_b0
from ml.ripeness_baseline.screen_lr_v002 import train_validation_only

SEEDS = [20260911, 20260912, 20260913]


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


def summarize(rows: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    keys = ["macro_f1", "accuracy", "ordinal_mae", "weighted_kappa", "m1_f1", "best_epoch"]
    return {
        key: {
            "mean": statistics.mean(float(r[key]) for r in rows),
            "std": statistics.stdev(float(r[key]) for r in rows) if len(rows) > 1 else 0.0,
        }
        for key in keys
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("artifacts/ripeness-v007-efficientnet-b0-confirmation-local-gpu"),
    )
    parser.add_argument("--epochs", type=int, default=15)
    args = parser.parse_args()

    logger = RunLogger(args.workdir, "ripeness_v007_efficientnet_b0_confirmation")
    try:
        logger.emit(
            "INFO",
            "RUN_STARTED",
            "RIPENESS-V007 paired multi-seed architecture confirmation started",
            phase="INIT",
            experiment_id="RIPENESS-V007-EFFICIENTNET-B0-CONFIRMATION",
            snapshot_id="KGCV-RIPENESS-V001",
            seeds=SEEDS,
            test_evaluated=False,
        )
        cache = get_or_build_snapshot_cache(logger)

        pairs: list[dict[str, Any]] = []
        baseline_rows: list[dict[str, float]] = []
        candidate_rows: list[dict[str, float]] = []

        for seed in SEEDS:
            logger.emit(
                "INFO", "PAIR_STARTED", "paired architecture seed started",
                phase="CONFIRMATION", seed=seed,
            )
            seed_dir = args.workdir / f"seed-{seed}"
            baseline = train_validation_only(cache, seed_dir, logger, BASE_LR, args.epochs, seed)
            candidate = train_efficientnet_b0(cache, seed_dir, logger, seed=seed, max_epochs=args.epochs)
            b = compact(baseline)
            c = compact(candidate)
            baseline_rows.append(b)
            candidate_rows.append(c)
            pairs.append({
                "seed": seed,
                "resnet18": b,
                "efficientnet_b0": c,
                "delta": {
                    "macro_f1": c["macro_f1"] - b["macro_f1"],
                    "accuracy": c["accuracy"] - b["accuracy"],
                    "ordinal_mae": c["ordinal_mae"] - b["ordinal_mae"],
                    "weighted_kappa": c["weighted_kappa"] - b["weighted_kappa"],
                    "m1_f1": c["m1_f1"] - b["m1_f1"],
                },
            })

        baseline_summary = summarize(baseline_rows)
        candidate_summary = summarize(candidate_rows)
        mean_delta = {
            key: candidate_summary[key]["mean"] - baseline_summary[key]["mean"]
            for key in ["macro_f1", "accuracy", "ordinal_mae", "weighted_kappa", "m1_f1"]
        }
        wins = {
            "macro_f1": sum(p["delta"]["macro_f1"] > 0 for p in pairs),
            "accuracy": sum(p["delta"]["accuracy"] > 0 for p in pairs),
            "ordinal_mae": sum(p["delta"]["ordinal_mae"] < 0 for p in pairs),
            "weighted_kappa": sum(p["delta"]["weighted_kappa"] > 0 for p in pairs),
            "m1_f1": sum(p["delta"]["m1_f1"] > 0 for p in pairs),
        }

        result = {
            "status": "CONFIRMATION_COMPLETE",
            "test_evaluated": False,
            "controlled_change": "resnet18_vs_efficientnet_b0_architecture_only",
            "seeds": SEEDS,
            "pairs": pairs,
            "resnet18_summary": baseline_summary,
            "efficientnet_b0_summary": candidate_summary,
            "mean_delta": mean_delta,
            "candidate_seed_wins": wins,
        }
        (args.workdir / "confirmation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.finish_summary(
            status="SUCCESS",
            summary_path=args.workdir / "summaries" / "run_summary.json",
            final_metrics={
                "resnet18": baseline_summary,
                "efficientnet_b0": candidate_summary,
                "mean_delta": mean_delta,
                "candidate_seed_wins": wins,
            },
        )
    except Exception as exc:
        logger.exception("RUN_FAILED", "V007 architecture confirmation failed", exc, phase="FAILED")
        logger.finish_summary(
            status="FAILED",
            summary_path=args.workdir / "summaries" / "run_summary.json",
        )
        raise


if __name__ == "__main__":
    main()
