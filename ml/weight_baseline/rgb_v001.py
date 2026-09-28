from __future__ import annotations

import argparse
import csv
import json
import math
import random
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SNAPSHOT_STATUS = "WEIGHT_SNAPSHOT_FROZEN"
EXPECTED_VIEWS_PER_FRUIT = 22
SEED = 20260928
MODEL_NAME = "EFFICIENTNET_B0_IMAGENET"
INPUT_SIZE = 224
RESIZE_SIZE = 256
EPOCHS = 15
PATIENCE = 4
BATCH_SIZE = 32
LEARNING_RATE = 1e-4
WEIGHT_DECAY = 1e-4
HUBER_BETA = 1.0
GRAD_CLIP_NORM = 5.0
PRIMARY_AGGREGATION = "MEAN_22_VIEW"


@dataclass(frozen=True)
class SnapshotRow:
    fruit_id: str
    split: str
    target_g: float
    relative_path: str
    sha256: str


def _to_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"non-finite {field}: {value!r}")
    return number


def _grade(weight_g: float) -> str:
    if weight_g >= 22:
        return "SP_WEIGHT"
    if weight_g >= 16:
        return "HI_WEIGHT"
    if weight_g >= 12:
        return "MD_WEIGHT"
    return "JM_WEIGHT_CANDIDATE"


def _metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    if not actual or len(actual) != len(predicted):
        raise ValueError("metrics require aligned non-empty values")
    errors = [prediction - target for target, prediction in zip(actual, predicted, strict=True)]
    abs_errors = [abs(error) for error in errors]
    squared_errors = [error * error for error in errors]
    mean_actual = sum(actual) / len(actual)
    ss_total = sum((value - mean_actual) ** 2 for value in actual)
    ss_residual = sum(squared_errors)
    return {
        "mae_g": sum(abs_errors) / len(abs_errors),
        "rmse_g": math.sqrt(sum(squared_errors) / len(squared_errors)),
        "r2": 1.0 - ss_residual / ss_total if ss_total > 1e-12 else 0.0,
        "bias_g": sum(errors) / len(errors),
        "max_abs_error_g": max(abs_errors),
    }


