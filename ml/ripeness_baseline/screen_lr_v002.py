from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from ml.observability import RunLogger
from ml.ripeness_baseline.train_v001 import (
    CLASS_TO_INDEX,
    CLASS_VALUES,
    EXPECTED_ASSIGNMENT_SHA256,
    EXPECTED_PHYSICAL_IMAGES,
    EXPECTED_SAMPLES,
    EXPECTED_SPLIT_COUNTS,
    SEED,
    build_crop_cache,
    metrics,
    seed_all,
)

BASELINE_VALID = {
    "learning_rate": 3e-4,
    "best_epoch": 1,
    "macro_f1": 0.9536944102033728,
    "accuracy": 0.9567901234567902,
    "ordinal_mae": 0.06790123456790123,
    "weighted_kappa": 0.9603116512313006,
    "m1_f1": 0.9177489177489178,
    "confusion_matrix": [[237, 12, 1], [4, 106, 1], [1, 2, 122]],
}
CANDIDATE_LRS = [1e-4, 5e-5]


def train_validation_only(
    cache: dict[str, Any],
    out: Path,
    logger: RunLogger,
    learning_rate: float,
    max_epochs: int,
) -> dict[str, Any]:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset
    from torchvision import models, transforms

    seed_all(SEED)

    class DS(Dataset):
        def __init__(self, records: list[dict[str, Any]], train_mode: bool):
            self.records = records
            self.transform = (
                transforms.Compose(
                    [
                        transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),
                        transforms.RandomHorizontalFlip(),
                        transforms.ColorJitter(0.15, 0.15, 0.15, 0.05),
                        transforms.ToTensor(),
                        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
                    ]
                )
                if train_mode
                else transforms.Compose(
                    [
                        transforms.Resize(256),
                        transforms.CenterCrop(224),
                        transforms.ToTensor(),
                        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
                    ]
                )
            )

        def __len__(self) -> int:
            return len(self.records)

        def __getitem__(self, index: int):
            record = self.records[index]
            return self.transform(Image.open(record["path"]).convert("RGB")), CLASS_TO_INDEX[record["label"]]

    records = cache["records"]
    train_records = [r for r in records if r["split"] == "train"]
    valid_records = [r for r in records if r["split"] == "valid"]
    train_counts = Counter(r["label"] for r in train_records)
    weights = torch.tensor(
        [len(train_records) / (len(CLASS_VALUES) * train_counts[c]) for c in CLASS_VALUES],
        dtype=torch.float32,
    )

    def loader(records_: list[dict[str, Any]], train_mode: bool) -> DataLoader:
        generator = torch.Generator().manual_seed(SEED)
        return DataLoader(
            DS(records_, train_mode),
            batch_size=32,
            shuffle=train_mode,
            generator=generator if train_mode else None,
            num_workers=2,
            pin_memory=False,
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    exp_name = f"LR-{learning_rate:.0e}"
    exp_out = out / exp_name
    checkpoint = exp_out / "checkpoints" / "best.pt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, len(CLASS_VALUES))
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss(weight=weights.to(device))

    best_f1 = -1.0
    best_epoch = 0
    best_metrics: dict[str, Any] | None = None
    best_valid_loss = 0.0
    patience = 0
    history: list[dict[str, Any]] = []

    def evaluate() -> tuple[float, dict[str, Any]]:
        model.eval()
        y_true: list[int] = []
        y_pred: list[int] = []
        total_loss = 0.0
        count = 0
        with torch.no_grad():
            for images, labels in loader(valid_records, False):
                images = images.to(device)
                labels = labels.to(device)
                logits = model(images)
                total_loss += criterion(logits, labels).item() * len(labels)
                count += len(labels)
                predicted = logits.argmax(1).cpu().tolist()
                y_true.extend(CLASS_VALUES[i] for i in labels.cpu().tolist())
                y_pred.extend(CLASS_VALUES[i] for i in predicted)
        return total_loss / count, metrics(y_true, y_pred)

    logger.emit(
        "INFO",
        "SCREENING_STARTED",
        "controlled validation-only LR screening started",
        phase="SCREENING",
        experiment=exp_name,
        learning_rate=learning_rate,
        seed=SEED,
        train_samples=len(train_records),
        valid_samples=len(valid_records),
        test_evaluated=False,
    )

    for epoch in range(1, max_epochs + 1):
        started = time.monotonic()
        model.train()
        train_loader = loader(train_records, True)
        running_loss = 0.0
        seen = 0
        for images, labels in train_loader:
            images = images.to(device)
            labels = labels.to(device)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, labels)
            if not torch.isfinite(loss):
                raise RuntimeError(f"non-finite loss at lr={learning_rate} epoch={epoch}")
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * len(labels)
            seen += len(labels)

        valid_loss, valid_metrics = evaluate()
        improved = valid_metrics["macro_f1"] > best_f1 + 1e-8
        if improved:
            best_f1 = valid_metrics["macro_f1"]
            best_epoch = epoch
            best_metrics = valid_metrics
            best_valid_loss = valid_loss
            patience = 0
            torch.save(model.state_dict(), checkpoint)
            logger.emit(
                "INFO",
                "CHECKPOINT_SAVED",
                "screening checkpoint improved",
                phase="SCREENING",
                experiment=exp_name,
                epoch=epoch,
                metric_name="valid_macro_f1",
                metric_value=best_f1,
                checkpoint_path=str(checkpoint),
                checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            )
        else:
            patience += 1

        row = {
            "epoch": epoch,
            "learning_rate": learning_rate,
            "train_loss": running_loss / seen,
            "valid_loss": valid_loss,
            "best_epoch": best_epoch,
            "early_stopping_counter": patience,
            "epoch_elapsed_sec": round(time.monotonic() - started, 3),
            **valid_metrics,
        }
        history.append(row)
        logger.emit("INFO", "EPOCH_COMPLETED", f"{exp_name} epoch {epoch} completed", phase="SCREENING", **row)
        if patience >= 5:
            break

    if best_metrics is None or not checkpoint.exists():
        raise RuntimeError(f"no valid checkpoint created for {exp_name}")

    result = {
        "experiment": exp_name,
        "learning_rate": learning_rate,
        "seed": SEED,
        "test_evaluated": False,
        "best_epoch": best_epoch,
        "best_valid_loss": best_valid_loss,
        "best_valid_metrics": best_metrics,
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "history": history,
    }
    (exp_out / "validation_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path, default=Path("artifacts/ripeness-v002-lr-screening"))
    parser.add_argument("--epochs", type=int, default=15)
    args = parser.parse_args()
    logger = RunLogger(args.workdir, "ripeness_v002_lr_screening")

    try:
        logger.emit(
            "INFO",
            "RUN_STARTED",
            "RIPENESS-V002 LR screening started",
            phase="INIT",
            experiment_id="RIPENESS-V002-LR-SCREENING",
            snapshot_id="KGCV-RIPENESS-V001",
            seed=SEED,
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

        results = [train_validation_only(cache, args.workdir, logger, lr, args.epochs) for lr in CANDIDATE_LRS]
        comparison = {
            "status": "SCREENING_COMPLETE",
            "test_evaluated": False,
            "baseline_validation": BASELINE_VALID,
            "candidates": results,
        }
        (args.workdir / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.finish_summary(
            status="SUCCESS",
            summary_path=args.workdir / "summaries" / "run_summary.json",
            input_count=cache["physical_images"],
            processed_count=cache["physical_images"],
            success_count=cache["samples"],
            failed_count=0,
            final_metrics={
                r["experiment"]: {
                    "best_epoch": r["best_epoch"],
                    "macro_f1": r["best_valid_metrics"]["macro_f1"],
                    "m1_f1": r["best_valid_metrics"]["per_class"]["1"]["f1"],
                    "ordinal_mae": r["best_valid_metrics"]["ordinal_mae"],
                    "weighted_kappa": r["best_valid_metrics"]["weighted_kappa"],
                }
                for r in results
            },
        )
    except Exception as exc:
        logger.exception("RUN_FAILED", "LR screening failed", exc, phase="FAILED")
        logger.finish_summary(status="FAILED", summary_path=args.workdir / "summaries" / "run_summary.json")
        raise


if __name__ == "__main__":
    main()
