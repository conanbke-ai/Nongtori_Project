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
from ml.ripeness_baseline.screen_lr_v002 import _num_workers, train_validation_only
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

BASE_LR = 5e-5
MAX_EPOCHS = 15
ETA_MIN = 5e-6


def train_cosine_validation_only(
    cache: dict[str, Any],
    out: Path,
    logger: RunLogger,
    *,
    learning_rate: float = BASE_LR,
    max_epochs: int = MAX_EPOCHS,
    eta_min: float = ETA_MIN,
    seed: int = SEED,
) -> dict[str, Any]:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset
    from torchvision import models, transforms

    seed_all(seed)

    class DS(Dataset):
        def __init__(self, records: list[dict[str, Any]], train_mode: bool):
            self.records = records
            self.transform = transforms.Compose([
                transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),
                transforms.RandomHorizontalFlip(),
                transforms.ColorJitter(0.15, 0.15, 0.15, 0.05),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]) if train_mode else transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ])

        def __len__(self) -> int:
            return len(self.records)

        def __getitem__(self, index: int):
            record = self.records[index]
            image = Image.open(record["path"]).convert("RGB")
            return self.transform(image), CLASS_TO_INDEX[record["label"]]

    records = cache["records"]
    train_records = [r for r in records if r["split"] == "train"]
    valid_records = [r for r in records if r["split"] == "valid"]
    train_counts = Counter(r["label"] for r in train_records)
    weights = torch.tensor(
        [len(train_records) / (len(CLASS_VALUES) * train_counts[c]) for c in CLASS_VALUES],
        dtype=torch.float32,
    )
    workers = _num_workers()

    def loader(records_: list[dict[str, Any]], train_mode: bool) -> DataLoader:
        generator = torch.Generator().manual_seed(seed)
        return DataLoader(
            DS(records_, train_mode),
            batch_size=32,
            shuffle=train_mode,
            generator=generator if train_mode else None,
            num_workers=workers,
            pin_memory=torch.cuda.is_available(),
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    exp_name = f"COSINE-LR-{learning_rate:.0e}-seed-{seed}"
    exp_out = out / exp_name
    checkpoint = exp_out / "checkpoints" / "best.pt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, len(CLASS_VALUES))
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=max_epochs,
        eta_min=eta_min,
    )
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
                images = images.to(device, non_blocking=True)
                labels = labels.to(device, non_blocking=True)
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
        "cosine scheduler validation screening started",
        phase="SCREENING",
        experiment=exp_name,
        scheduler="CosineAnnealingLR",
        base_lr=learning_rate,
        eta_min=eta_min,
        t_max=max_epochs,
        seed=seed,
        train_samples=len(train_records),
        valid_samples=len(valid_records),
        test_evaluated=False,
        controlled_change="scheduler_only",
    )

    for epoch in range(1, max_epochs + 1):
        started = time.monotonic()
        current_lr = float(optimizer.param_groups[0]["lr"])
        model.train()
        running_loss = 0.0
        seen = 0
        for images, labels in loader(train_records, True):
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, labels)
            if not torch.isfinite(loss):
                raise RuntimeError(f"non-finite loss seed={seed} epoch={epoch}")
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
                "cosine validation checkpoint improved",
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

        scheduler.step()
        next_lr = float(optimizer.param_groups[0]["lr"])
        row = {
            "epoch": epoch,
            "learning_rate": current_lr,
            "next_learning_rate": next_lr,
            "seed": seed,
            "scheduler": "CosineAnnealingLR",
            "train_loss": running_loss / seen,
            "valid_loss": valid_loss,
            "best_epoch": best_epoch,
            "early_stopping_counter": patience,
            "epoch_elapsed_sec": round(time.monotonic() - started, 3),
            **valid_metrics,
        }
        history.append(row)
        logger.emit(
            "INFO",
            "EPOCH_COMPLETED",
            f"{exp_name} epoch {epoch} completed",
            phase="SCREENING",
            **row,
        )
        if patience >= 5:
            break

    if best_metrics is None or not checkpoint.exists():
        raise RuntimeError("no valid cosine checkpoint created")

    result = {
        "experiment": exp_name,
        "scheduler": "CosineAnnealingLR",
        "base_lr": learning_rate,
        "eta_min": eta_min,
        "seed": seed,
        "test_evaluated": False,
        "controlled_change": "scheduler_only",
        "best_epoch": best_epoch,
        "best_valid_loss": best_valid_loss,
        "best_valid_metrics": best_metrics,
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "history": history,
    }
    (exp_out / "validation_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path, default=Path("artifacts/ripeness-v004-cosine-local-gpu"))
    parser.add_argument("--epochs", type=int, default=MAX_EPOCHS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--eta-min", type=float, default=ETA_MIN)
    args = parser.parse_args()

    logger = RunLogger(args.workdir, "ripeness_v004_cosine_screening")
    try:
        logger.emit(
            "INFO",
            "RUN_STARTED",
            "RIPENESS-V004 cosine scheduler screening started",
            phase="INIT",
            experiment_id="RIPENESS-V004-COSINE-SCREENING",
            snapshot_id="KGCV-RIPENESS-V001",
            seed=args.seed,
            test_evaluated=False,
        )
        cache = build_crop_cache(args.workdir / "crops", logger)
        if cache["errors"]:
            raise RuntimeError(f"cache errors={len(cache['errors'])}")
        if cache["physical_images"] != EXPECTED_PHYSICAL_IMAGES or cache["samples"] != EXPECTED_SAMPLES:
            raise RuntimeError("snapshot count contract failed")
        if cache["split_counts"] != EXPECTED_SPLIT_COUNTS or cache["assignment_sha256"] != EXPECTED_ASSIGNMENT_SHA256:
            raise RuntimeError("frozen split contract failed")

        baseline = train_validation_only(cache, args.workdir, logger, BASE_LR, args.epochs, args.seed)
        candidate = train_cosine_validation_only(
            cache,
            args.workdir,
            logger,
            learning_rate=BASE_LR,
            max_epochs=args.epochs,
            eta_min=args.eta_min,
            seed=args.seed,
        )
        comparison = {
            "status": "SCREENING_COMPLETE",
            "test_evaluated": False,
            "change_category": "OPTIMIZATION",
            "controlled_change": "scheduler_only",
            "baseline": baseline,
            "candidate": candidate,
        }
        (args.workdir / "comparison.json").write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.finish_summary(
            status="SUCCESS",
            summary_path=args.workdir / "summaries" / "run_summary.json",
            final_metrics={
                "full_5e-5_no_scheduler": baseline["best_valid_metrics"],
                "full_5e-5_cosine": candidate["best_valid_metrics"],
            },
        )
    except Exception as exc:
        logger.exception("RUN_FAILED", "cosine scheduler screening failed", exc, phase="FAILED")
        logger.finish_summary(status="FAILED", summary_path=args.workdir / "summaries" / "run_summary.json")
        raise


if __name__ == "__main__":
    main()