def _grade_metrics(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    expected = [_grade(value) for value in actual]
    observed = [_grade(value) for value in predicted]
    correct = sum(a == b for a, b in zip(expected, observed, strict=True))
    confusion = Counter(
        f"{a}->{b}" for a, b in zip(expected, observed, strict=True)
    )
    return {
        "grade_accuracy": correct / len(expected),
        "grade_confusion": dict(sorted(confusion.items())),
    }


def load_weight_snapshot(snapshot_dir: Path) -> tuple[dict[str, Any], list[SnapshotRow]]:
    snapshot_dir = Path(snapshot_dir)
    descriptor_path = snapshot_dir / "WEIGHT_SNAPSHOT.json"
    manifest_path = snapshot_dir / "sample-manifest.csv"
    if not descriptor_path.exists():
        raise FileNotFoundError(f"weight snapshot descriptor missing: {descriptor_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"weight sample manifest missing: {manifest_path}")

    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    if descriptor.get("status") != SNAPSHOT_STATUS:
        raise ValueError(f"weight snapshot is not frozen: {descriptor.get('status')!r}")
    if descriptor.get("split_group") != "FRUIT_ID":
        raise ValueError("RGB baseline requires FRUIT_ID atomic split")
    if descriptor.get("primary_target") != "weight_with_calyx_g":
        raise ValueError("unexpected weight target contract")

    with manifest_path.open(encoding="utf-8", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))
    if len(raw_rows) != int(descriptor.get("image_count") or 0):
        raise ValueError("sample manifest image count does not match descriptor")

    rows: list[SnapshotRow] = []
    fruit_splits: dict[str, str] = {}
    fruit_targets: dict[str, float] = {}
    fruit_views: Counter[str] = Counter()
    seen_paths: set[str] = set()

    for raw in raw_rows:
        fruit_id = str(raw.get("fruit_id") or "").strip()
        split = str(raw.get("split") or "").strip()
        relative_path = str(raw.get("relative_path") or "").strip()
        digest = str(raw.get("sha256") or "").strip().lower()
        target = _to_float(raw.get("weight_with_calyx_g"), "weight_with_calyx_g")
        if not fruit_id:
            raise ValueError("sample manifest row missing fruit_id")
        if split not in {"train", "validation", "test"}:
            raise ValueError(f"unexpected split for {fruit_id}: {split!r}")
        if not relative_path:
            raise ValueError(f"sample manifest row missing relative_path for {fruit_id}")
        if relative_path in seen_paths:
            raise ValueError(f"duplicate sample relative_path: {relative_path}")
        seen_paths.add(relative_path)
        if len(digest) != 64:
            raise ValueError(f"invalid SHA-256 for {relative_path}")

        prior_split = fruit_splits.setdefault(fruit_id, split)
        if prior_split != split:
            raise ValueError(f"FRUIT_ID leakage in manifest: {fruit_id}")
        prior_target = fruit_targets.setdefault(fruit_id, target)
        if abs(prior_target - target) > 1e-9:
            raise ValueError(f"inconsistent target across views for {fruit_id}")

        fruit_views[fruit_id] += 1
        rows.append(
            SnapshotRow(
                fruit_id=fruit_id,
                split=split,
                target_g=target,
                relative_path=relative_path,
                sha256=digest,
            )
        )

    wrong_views = {
        fruit_id: count
        for fruit_id, count in fruit_views.items()
        if count != EXPECTED_VIEWS_PER_FRUIT
    }
    if wrong_views:
        sample = dict(list(sorted(wrong_views.items()))[:10])
        raise ValueError(
            f"RGB baseline requires exactly {EXPECTED_VIEWS_PER_FRUIT} views per fruit: {sample}"
        )
    if len(fruit_views) != int(descriptor.get("fruit_count") or 0):
        raise ValueError("sample manifest fruit count does not match descriptor")

    return descriptor, rows


def aggregate_fruit_predictions(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        fruit_id = str(record["fruit_id"])
        grouped[fruit_id].append(record)

    result: list[dict[str, Any]] = []
    for fruit_id in sorted(grouped):
        items = grouped[fruit_id]
        splits = {str(item["split"]) for item in items}
        targets = {round(float(item["target_g"]), 9) for item in items}
        if len(splits) != 1 or len(targets) != 1:
            raise ValueError(f"inconsistent view records for fruit {fruit_id}")
        if len(items) != EXPECTED_VIEWS_PER_FRUIT:
            raise ValueError(
                f"fruit {fruit_id} has {len(items)} predictions; "
                f"expected {EXPECTED_VIEWS_PER_FRUIT}"
            )
        prediction = sum(float(item["prediction_g"]) for item in items) / len(items)
        result.append(
            {
                "fruit_id": fruit_id,
                "split": next(iter(splits)),
                "actual_weight_g": float(items[0]["target_g"]),
                "predicted_weight_g": prediction,
                "view_count": len(items),
            }
        )
    return result


def evaluate_fruit_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("cannot evaluate empty fruit predictions")
    actual = [float(record["actual_weight_g"]) for record in records]
    predicted = [float(record["predicted_weight_g"]) for record in records]
    report: dict[str, Any] = _metrics(actual, predicted)
    report.update(_grade_metrics(actual, predicted))
    report["n_fruits"] = len(records)
    return report


def _verify_assets(snapshot_dir: Path, descriptor: dict[str, Any], rows: list[SnapshotRow]) -> Path:
    asset_root_text = str(descriptor.get("materialized_asset_root") or "").strip()
    if not asset_root_text:
        raise ValueError("snapshot descriptor has no materialized_asset_root")
    asset_root = Path(asset_root_text)
    if not asset_root.is_absolute():
        # Snapshot stores a repository-relative root.
        repo_root = snapshot_dir.parent.parent.parent
        asset_root = repo_root / asset_root
    if not asset_root.exists():
        raise FileNotFoundError(f"materialized RGB asset root missing: {asset_root}")

    missing = []
    for row in rows:
        path = asset_root / Path(row.relative_path)
        if not path.is_file():
            missing.append(str(path))
            if len(missing) >= 10:
                break
    if missing:
        raise FileNotFoundError(f"RGB assets missing; sample={missing}")
    return asset_root


def _seed_all(seed: int = SEED) -> None:
    random.seed(seed)
    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _runtime_imports():
    try:
        import torch
        from PIL import Image
        from torch import nn
        from torch.utils.data import DataLoader, Dataset
        from torchvision import models, transforms
    except ImportError as exc:
        raise RuntimeError(
            "RGB baseline requires torch, torchvision, and Pillow in the local ML environment"
        ) from exc
    return torch, Image, nn, DataLoader, Dataset, models, transforms


def run_rgb_baseline(
    snapshot_dir: Path,
    output_dir: Path,
    *,
    device_name: str | None = None,
    workers: int = 4,
) -> dict[str, Any]:
    torch, Image, nn, DataLoader, Dataset, models, transforms = _runtime_imports()
    snapshot_dir = Path(snapshot_dir)
    output_dir = Path(output_dir)

    final_report = output_dir / "rgb_baseline.json"
    if final_report.exists():
        raise FileExistsError(
            f"immutable RGB baseline result already exists: {final_report}"
        )

    descriptor, rows = load_weight_snapshot(snapshot_dir)
    asset_root = _verify_assets(snapshot_dir, descriptor, rows)
    split_rows = {
        split: [row for row in rows if row.split == split]
        for split in ("train", "validation", "test")
    }
    for split, items in split_rows.items():
        if not items:
            raise ValueError(f"weight snapshot has empty {split} image split")

    class WeightViewDataset(Dataset):
        def __init__(self, items: list[SnapshotRow], transform):
            self.items = items
            self.transform = transform

        def __len__(self):
            return len(self.items)

        def __getitem__(self, index: int):
            row = self.items[index]
            path = asset_root / Path(row.relative_path)
            image = Image.open(path).convert("RGB")
            tensor = self.transform(image)
            return tensor, torch.tensor(row.target_g, dtype=torch.float32), row.fruit_id, row.split

    normalize = transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    )
    train_transform = transforms.Compose(
        [
            transforms.Resize(RESIZE_SIZE),
            transforms.CenterCrop(INPUT_SIZE),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.ToTensor(),
            normalize,
        ]
    )
    eval_transform = transforms.Compose(
        [
            transforms.Resize(RESIZE_SIZE),
            transforms.CenterCrop(INPUT_SIZE),
            transforms.ToTensor(),
            normalize,
        ]
    )

    _seed_all(SEED)
    if device_name:
        device = torch.device(device_name)
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    train_loader = DataLoader(
        WeightViewDataset(split_rows["train"], train_transform),
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=workers,
        pin_memory=device.type == "cuda",
        persistent_workers=workers > 0,
    )
    validation_loader = DataLoader(
        WeightViewDataset(split_rows["validation"], eval_transform),
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=workers,
        pin_memory=device.type == "cuda",
        persistent_workers=workers > 0,
    )
    test_loader = DataLoader(
        WeightViewDataset(split_rows["test"], eval_transform),
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=workers,
        pin_memory=device.type == "cuda",
        persistent_workers=workers > 0,
    )

    weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1
    model = models.efficientnet_b0(weights=weights)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, 1)
    model.to(device)

    criterion = nn.SmoothL1Loss(beta=HUBER_BETA)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
    )
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "best.pt"
    history_path = output_dir / "training_history.json"

    def infer(loader) -> tuple[list[dict[str, Any]], float]:
        model.eval()
        records: list[dict[str, Any]] = []
        total_loss = 0.0
        total_count = 0
        with torch.no_grad():
            for images, targets, fruit_ids, splits in loader:
                images = images.to(device, non_blocking=True)
                targets = targets.to(device, non_blocking=True)
                with torch.amp.autocast(
                    device_type=device.type,
                    enabled=device.type == "cuda",
                ):
                    outputs = model(images).squeeze(1)
                    loss = criterion(outputs, targets)
                total_loss += float(loss.item()) * int(targets.shape[0])
                total_count += int(targets.shape[0])
                predictions = outputs.detach().cpu().tolist()
                target_values = targets.detach().cpu().tolist()
                for fruit_id, split, target, prediction in zip(
                    fruit_ids,
                    splits,
                    target_values,
                    predictions,
                    strict=True,
                ):
                    records.append(
                        {
                            "fruit_id": str(fruit_id),
                            "split": str(split),
                            "target_g": float(target),
                            "prediction_g": float(prediction),
                        }
                    )
        return records, total_loss / max(1, total_count)

    history: list[dict[str, Any]] = []
    best_validation_mae = float("inf")
    best_epoch = 0
    stale_epochs = 0

    for epoch in range(1, EPOCHS + 1):
        model.train()
        train_loss_sum = 0.0
        train_count = 0
        for images, targets, _fruit_ids, _splits in train_loader:
            images = images.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(
                device_type=device.type,
                enabled=device.type == "cuda",
            ):
                outputs = model(images).squeeze(1)
                loss = criterion(outputs, targets)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)
            scaler.step(optimizer)
            scaler.update()
            train_loss_sum += float(loss.item()) * int(targets.shape[0])
            train_count += int(targets.shape[0])

        validation_views, validation_loss = infer(validation_loader)
        validation_fruits = aggregate_fruit_predictions(validation_views)
        validation_metrics = evaluate_fruit_records(validation_fruits)
        epoch_report = {
            "epoch": epoch,
            "train_view_loss": train_loss_sum / max(1, train_count),
            "validation_view_loss": validation_loss,
            "validation_fruit_metrics": validation_metrics,
        }
        history.append(epoch_report)
        history_path.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        validation_mae = float(validation_metrics["mae_g"])
        if validation_mae < best_validation_mae - 1e-4:
            best_validation_mae = validation_mae
            best_epoch = epoch
            stale_epochs = 0
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "validation_fruit_mae_g": validation_mae,
                    "model_name": MODEL_NAME,
                    "seed": SEED,
                },
                checkpoint_path,
            )
        else:
            stale_epochs += 1
            if stale_epochs >= PATIENCE:
                break

    if not checkpoint_path.exists():
        raise RuntimeError("RGB baseline training produced no checkpoint")

    checkpoint = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])

    split_loaders = {
        "train": DataLoader(
            WeightViewDataset(split_rows["train"], eval_transform),
            batch_size=BATCH_SIZE,
            shuffle=False,
            num_workers=workers,
            pin_memory=device.type == "cuda",
            persistent_workers=workers > 0,
        ),
        "validation": validation_loader,
        "test": test_loader,
    }

    evaluations: dict[str, Any] = {}
    fruit_predictions: list[dict[str, Any]] = []
    for split in ("train", "validation", "test"):
        view_records, view_loss = infer(split_loaders[split])
        fruit_records = aggregate_fruit_predictions(view_records)
        metrics = evaluate_fruit_records(fruit_records)
        metrics["view_loss"] = view_loss
        metrics["n_views"] = len(view_records)
        evaluations[split] = metrics
        fruit_predictions.extend(fruit_records)

    prediction_path = output_dir / "rgb_fruit_predictions.csv"
    with prediction_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fruit_id",
                "split",
                "actual_weight_g",
                "predicted_weight_g",
                "view_count",
            ],
        )
        writer.writeheader()
        writer.writerows(fruit_predictions)

    report = {
        "status": "RGB_BASELINE_COMPLETE",
        "snapshot_id": descriptor.get("snapshot_id"),
        "task": "STRAWBERRY_WEIGHT_REGRESSION",
        "model": MODEL_NAME,
        "pretrained_weights": "IMAGENET1K_V1",
        "primary_target": "weight_with_calyx_g",
        "training_unit": "RGB_VIEW",
        "evaluation_unit": "FRUIT_ID",
        "aggregation": PRIMARY_AGGREGATION,
        "split_group": "FRUIT_ID",
        "seed": SEED,
        "device": str(device),
        "protocol": {
            "input_size": INPUT_SIZE,
            "resize_size": RESIZE_SIZE,
            "epochs_max": EPOCHS,
            "patience": PATIENCE,
            "batch_size": BATCH_SIZE,
            "learning_rate": LEARNING_RATE,
            "weight_decay": WEIGHT_DECAY,
            "loss": f"SmoothL1(beta={HUBER_BETA})",
            "gradient_clip_norm": GRAD_CLIP_NORM,
            "train_augmentation": ["horizontal_flip_0.5"],
            "checkpoint_selection": "BEST_VALIDATION_FRUIT_MAE",
            "test_policy": "REPORT_ONCE_NO_TEST_TUNING",
        },
        "best_epoch": best_epoch,
        "best_validation_mae_g": best_validation_mae,
        "metrics": evaluations,
        "checkpoint": str(checkpoint_path),
        "prediction_file": str(prediction_path),
        "history_file": str(history_path),
    }
    final_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Train the fixed WEIGHT-DRYAD-V001 RGB-only EfficientNet-B0 baseline"
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=Path("data/snapshots/WEIGHT-DRYAD-V001"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/rgb-v001"),
    )
    parser.add_argument("--device")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        report = run_rgb_baseline(
            args.snapshot_dir,
            args.output_dir,
            device_name=args.device,
            workers=args.workers,
        )
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "RGB_BASELINE_BLOCKED", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
