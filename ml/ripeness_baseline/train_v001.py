from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ml.data_pipeline.hf_metadata_audit import _fetch_page
from ml.data_pipeline.kgcv_manifest import STAGE_MAPPING
from ml.observability import RunLogger

CLASS_VALUES = [0, 1, 4]
CLASS_TO_INDEX = {v: i for i, v in enumerate(CLASS_VALUES)}
SEED = 20260910
EXPECTED_PHYSICAL_IMAGES = 1477
EXPECTED_SAMPLES = 3162
EXPECTED_SPLIT_COUNTS = {"train": 2243, "valid": 486, "test": 433}
EXPECTED_ASSIGNMENT_SHA256 = "5e2424f7c26d84e4f8d43ca90ba60b46806eb9d7bb361669c8b42ad27f2040ea"


def seed_all(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(False)


def fetch_bytes(url: str, logger: RunLogger, row_idx: int, retries: int = 5) -> bytes:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Nongtori-Baseline/1.0"})
            with urllib.request.urlopen(req, timeout=180) as response:
                return response.read()
        except Exception as exc:
            last = exc
            backoff = min(16, 2 ** (attempt - 1))
            logger.emit(
                "WARNING",
                "REMOTE_FETCH_RETRY",
                "image fetch failed; retrying",
                phase="CACHE_BUILD",
                row_idx=row_idx,
                attempt=attempt,
                max_attempts=retries,
                error_type=type(exc).__name__,
                error_message=str(exc),
                backoff_sec=backoff,
            )
            if attempt < retries:
                time.sleep(backoff)
    raise RuntimeError(last)


def image_src(row: dict[str, Any]) -> str:
    image = row.get("image") or {}
    if isinstance(image, dict) and image.get("src"):
        return str(image["src"])
    raise ValueError("missing image.src")


def _stage_for_category(category_id: int) -> str | None:
    return {
        0: "flower",
        1: "green",
        2: "overripe",
        3: "red",
        4: "small g",
        5: "turning red",
        6: "white",
    }.get(category_id)


def _assignment_sha256(records: list[dict[str, Any]]) -> str:
    rows = []
    for record in records:
        sample_id = f"kgcv:{record['row_idx']}:{record['object_idx']}"
        rows.append((sample_id, record["sha256"], record["split"], str(record["label"])))
    rows.sort()
    payload = "\n".join("|".join(item) for item in rows) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_crop_cache(root: Path, logger: RunLogger) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    logger.emit(
        "INFO",
        "PHASE_STARTED",
        "building KGCV object crop cache from frozen asset universe",
        phase="CACHE_BUILD",
        expected_physical_images=EXPECTED_PHYSICAL_IMAGES,
        expected_samples=EXPECTED_SAMPLES,
    )

    first = _fetch_page(offset=0, length=100)
    total = int(first["num_rows_total"])
    pages = [first]
    for offset in range(100, total, 100):
        pages.append(_fetch_page(offset=offset, length=min(100, total - offset)))

    records: list[dict[str, Any]] = []
    hash_to_rows: dict[str, list[int]] = {}
    errors: list[dict[str, Any]] = []
    processed = 0
    next_pct = 5

    # IMPORTANT: every one of the 1,477 physical images is hashed before the
    # split is assigned. This reproduces KGCV-RIPENESS-V001 exactly. Eligible
    # object filtering happens only after the physical image enters the frozen
    # asset universe.
    for page in pages:
        for wrapped in page.get("rows", []):
            row_idx = int(wrapped["row_idx"])
            row = wrapped.get("row") or {}
            objects = row.get("objects") or {}
            processed += 1
            try:
                data = fetch_bytes(image_src(row), logger, row_idx)
                sha256 = hashlib.sha256(data).hexdigest()
                hash_to_rows.setdefault(sha256, []).append(row_idx)

                categories = objects.get("categories") or []
                eligible: list[tuple[int, str, int]] = []
                for object_idx, category_id in enumerate(categories):
                    stage = _stage_for_category(int(category_id))
                    spec = STAGE_MAPPING.get(stage or "", {})
                    if spec.get("eligible") and spec.get("maturity") in CLASS_TO_INDEX:
                        eligible.append((object_idx, str(stage), int(spec["maturity"])))

                if eligible:
                    image = Image.open(io.BytesIO(data)).convert("RGB")
                    width, height = image.size
                    bboxes = objects.get("bbox") or []
                    for object_idx, stage, maturity in eligible:
                        if object_idx >= len(bboxes):
                            raise ValueError(f"missing bbox object={object_idx}")
                        x, y, bbox_width, bbox_height = [float(v) for v in bboxes[object_idx]]
                        x1 = max(0, int(math.floor(x)))
                        y1 = max(0, int(math.floor(y)))
                        x2 = min(width, int(math.ceil(x + bbox_width)))
                        y2 = min(height, int(math.ceil(y + bbox_height)))
                        if x2 <= x1 or y2 <= y1:
                            raise ValueError(f"invalid bbox {bboxes[object_idx]}")
                        path = root / f"{row_idx}_{object_idx}.jpg"
                        image.crop((x1, y1, x2, y2)).save(path, quality=92)
                        records.append(
                            {
                                "row_idx": row_idx,
                                "object_idx": object_idx,
                                "sha256": sha256,
                                "path": str(path),
                                "label": maturity,
                                "stage": stage,
                            }
                        )
            except Exception as exc:
                errors.append({"row_idx": row_idx, "error": str(exc)})
                logger.exception(
                    "CACHE_ROW_FAILED",
                    "failed to materialize source row",
                    exc,
                    phase="CACHE_BUILD",
                    row_idx=row_idx,
                )

            pct = processed * 100 / total
            if pct >= next_pct or processed == total:
                logger.progress(
                    phase="CACHE_BUILD",
                    current=processed,
                    total=total,
                    message="source rows scanned",
                    physical_hashes=len(hash_to_rows),
                    crop_samples=len(records),
                    failed_rows=len(errors),
                )
                next_pct += 5

    hashes = sorted(hash_to_rows)
    random.Random(SEED).shuffle(hashes)
    n_hashes = len(hashes)
    train_end = round(n_hashes * 0.70)
    valid_end = train_end + round(n_hashes * 0.15)
    split_of = {
        sha: ("train" if i < train_end else "valid" if i < valid_end else "test")
        for i, sha in enumerate(hashes)
    }
    for record in records:
        record["split"] = split_of[record["sha256"]]

    split_counts = dict(Counter(record["split"] for record in records))
    assignment_sha256 = _assignment_sha256(records)
    meta = {
        "physical_images": len(hash_to_rows),
        "samples": len(records),
        "errors": errors,
        "records": records,
        "split_counts": split_counts,
        "class_counts": dict(Counter(str(record["label"]) for record in records)),
        "assignment_sha256": assignment_sha256,
    }
    (root / "cache_manifest.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    logger.emit(
        "INFO",
        "SNAPSHOT_ASSIGNMENT_VERIFIED",
        "reconstructed frozen split assignment",
        phase="CACHE_BUILD",
        physical_images=meta["physical_images"],
        samples=meta["samples"],
        split_counts=split_counts,
        assignment_sha256=assignment_sha256,
        expected_assignment_sha256=EXPECTED_ASSIGNMENT_SHA256,
    )
    logger.emit(
        "INFO",
        "PHASE_COMPLETED",
        "crop cache built",
        phase="CACHE_BUILD",
        physical_images=meta["physical_images"],
        samples=meta["samples"],
        split_counts=meta["split_counts"],
        class_counts=meta["class_counts"],
        failed_rows=len(errors),
    )
    return meta


def metrics(y_true: list[int], y_pred: list[int]) -> dict[str, Any]:
    from sklearn.metrics import (
        accuracy_score,
        cohen_kappa_score,
        confusion_matrix,
        f1_score,
        precision_recall_fscore_support,
    )

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=CLASS_VALUES, zero_division=0
    )
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=CLASS_VALUES, average="macro", zero_division=0)),
        "ordinal_mae": float(np.mean(np.abs(np.array(y_true) - np.array(y_pred)))),
        "weighted_kappa": float(cohen_kappa_score(y_true, y_pred, labels=CLASS_VALUES, weights="quadratic")),
        "per_class": {
            str(class_value): {
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
            }
            for i, class_value in enumerate(CLASS_VALUES)
        },
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=CLASS_VALUES).tolist(),
    }


