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
from ml.ripeness_baseline.screen_backbone_v007 import BASE_LR, MAX_EPOCHS, train_efficientnet_b0
from ml.ripeness_baseline.screen_lr_v002 import _num_workers
from ml.ripeness_baseline.train_v001 import CLASS_TO_INDEX, CLASS_VALUES, SEED, metrics, seed_all


def _ordinal_targets(class_indices, device):
    import torch
    # rank 0 -> [0,0], rank 1 -> [1,0], rank 2 -> [1,1]
    rank = class_indices.to(device)
    return torch.stack([(rank >= 1).float(), (rank >= 2).float()], dim=1)


class OrderedThresholdHead:
    @staticmethod
    def build(in_features: int):
        import torch
        from torch import nn
        import torch.nn.functional as F

        class Head(nn.Module):
            def __init__(self):
                super().__init__()
                self.score = nn.Linear(in_features, 1)
                self.cut1 = nn.Parameter(torch.tensor(0.0))
                self.raw_gap = nn.Parameter(torch.tensor(0.5))

            def forward(self, x):
                s = self.score(x).squeeze(1)
                c1 = self.cut1
                c2 = c1 + F.softplus(self.raw_gap)
                # logits for P(rank > 0), P(rank > 1)
                return torch.stack([s - c1, s - c2], dim=1)

        return Head()


def train_ordinal_efficientnet(
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
            r = self.records[index]
            image = Image.open(r["path"]).convert("RGB")
            return self.transform(image), CLASS_TO_INDEX[r["label"]]

    records = cache["records"]
    train_records = [r for r in records if r["split"] == "train"]
    valid_records = [r for r in records if r["split"] == "valid"]
    workers = _num_workers()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    counts = Counter(CLASS_TO_INDEX[r["label"]] for r in train_records)
    # Per-threshold positive weighting derived from frozen train split only.
    n = len(train_records)
    pos0 = counts[1] + counts[2]
    neg0 = counts[0]
    pos1 = counts[2]
    neg1 = counts[0] + counts[1]
    pos_weight = torch.tensor([
        neg0 / max(1, pos0),
        neg1 / max(1, pos1),
    ], dtype=torch.float32, device=device)

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
    in_features = model.classifier[1].in_features
    model.classifier[1] = OrderedThresholdHead.build(in_features)
    model.to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=BASE_LR, weight_decay=1e-4)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    exp = f"EFFICIENTNET-B0-ORDINAL-LR-{BASE_LR:.0e}-seed-{seed}"
    checkpoint = out / exp / "checkpoints" / "best.pt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    best_f1 = -1.0
    best_epoch = 0
    best_metrics = None
    best_valid_loss = 0.0
    patience = 0
    history: list[dict[str, Any]] = []

    def decode(logits):
        probs = torch.sigmoid(logits)
        return (probs >= 0.5).sum(dim=1)

    def evaluate():
        model.eval()
        y_true, y_pred = [], []
        loss_sum, count = 0.0, 0
        with torch.no_grad():
            for images, labels in loader(valid_records, False):
                images = images.to(device, non_blocking=True)
                labels = labels.to(device, non_blocking=True)
                logits = model(images)
                target = _ordinal_targets(labels, device)
                loss = criterion(logits, target)
                loss_sum += loss.item() * len(labels)
                count += len(labels)
                pred_idx = decode(logits).cpu().tolist()
                y_true.extend(CLASS_VALUES[i] for i in labels.cpu().tolist())
                y_pred.extend(CLASS_VALUES[i] for i in pred_idx)
        return loss_sum / count, metrics(y_true, y_pred)

    logger.emit(
        "INFO", "SCREENING_STARTED", "EfficientNet-B0 ordinal-head screening started",
        phase="SCREENING", experiment=exp, change_category="ORDINAL_HEAD",
        architecture="efficientnet_b0", head="ordered_cumulative_threshold",
        seed=seed, test_evaluated=False, threshold_pos_weight=pos_weight.detach().cpu().tolist(),
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
            target = _ordinal_targets(labels, device)
            loss = criterion(logits, target)
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
                "INFO", "CHECKPOINT_SAVED", "ordinal-head validation checkpoint improved",
                phase="SCREENING", epoch=epoch, metric_name="valid_macro_f1",
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
        raise RuntimeError("no ordinal-head checkpoint created")

    peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024) if torch.cuda.is_available() else None
    result = {
        "experiment": exp,
        "architecture": "efficientnet_b0",
        "head": "ordered_cumulative_threshold",
        "seed": seed,
        "test_evaluated": False,
        "controlled_change": "softmax_head_to_structural_ordinal_head",
        "total_params": sum(p.numel() for p in model.parameters()),
        "trainable_params": sum(p.numel() for p in model.parameters() if p.requires_grad),
        "peak_vram_mb": peak_vram_mb,
        "best_epoch": best_epoch,
        "best_valid_loss": best_valid_loss,
        "best_valid_metrics": best_metrics,
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "threshold_pos_weight": pos_weight.detach().cpu().tolist(),
        "history": history,
    }
    (out / exp / "validation_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path, default=Path("artifacts/ripeness-v009-ordinal-head-local-gpu"))
    parser.add_argument("--epochs", type=int, default=MAX_EPOCHS)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    logger = RunLogger(args.workdir, "ripeness_v009_ordinal_head")
    try:
        logger.emit(
            "INFO", "RUN_STARTED", "RIPENESS-V009 ordinal-head screening started",
            phase="INIT", experiment_id="RIPENESS-V009-ORDINAL-HEAD",
            snapshot_id="KGCV-RIPENESS-V001", seed=args.seed,
            test_evaluated=False, field_data_used=False,
        )
        cache = get_or_build_snapshot_cache(logger)
        baseline = train_efficientnet_b0(cache, args.workdir, logger, seed=args.seed, max_epochs=args.epochs)
        candidate = train_ordinal_efficientnet(cache, args.workdir, logger, seed=args.seed, max_epochs=args.epochs)
        comparison = {
            "status": "SCREENING_COMPLETE",
            "test_evaluated": False,
            "field_data_used": False,
            "controlled_change": "efficientnet_b0_softmax_vs_ordered_ordinal_head",
            "baseline": baseline,
            "candidate": candidate,
        }
        (args.workdir / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.finish_summary(
            status="SUCCESS",
            summary_path=args.workdir / "summaries" / "run_summary.json",
            final_metrics={
                "efficientnet_softmax": baseline["best_valid_metrics"],
                "efficientnet_ordinal": candidate["best_valid_metrics"],
            },
        )
    except Exception as exc:
        logger.exception("RUN_FAILED", "V009 ordinal-head screening failed", exc, phase="FAILED")
        logger.finish_summary(status="FAILED", summary_path=args.workdir / "summaries" / "run_summary.json")
        raise


if __name__ == "__main__":
    main()
