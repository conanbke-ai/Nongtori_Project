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
from ml.ripeness_baseline.cache_v001 import get_or_build_snapshot_cache
from ml.ripeness_baseline.screen_lr_v002 import _num_workers, train_validation_only
from ml.ripeness_baseline.train_v001 import CLASS_TO_INDEX, CLASS_VALUES, SEED, metrics, seed_all

BASE_LR = 5e-5
MAX_EPOCHS = 15


def train_efficientnet_b0(
    cache: dict[str, Any],
    out: Path,
    logger: RunLogger,
    *,
    seed: int = SEED,
    max_epochs: int = MAX_EPOCHS,
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

        def __len__(self):
            return len(self.records)

        def __getitem__(self, index: int):
            record = self.records[index]
            image = Image.open(record["path"]).convert("RGB")
            return self.transform(image), CLASS_TO_INDEX[record["label"]]

    records = cache["records"]
    train_records = [r for r in records if r["split"] == "train"]
    valid_records = [r for r in records if r["split"] == "valid"]
    counts = Counter(r["label"] for r in train_records)
    weights = torch.tensor(
        [len(train_records) / (len(CLASS_VALUES) * counts[c]) for c in CLASS_VALUES],
        dtype=torch.float32,
    )
    workers = _num_workers()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def loader(rs, train_mode):
        generator = torch.Generator().manual_seed(seed)
        return DataLoader(
            DS(rs, train_mode),
            batch_size=32,
            shuffle=train_mode,
            generator=generator if train_mode else None,
            num_workers=workers,
            pin_memory=torch.cuda.is_available(),
        )

    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASS_VALUES))
    model.to(device)
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    optimizer = torch.optim.AdamW(model.parameters(), lr=BASE_LR, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss(weight=weights.to(device))

    exp = f"EFFICIENTNET-B0-LR-{BASE_LR:.0e}-seed-{seed}"
    checkpoint = out / exp / "checkpoints" / "best.pt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    best_f1 = -1.0
    best_epoch = 0
    best_metrics = None
    best_valid_loss = 0.0
    patience = 0
    history: list[dict[str, Any]] = []

    def evaluate():
        model.eval()
        y_true, y_pred = [], []
        loss_sum, count = 0.0, 0
        with torch.no_grad():
            for images, labels in loader(valid_records, False):
                images = images.to(device, non_blocking=True)
                labels = labels.to(device, non_blocking=True)
                logits = model(images)
                loss = criterion(logits, labels)
                loss_sum += loss.item() * len(labels)
                count += len(labels)
                preds = logits.argmax(1).cpu().tolist()
                y_true.extend(CLASS_VALUES[i] for i in labels.cpu().tolist())
                y_pred.extend(CLASS_VALUES[i] for i in preds)
        return loss_sum / count, metrics(y_true, y_pred)

    logger.emit(
        "INFO",
        "SCREENING_STARTED",
        "EfficientNet-B0 architecture screening started",
        phase="SCREENING",
        experiment=exp,
        change_category="ARCHITECTURE",
        architecture="efficientnet_b0",
        pretrained="IMAGENET1K_V1",
        total_params=total_params,
        trainable_params=trainable_params,
        seed=seed,
        test_evaluated=False,
    )

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    for epoch in range(1, max_epochs + 1):
        started = time.monotonic()
        model.train()
        loss_sum, count = 0.0, 0
        for images, labels in loader(train_records, True):
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, labels)
            if not torch.isfinite(loss):
                raise RuntimeError(f"non-finite loss epoch={epoch}")
            loss.backward()
            optimizer.step()
            loss_sum += loss.item() * len(labels)
            count += len(labels)

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
                "EfficientNet-B0 validation checkpoint improved",
                phase="SCREENING",
                epoch=epoch,
                metric_name="valid_macro_f1",
                metric_value=best_f1,
                checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            )
        else:
            patience += 1

        row = {
            "epoch": epoch,
            "learning_rate": BASE_LR,
            "train_loss": loss_sum / count,
            "valid_loss": valid_loss,
            "best_epoch": best_epoch,
            "early_stopping_counter": patience,
            "epoch_elapsed_sec": round(time.monotonic() - started, 3),
            **valid_metrics,
        }
        history.append(row)
        logger.emit("INFO", "EPOCH_COMPLETED", f"{exp} epoch {epoch} completed", phase="SCREENING", **row)
        if patience >= 5:
            break

    if best_metrics is None:
        raise RuntimeError("no EfficientNet-B0 checkpoint created")

    peak_vram_mb = None
    if torch.cuda.is_available():
        peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)

    result = {
        "experiment": exp,
        "architecture": "efficientnet_b0",
        "seed": seed,
        "test_evaluated": False,
        "controlled_change": "architecture_only_under_current_recipe",
        "total_params": total_params,
        "trainable_params": trainable_params,
        "peak_vram_mb": peak_vram_mb,
        "best_epoch": best_epoch,
        "best_valid_loss": best_valid_loss,
        "best_valid_metrics": best_metrics,
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "history": history,
    }
    (out / exp / "validation_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path, default=Path("artifacts/ripeness-v007-efficientnet-b0-local-gpu"))
    parser.add_argument("--epochs", type=int, default=MAX_EPOCHS)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    logger = RunLogger(args.workdir, "ripeness_v007_efficientnet_b0")
    try:
        logger.emit(
            "INFO",
            "RUN_STARTED",
            "RIPENESS-V007 EfficientNet-B0 screening started",
            phase="INIT",
            experiment_id="RIPENESS-V007-EFFICIENTNET-B0",
            snapshot_id="KGCV-RIPENESS-V001",
            seed=args.seed,
            test_evaluated=False,
        )
        cache = get_or_build_snapshot_cache(logger)
        baseline = train_validation_only(cache, args.workdir, logger, BASE_LR, args.epochs, args.seed)
        candidate = train_efficientnet_b0(cache, args.workdir, logger, seed=args.seed, max_epochs=args.epochs)
        comparison = {
            "status": "SCREENING_COMPLETE",
            "test_evaluated": False,
            "change_category": "ARCHITECTURE",
            "controlled_change": "resnet18_vs_efficientnet_b0_under_same_training_recipe",
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
                "resnet18": baseline["best_valid_metrics"],
                "efficientnet_b0": candidate["best_valid_metrics"],
            },
        )
    except Exception as exc:
        logger.exception("RUN_FAILED", "V007 backbone screening failed", exc, phase="FAILED")
        logger.finish_summary(status="FAILED", summary_path=args.workdir / "summaries" / "run_summary.json")
        raise


if __name__ == "__main__":
    main()