def train(cache: dict[str, Any], out: Path, logger: RunLogger, max_epochs: int = 30) -> dict[str, Any]:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset
    from torchvision import models, transforms

    class DS(Dataset):
        def __init__(self, records: list[dict[str, Any]], train_mode: bool = False):
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
            return (
                self.transform(Image.open(record["path"]).convert("RGB")),
                CLASS_TO_INDEX[record["label"]],
            )

    records = cache["records"]
    train_records = [r for r in records if r["split"] == "train"]
    valid_records = [r for r in records if r["split"] == "valid"]
    test_records = [r for r in records if r["split"] == "test"]
    counts = Counter(r["label"] for r in train_records)
    weights = torch.tensor(
        [len(train_records) / (len(CLASS_VALUES) * counts[c]) for c in CLASS_VALUES],
        dtype=torch.float32,
    )

    def loader(records_: list[dict[str, Any]], train_mode: bool) -> DataLoader:
        return DataLoader(
            DS(records_, train_mode),
            batch_size=32,
            shuffle=train_mode,
            num_workers=2,
            pin_memory=False,
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.emit(
        "INFO",
        "TRAINING_STARTED",
        "baseline training started",
        phase="TRAIN",
        device=str(device),
        max_epochs=max_epochs,
        train_samples=len(train_records),
        valid_samples=len(valid_records),
        test_samples=len(test_records),
        class_weights=weights.tolist(),
    )

    model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, len(CLASS_VALUES))
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss(weight=weights.to(device))
    best = -1.0
    best_epoch = 0
    patience = 0
    history: list[dict[str, Any]] = []
    best_path = out / "checkpoints" / "best.pt"
    best_path.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    def evaluate(data_loader: DataLoader) -> tuple[float, dict[str, Any]]:
        model.eval()
        y_true: list[int] = []
        y_pred: list[int] = []
        total_loss = 0.0
        count = 0
        with torch.no_grad():
            for images, labels in data_loader:
                images = images.to(device)
                labels = labels.to(device)
                logits = model(images)
                total_loss += criterion(logits, labels).item() * len(labels)
                count += len(labels)
                predictions = logits.argmax(1).cpu().tolist()
                y_true += [CLASS_VALUES[i] for i in labels.cpu().tolist()]
                y_pred += [CLASS_VALUES[i] for i in predictions]
        return total_loss / max(1, count), metrics(y_true, y_pred)

    for epoch in range(1, max_epochs + 1):
        epoch_start = time.monotonic()
        model.train()
        total_train_loss = 0.0
        seen = 0
        train_loader = loader(train_records, True)
        batches = len(train_loader)
        next_batch_pct = 10
        logger.emit(
            "INFO",
            "EPOCH_STARTED",
            f"epoch {epoch}/{max_epochs} started",
            phase="TRAIN",
            epoch=epoch,
            max_epochs=max_epochs,
            learning_rate=optimizer.param_groups[0]["lr"],
        )

        for batch_index, (images, labels) in enumerate(train_loader, 1):
            images = images.to(device)
            labels = labels.to(device)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, labels)
            if not torch.isfinite(loss):
                raise RuntimeError(
                    f"non-finite loss at epoch={epoch} batch={batch_index}: {loss.item()}"
                )
            loss.backward()
            optimizer.step()
            total_train_loss += loss.item() * len(labels)
            seen += len(labels)
            pct = batch_index * 100 / batches
            if pct >= next_batch_pct or batch_index == batches:
                logger.progress(
                    phase="TRAIN_BATCH",
                    current=batch_index,
                    total=batches,
                    message=f"epoch {epoch} batch progress",
                    epoch=epoch,
                    running_train_loss=total_train_loss / max(1, seen),
                    learning_rate=optimizer.param_groups[0]["lr"],
                )
                next_batch_pct += 10

        valid_loss, valid_metrics = evaluate(loader(valid_records, False))
        improved = valid_metrics["macro_f1"] > best + 1e-8
        checkpoint_saved = False
        if improved:
            best = valid_metrics["macro_f1"]
            best_epoch = epoch
            patience = 0
            torch.save(model.state_dict(), best_path)
            checkpoint_sha = hashlib.sha256(best_path.read_bytes()).hexdigest()
            checkpoint_saved = True
            logger.emit(
                "INFO",
                "CHECKPOINT_SAVED",
                "new best checkpoint saved",
                phase="CHECKPOINT",
                epoch=epoch,
                checkpoint_path=str(best_path),
                checkpoint_sha256=checkpoint_sha,
                metric_name="valid_macro_f1",
                metric_value=best,
            )
        else:
            patience += 1
            logger.emit(
                "WARNING",
                "EARLY_STOPPING_WAIT",
                "validation metric did not improve",
                phase="VALIDATE",
                epoch=epoch,
                early_stopping_counter=patience,
                patience_limit=5,
                best_metric=best,
                best_epoch=best_epoch,
            )

        epoch_row = {
            "epoch": epoch,
            "train_loss": total_train_loss / seen,
            "valid_loss": valid_loss,
            "learning_rate": optimizer.param_groups[0]["lr"],
            "best_metric": best,
            "best_epoch": best_epoch,
            "early_stopping_counter": patience,
            "checkpoint_saved": checkpoint_saved,
            "epoch_elapsed_sec": round(time.monotonic() - epoch_start, 3),
            **valid_metrics,
        }
        history.append(epoch_row)
        logger.emit(
            "INFO",
            "EPOCH_COMPLETED",
            f"epoch {epoch}/{max_epochs} completed",
            phase="VALIDATE",
            **epoch_row,
        )
        if patience >= 5:
            logger.emit(
                "INFO",
                "EARLY_STOPPING_TRIGGERED",
                "early stopping triggered",
                phase="TRAIN",
                epoch=epoch,
                best_epoch=best_epoch,
                best_valid_macro_f1=best,
            )
            break

    if not best_path.exists():
        raise RuntimeError("required best checkpoint was not created")
    final_checkpoint_sha = hashlib.sha256(best_path.read_bytes()).hexdigest()
    model.load_state_dict(torch.load(best_path, map_location=device, weights_only=True))
    logger.emit(
        "INFO",
        "TEST_STARTED",
        "running final frozen test evaluation",
        phase="TEST",
        test_samples=len(test_records),
        best_epoch=best_epoch,
        checkpoint_sha256=final_checkpoint_sha,
    )
    test_loss, test_metrics = evaluate(loader(test_records, False))
    logger.emit(
        "INFO",
        "TEST_COMPLETED",
        "final test evaluation completed",
        phase="TEST",
        test_loss=test_loss,
        **test_metrics,
    )
    result = {
        "experiment_id": "RIPENESS-BASELINE-V001",
        "snapshot_id": "KGCV-RIPENESS-V001",
        "status": "REPRODUCED",
        "device": str(device),
        "seed": SEED,
        "assignment_sha256": cache["assignment_sha256"],
        "best_epoch": best_epoch,
        "best_valid_macro_f1": best,
        "best_checkpoint": str(best_path),
        "best_checkpoint_sha256": final_checkpoint_sha,
        "test_loss": test_loss,
        "test_metrics": test_metrics,
        "history": history,
        "cache_summary": {k: v for k, v in cache.items() if k != "records"},
    }
    (out / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workdir", type=Path, default=Path("artifacts/ripeness-baseline-v001")
    )
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()
    logger = RunLogger(args.workdir, "ripeness_baseline_v001")
    try:
        logger.emit(
            "INFO",
            "RUN_STARTED",
            "RIPENESS-BASELINE-V001 run started",
            phase="INIT",
            experiment_id="RIPENESS-BASELINE-V001",
            snapshot_id="KGCV-RIPENESS-V001",
            seed=SEED,
            max_epochs=args.epochs,
        )
        seed_all()
        cache = build_crop_cache(args.workdir / "crops", logger)
        if cache["errors"]:
            raise RuntimeError(f"cache errors={len(cache['errors'])}")
        if cache["physical_images"] != EXPECTED_PHYSICAL_IMAGES:
            raise RuntimeError(
                f"physical image contract failed: {cache['physical_images']} != {EXPECTED_PHYSICAL_IMAGES}"
            )
        if cache["samples"] != EXPECTED_SAMPLES:
            raise RuntimeError(
                f"sample contract failed: {cache['samples']} != {EXPECTED_SAMPLES}"
            )
        if cache["split_counts"] != EXPECTED_SPLIT_COUNTS:
            raise RuntimeError(
                f"split contract failed: {cache['split_counts']} != {EXPECTED_SPLIT_COUNTS}"
            )
        if cache["assignment_sha256"] != EXPECTED_ASSIGNMENT_SHA256:
            raise RuntimeError(
                "eligible assignment checksum mismatch: "
                f"{cache['assignment_sha256']} != {EXPECTED_ASSIGNMENT_SHA256}"
            )

        result = train(cache, args.workdir, logger, args.epochs)
        logger.finish_summary(
            status="SUCCESS",
            summary_path=args.workdir / "summaries" / "run_summary.json",
            input_count=cache["physical_images"],
            processed_count=cache["physical_images"],
            success_count=cache["samples"],
            failed_count=len(cache["errors"]),
            snapshot_assignment_sha256=cache["assignment_sha256"],
            best_checkpoint=result["best_checkpoint"],
            best_checkpoint_sha256=result["best_checkpoint_sha256"],
            best_metric={"valid_macro_f1": result["best_valid_macro_f1"]},
            final_metrics=result["test_metrics"],
        )
        print(json.dumps(result["test_metrics"], ensure_ascii=False, indent=2))
    except Exception as exc:
        logger.exception("RUN_FAILED", "baseline run failed", exc, phase="FAILED")
        logger.finish_summary(
            status="FAILED",
            summary_path=args.workdir / "summaries" / "run_summary.json",
        )
        raise


if __name__ == "__main__":
    main()
