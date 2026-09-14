from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from ml.observability import RunLogger
from ml.ripeness_baseline.screen_lr_v002 import train_validation_only
from ml.ripeness_baseline.train_v001 import (
    EXPECTED_ASSIGNMENT_SHA256,
    EXPECTED_PHYSICAL_IMAGES,
    EXPECTED_SAMPLES,
    EXPECTED_SPLIT_COUNTS,
    build_crop_cache,
)

LRS = [3e-4, 5e-5]
SEEDS = [20260911, 20260912, 20260913]


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for lr in LRS:
        selected = [r for r in results if r["learning_rate"] == lr]
        metrics = {
            "macro_f1": [r["best_valid_metrics"]["macro_f1"] for r in selected],
            "m1_f1": [r["best_valid_metrics"]["per_class"]["1"]["f1"] for r in selected],
            "ordinal_mae": [r["best_valid_metrics"]["ordinal_mae"] for r in selected],
            "weighted_kappa": [r["best_valid_metrics"]["weighted_kappa"] for r in selected],
            "best_epoch": [float(r["best_epoch"]) for r in selected],
        }
        summary[f"{lr:.0e}"] = {
            key: {
                "values": values,
                "mean": statistics.mean(values),
                "std": statistics.stdev(values) if len(values) > 1 else 0.0,
            }
            for key, values in metrics.items()
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path, default=Path("artifacts/ripeness-v002-lr-confirmation"))
    parser.add_argument("--epochs", type=int, default=12)
    args = parser.parse_args()
    logger = RunLogger(args.workdir, "ripeness_v002_lr_confirmation")
    logger.emit("INFO", "RUN_STARTED", "paired multi-seed LR confirmation started", phase="INIT", experiment_id="RIPENESS-V002-LR-CONFIRMATION", snapshot_id="KGCV-RIPENESS-V001", seeds=SEEDS, learning_rates=LRS, test_evaluated=False)

    try:
        cache = build_crop_cache(args.workdir / "crops", logger)
        if cache["errors"] or cache["physical_images"] != EXPECTED_PHYSICAL_IMAGES or cache["samples"] != EXPECTED_SAMPLES:
            raise RuntimeError("snapshot count/error contract failed")
        if cache["split_counts"] != EXPECTED_SPLIT_COUNTS or cache["assignment_sha256"] != EXPECTED_ASSIGNMENT_SHA256:
            raise RuntimeError("frozen split contract failed")

        # train_validation_only seeds itself internally in the screening implementation,
        # so confirmation uses a controlled wrapper patch: each seed is passed through
        # the module-level seed value via an isolated subprocess in the workflow.
        # This script aggregates per-seed result files produced by those subprocesses.
        result_files = sorted(args.workdir.glob("seed-*/pair-result.json"))
        if not result_files:
            raise RuntimeError("no paired seed result files found; use workflow seed matrix")
        results: list[dict[str, Any]] = []
        for path in result_files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            results.extend(payload["results"])
        report = {"status":"CONFIRMATION_COMPLETE","test_evaluated":False,"seeds":SEEDS,"summary":summarize(results),"results":results}
        (args.workdir / "confirmation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.finish_summary(status="SUCCESS", summary_path=args.workdir/"summaries"/"run_summary.json", final_metrics=report["summary"])
    except Exception as exc:
        logger.exception("RUN_FAILED", "LR confirmation aggregation failed", exc, phase="FAILED")
        logger.finish_summary(status="FAILED", summary_path=args.workdir/"summaries"/"run_summary.json")
        raise


if __name__ == "__main__":
    main()
