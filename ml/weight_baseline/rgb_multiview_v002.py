from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from ml.weight_baseline.development_cv_v1 import _load_official_split_rows
from ml.weight_baseline.geometry_v002 import _evaluate
from ml.weight_baseline.rgb_v001 import (
    BATCH_SIZE,
    EPOCHS,
    EXPECTED_VIEWS_PER_FRUIT,
    GRAD_CLIP_NORM,
    HUBER_BETA,
    INPUT_SIZE,
    LEARNING_RATE,
    MODEL_NAME,
    PATIENCE,
    RESIZE_SIZE,
    SEED,
    WEIGHT_DECAY,
    WeightViewDataset,
    _runtime_imports,
    _seed_all,
    _verify_assets,
    load_weight_snapshot,
)

AGGREGATIONS = (
    "MEAN_22_VIEW",
    "MEDIAN_22_VIEW",
    "TRIMMED_MEAN_10PCT_EACH_TAIL",
    "TRIMMED_MEAN_20PCT_EACH_TAIL",
)
CHECKPOINT_AGGREGATION = "MEAN_22_VIEW"

LOG_WIDTH = 88


def _bar(current: int, total: int, width: int = 16) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    fraction = min(1.0, max(0.0, current / total))
    filled = int(round(width * fraction))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _print_header(title: str) -> None:
    print("", flush=True)
    print("=" * LOG_WIDTH, flush=True)
    print(f" {title}", flush=True)
    print("=" * LOG_WIDTH, flush=True)


def _device_diagnostics(torch) -> dict[str, Any]:
    cuda_available = bool(torch.cuda.is_available())
    device_count = int(torch.cuda.device_count()) if cuda_available else 0
    names = [
        str(torch.cuda.get_device_name(index))
        for index in range(device_count)
    ] if cuda_available else []
    return {
        "python": sys.executable,
        "torch_version": str(torch.__version__),
        "torch_cuda_build": str(torch.version.cuda),
        "cuda_available": cuda_available,
        "cuda_device_count": device_count,
        "cuda_device_names": names,
    }


def _resolve_device(
    torch,
    *,
    device_name: str | None,
    allow_cpu: bool,
):
    diagnostics = _device_diagnostics(torch)
    if device_name:
        requested = torch.device(device_name)
        if requested.type == "cuda" and not diagnostics["cuda_available"]:
            raise RuntimeError(
                "CUDA was explicitly requested but is unavailable in the current Python/PyTorch "
                f"environment. python={diagnostics['python']} · "
                f"torch={diagnostics['torch_version']} · "
                f"torch CUDA build={diagnostics['torch_cuda_build']} · "
                "torch.cuda.is_available()=False"
            )
        device = requested
    else:
        device = torch.device(
            "cuda" if diagnostics["cuda_available"] else "cpu"
        )

    if device.type == "cpu" and not allow_cpu:
        raise RuntimeError(
            "RGB V002 is compute-heavy (5 CV folds + 1 final fit), so CPU training is blocked "
            "by default. The current Python/PyTorch environment cannot use CUDA. "
            f"python={diagnostics['python']} · torch={diagnostics['torch_version']} · "
            f"torch CUDA build={diagnostics['torch_cuda_build']} · "
            f"torch.cuda.is_available()={diagnostics['cuda_available']}. "
            "Activate the CUDA-enabled environment and rerun. Use --allow-cpu only when CPU "
            "execution is intentional."
        )
    return device, diagnostics


def _print_run_overview(
    *,
    device,
    diagnostics: dict[str, Any],
    train_count: int,
    validation_count: int,
    test_count: int,
    fold_count: int,
    output_dir: Path,
    workers: int,
) -> None:
    _print_header("RGB WEIGHT V002 · 22-VIEW AGGREGATION")
    if device.type == "cuda":
        device_text = (
            f"CUDA · {diagnostics['cuda_device_names'][0]}"
            if diagnostics["cuda_device_names"]
            else "CUDA"
        )
    else:
        device_text = "CPU"
    print(f" 목적       22장의 view 예측을 fruit-level 1개 값으로 합치는 방법 비교", flush=True)
    print(f" 모델       EfficientNet-B0 · V001 구조 유지 · aggregation만 변경", flush=True)
    print(
        f" 데이터     train {train_count} · validation {validation_count}(확인용) · "
        f"test {test_count}(LOCKED)",
        flush=True,
    )
    print(
        f" 개발       {fold_count}-fold CV + final train-only 1회 · 총 {fold_count + 1}개 학습 단계",
        flush=True,
    )
    print(f" 실행장치   {device_text} · workers={workers}", flush=True)
    print(
        f" 환경       PyTorch {diagnostics['torch_version']} · "
        f"CUDA build {diagnostics['torch_cuda_build']} · "
        f"cuda_available={diagnostics['cuda_available']}",
        flush=True,
    )
    print(f" Python     {diagnostics['python']}", flush=True)
    print(f" 결과       {output_dir}", flush=True)
    print("-" * LOG_WIDTH, flush=True)
    print(
        " 선택 기준  Grade error → Threshold crossing → MAE → RMSE",
        flush=True,
    )
    print("=" * LOG_WIDTH, flush=True)



def _read_cv_assignments(path: Path) -> dict[str, int]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"development CV manifest missing: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("development CV manifest is empty")

    required = {"fruit_id", "official_split", "cv_fold"}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"development CV manifest missing columns: {sorted(missing)}")

    result: dict[str, int] = {}
    for row in rows:
        fruit_id = str(row.get("fruit_id") or "").strip()
        if str(row.get("official_split") or "").strip() != "train":
            raise ValueError(f"non-train fruit in development CV: {fruit_id}")
        if fruit_id in result:
            raise ValueError(f"duplicate fruit in development CV: {fruit_id}")
        try:
            fold = int(row.get("cv_fold") or "")
        except ValueError as exc:
            raise ValueError(f"invalid cv_fold for {fruit_id}") from exc
        if fold < 0:
            raise ValueError(f"negative cv_fold for {fruit_id}")
        result[fruit_id] = fold
    return result


def _aggregate_values(values: list[float], method: str) -> float:
    if len(values) != EXPECTED_VIEWS_PER_FRUIT:
        raise ValueError(
            f"aggregation requires exactly {EXPECTED_VIEWS_PER_FRUIT} predictions; "
            f"got {len(values)}"
        )
    ordered = sorted(float(value) for value in values)
    if method == "MEAN_22_VIEW":
        kept = ordered
    elif method == "MEDIAN_22_VIEW":
        return float(statistics.median(ordered))
    elif method == "TRIMMED_MEAN_10PCT_EACH_TAIL":
        trim = int(math.floor(EXPECTED_VIEWS_PER_FRUIT * 0.10))
        kept = ordered[trim:len(ordered) - trim]
    elif method == "TRIMMED_MEAN_20PCT_EACH_TAIL":
        trim = int(math.floor(EXPECTED_VIEWS_PER_FRUIT * 0.20))
        kept = ordered[trim:len(ordered) - trim]
    else:
        raise ValueError(f"unsupported aggregation: {method}")
    if not kept:
        raise ValueError(f"aggregation removed all view predictions: {method}")
    return sum(kept) / len(kept)


def aggregate_view_records(
    records: Iterable[dict[str, Any]],
    method: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["fruit_id"])].append(record)

    fruits: list[dict[str, Any]] = []
    for fruit_id in sorted(grouped):
        items = grouped[fruit_id]
        targets = {round(float(item["target_g"]), 9) for item in items}
        if len(targets) != 1:
            raise ValueError(f"inconsistent target across views for {fruit_id}")
        if len(items) != EXPECTED_VIEWS_PER_FRUIT:
            raise ValueError(
                f"fruit {fruit_id} has {len(items)} view predictions; "
                f"expected {EXPECTED_VIEWS_PER_FRUIT}"
            )
        values = [float(item["prediction_g"]) for item in items]
        fruits.append(
            {
                "fruit_id": fruit_id,
                "actual_weight_g": float(items[0]["target_g"]),
                "predicted_weight_g": _aggregate_values(values, method),
                "view_prediction_std_g": statistics.pstdev(values),
                "view_prediction_range_g": max(values) - min(values),
                "view_count": len(values),
            }
        )
    return fruits


def _evaluate_aggregation(
    records: list[dict[str, Any]],
    method: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fruits = aggregate_view_records(records, method)
    actual = [float(row["actual_weight_g"]) for row in fruits]
    predicted = [float(row["predicted_weight_g"]) for row in fruits]
    metrics = _evaluate(actual, predicted)
    metrics["aggregation"] = method
    metrics["mean_view_prediction_std_g"] = (
        sum(float(row["view_prediction_std_g"]) for row in fruits) / len(fruits)
    )
    metrics["mean_view_prediction_range_g"] = (
        sum(float(row["view_prediction_range_g"]) for row in fruits) / len(fruits)
    )
    return fruits, metrics


def _candidate_key(item: dict[str, Any]) -> tuple[Any, ...]:
    preference = {
        name: index
        for index, name in enumerate(AGGREGATIONS)
    }
    metrics = item["oof_metrics"]
    return (
        int(metrics["grade_error_count"]),
        int(metrics["threshold_crossing_count"]),
        float(metrics["mae_g"]),
        float(metrics["rmse_g"]),
        preference[item["aggregation"]],
    )


def _build_transforms(transforms):
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
    return train_transform, eval_transform


def _build_model(nn, models, device):
    weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1
    model = models.efficientnet_b0(weights=weights)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, 1)
    model.to(device)
    return model


def _infer_views(
    model,
    loader,
    *,
    device,
    torch,
    criterion,
) -> tuple[list[dict[str, Any]], float]:
    model.eval()
    records: list[dict[str, Any]] = []
    total_loss = 0.0
    total_count = 0
    with torch.no_grad():
        for images, targets, fruit_ids, _splits in loader:
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
            targets_cpu = targets.detach().cpu().tolist()
            for fruit_id, target, prediction in zip(
                fruit_ids,
                targets_cpu,
                predictions,
                strict=True,
            ):
                records.append(
                    {
                        "fruit_id": str(fruit_id),
                        "target_g": float(target),
                        "prediction_g": float(prediction),
                    }
                )
    return records, total_loss / max(1, total_count)


def _train_fold(
    *,
    fold: int,
    train_rows,
    holdout_rows,
    asset_root: Path,
    output_dir: Path,
    device,
    workers: int,
    torch,
    nn,
    DataLoader,
    models,
    transforms,
) -> dict[str, Any]:
    fold_dir = output_dir / f"fold-{fold}"
    fold_dir.mkdir(parents=True, exist_ok=True)
    result_path = fold_dir / "fold_result.json"
    view_path = fold_dir / "holdout_view_predictions.csv"
    checkpoint_path = fold_dir / "best.pt"

    if result_path.exists() and view_path.exists() and checkpoint_path.exists():
        cached = json.loads(result_path.read_text(encoding="utf-8"))
        with view_path.open(encoding="utf-8", newline="") as handle:
            cached["holdout_view_predictions"] = list(csv.DictReader(handle))
        for row in cached["holdout_view_predictions"]:
            row["target_g"] = float(row["target_g"])
            row["prediction_g"] = float(row["prediction_g"])
        cached["reused"] = True
        return cached

    _seed_all(SEED + fold)
    train_transform, eval_transform = _build_transforms(transforms)
    train_loader = DataLoader(
        WeightViewDataset(train_rows, asset_root, train_transform),
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=workers,
        pin_memory=device.type == "cuda",
        persistent_workers=workers > 0,
    )
    holdout_loader = DataLoader(
        WeightViewDataset(holdout_rows, asset_root, eval_transform),
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=workers,
        pin_memory=device.type == "cuda",
        persistent_workers=workers > 0,
    )

    model = _build_model(nn, models, device)
    criterion = nn.SmoothL1Loss(beta=HUBER_BETA)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
    )
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    best_mae = float("inf")
    best_epoch = 0
    stale = 0
    history: list[dict[str, Any]] = []

    fold_number = fold + 1
    total_folds = 5
    print("", flush=True)
    print(
        f"[1-5/6] FOLD {fold_number}/{total_folds} "
        f"{_bar(fold_number - 1, total_folds)} · "
        f"train {len(train_rows) // EXPECTED_VIEWS_PER_FRUIT} fruit · "
        f"holdout {len(holdout_rows) // EXPECTED_VIEWS_PER_FRUIT} fruit",
        flush=True,
    )

    for epoch in range(1, EPOCHS + 1):
        started = time.perf_counter()
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

        holdout_views, holdout_view_loss = _infer_views(
            model,
            holdout_loader,
            device=device,
            torch=torch,
            criterion=criterion,
        )
        _holdout_fruits, holdout_metrics = _evaluate_aggregation(
            holdout_views,
            CHECKPOINT_AGGREGATION,
        )
        mae = float(holdout_metrics["mae_g"])
        improved = mae < best_mae - 1e-4
        if improved:
            best_mae = mae
            best_epoch = epoch
            stale = 0
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "holdout_mean22_mae_g": mae,
                    "model_name": MODEL_NAME,
                    "seed": SEED + fold,
                },
                checkpoint_path,
            )
        else:
            stale += 1

        history.append(
            {
                "epoch": epoch,
                "train_view_loss": train_loss_sum / max(1, train_count),
                "holdout_view_loss": holdout_view_loss,
                "holdout_mean22_metrics": holdout_metrics,
                "improved": improved,
                "elapsed_seconds": time.perf_counter() - started,
            }
        )
        epoch_elapsed = float(history[-1]["elapsed_seconds"])
        best_marker = " ★BEST" if improved else ""
        print(
            f"  E{epoch:02d}/{EPOCHS:02d} {_bar(epoch, EPOCHS)} · "
            f"MAE {mae:.3f}g · RMSE {float(holdout_metrics['rmse_g']):.3f} · "
            f"R² {float(holdout_metrics['r2']):.3f} · "
            f"Grade {float(holdout_metrics['grade_accuracy']) * 100:5.1f}% · "
            f"best {best_mae:.3f}g@E{best_epoch:02d}{best_marker} · "
            f"early-stop {stale}/{PATIENCE} · {_duration(epoch_elapsed)}",
            flush=True,
        )
        if stale >= PATIENCE:
            print(
                f"  ↳ early stop · best E{best_epoch:02d} · MAE {best_mae:.3f}g",
                flush=True,
            )
            break

    print(
        f"  ✓ FOLD {fold_number}/{total_folds} 완료 · "
        f"best E{best_epoch:02d} · MAE {best_mae:.3f}g",
        flush=True,
    )

    checkpoint = torch.load(
        checkpoint_path,
        map_location=device,
        weights_only=False,
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    holdout_views, _ = _infer_views(
        model,
        holdout_loader,
        device=device,
        torch=torch,
        criterion=criterion,
    )

    with view_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["fruit_id", "target_g", "prediction_g"],
        )
        writer.writeheader()
        writer.writerows(holdout_views)

    report = {
        "fold": fold,
        "best_epoch": best_epoch,
        "best_holdout_mean22_mae_g": best_mae,
        "checkpoint_selector": CHECKPOINT_AGGREGATION,
        "history": history,
        "holdout_view_prediction_file": str(view_path),
        "holdout_view_predictions": holdout_views,
        "reused": False,
    }
    serializable = {
        key: value
        for key, value in report.items()
        if key != "holdout_view_predictions"
    }
    result_path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _train_final_model(
    *,
    train_rows,
    validation_rows,
    final_epoch: int,
    asset_root: Path,
    output_dir: Path,
    device,
    workers: int,
    torch,
    nn,
    DataLoader,
    models,
    transforms,
) -> list[dict[str, Any]]:
    final_dir = output_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = final_dir / "final_train_only.pt"
    view_path = final_dir / "validation_view_predictions.csv"

    if checkpoint_path.exists() and view_path.exists():
        with view_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return [
            {
                "fruit_id": row["fruit_id"],
                "target_g": float(row["target_g"]),
                "prediction_g": float(row["prediction_g"]),
            }
            for row in rows
        ]

    _seed_all(SEED + 1000)
    train_transform, eval_transform = _build_transforms(transforms)
    train_loader = DataLoader(
        WeightViewDataset(train_rows, asset_root, train_transform),
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=workers,
        pin_memory=device.type == "cuda",
        persistent_workers=workers > 0,
    )
    validation_loader = DataLoader(
        WeightViewDataset(validation_rows, asset_root, eval_transform),
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=workers,
        pin_memory=device.type == "cuda",
        persistent_workers=workers > 0,
    )

    model = _build_model(nn, models, device)
    criterion = nn.SmoothL1Loss(beta=HUBER_BETA)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
    )
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    print("", flush=True)
    print(
        f"[6/6] FINAL TRAIN · official train 367 fruit · "
        f"fixed {final_epoch} epochs · validation은 학습에 사용하지 않음",
        flush=True,
    )
    for epoch in range(1, final_epoch + 1):
        model.train()
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
        print(
            f"  E{epoch:02d}/{final_epoch:02d} {_bar(epoch, final_epoch)} · "
            "train-only fitting",
            flush=True,
        )

    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "epoch": final_epoch,
            "model_name": MODEL_NAME,
            "seed": SEED + 1000,
            "training_policy": "OFFICIAL_TRAIN_ONLY_FIXED_EPOCH_FROM_INNER_CV",
        },
        checkpoint_path,
    )
    validation_views, _ = _infer_views(
        model,
        validation_loader,
        device=device,
        torch=torch,
        criterion=criterion,
    )
    with view_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["fruit_id", "target_g", "prediction_g"],
        )
        writer.writeheader()
        writer.writerows(validation_views)
    return validation_views


def run_rgb_multiview_v002(
    snapshot_dir: Path,
    cv_csv: Path,
    output_dir: Path,
    *,
    device_name: str | None = None,
    workers: int = 4,
    allow_cpu: bool = False,
) -> dict[str, Any]:
    torch, nn, DataLoader, models, transforms = _runtime_imports()
    snapshot_dir = Path(snapshot_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    descriptor, rows = load_weight_snapshot(snapshot_dir)
    asset_root = _verify_assets(snapshot_dir, descriptor, rows)
    assignments = _read_cv_assignments(cv_csv)

    train_rows = [row for row in rows if row.split == "train"]
    validation_rows = [row for row in rows if row.split == "validation"]
    test_count = len({row.fruit_id for row in rows if row.split == "test"})
    train_ids = {row.fruit_id for row in train_rows}
    if set(assignments) != train_ids:
        raise ValueError(
            "development CV fruit IDs must exactly match official train fruit IDs"
        )
    if not validation_rows or test_count == 0:
        raise ValueError("official validation/test must be non-empty")

    device, diagnostics = _resolve_device(
        torch,
        device_name=device_name,
        allow_cpu=allow_cpu,
    )
    _print_run_overview(
        device=device,
        diagnostics=diagnostics,
        train_count=len(train_ids),
        validation_count=len({row.fruit_id for row in validation_rows}),
        test_count=test_count,
        fold_count=len(set(assignments.values())),
        output_dir=output_dir,
        workers=workers,
    )

    all_oof_views: list[dict[str, Any]] = []
    fold_reports: list[dict[str, Any]] = []
    best_epochs: list[int] = []
    for fold in sorted(set(assignments.values())):
        fold_train_ids = {
            fruit_id for fruit_id, assigned in assignments.items()
            if assigned != fold
        }
        fold_holdout_ids = {
            fruit_id for fruit_id, assigned in assignments.items()
            if assigned == fold
        }
        fold_train_rows = [
            row for row in train_rows if row.fruit_id in fold_train_ids
        ]
        fold_holdout_rows = [
            row for row in train_rows if row.fruit_id in fold_holdout_ids
        ]
        report = _train_fold(
            fold=fold,
            train_rows=fold_train_rows,
            holdout_rows=fold_holdout_rows,
            asset_root=asset_root,
            output_dir=output_dir,
            device=device,
            workers=workers,
            torch=torch,
            nn=nn,
            DataLoader=DataLoader,
            models=models,
            transforms=transforms,
        )
        best_epochs.append(int(report["best_epoch"]))
        for row in report["holdout_view_predictions"]:
            all_oof_views.append({**row, "fold": fold})
        fold_reports.append(
            {
                key: value
                for key, value in report.items()
                if key != "holdout_view_predictions"
            }
        )

    if len(all_oof_views) != len(train_rows):
        raise ValueError(
            f"OOF view count mismatch: {len(all_oof_views)}/{len(train_rows)}"
        )

    candidate_results: list[dict[str, Any]] = []
    oof_fruits_by_method: dict[str, list[dict[str, Any]]] = {}
    for method in AGGREGATIONS:
        fruits, metrics = _evaluate_aggregation(all_oof_views, method)
        candidate_results.append(
            {
                "aggregation": method,
                "oof_metrics": metrics,
            }
        )
        oof_fruits_by_method[method] = fruits

    print("", flush=True)
    _print_header("OOF AGGREGATION 비교")
    for item in candidate_results:
        metrics = item["oof_metrics"]
        print(
            f" {item['aggregation']:<31} · "
            f"Grade err {int(metrics['grade_error_count']):3d} · "
            f"Cross {int(metrics['threshold_crossing_count']):3d} · "
            f"MAE {float(metrics['mae_g']):.3f}g · "
            f"RMSE {float(metrics['rmse_g']):.3f}g",
            flush=True,
        )

    selected = min(candidate_results, key=_candidate_key)
    selected_method = str(selected["aggregation"])
    final_epoch = int(statistics.median(best_epochs))
    print("-" * LOG_WIDTH, flush=True)
    print(
        f" 선택       {selected_method} · final epoch={final_epoch}",
        flush=True,
    )
    print("=" * LOG_WIDTH, flush=True)

    validation_views = _train_final_model(
        train_rows=train_rows,
        validation_rows=validation_rows,
        final_epoch=final_epoch,
        asset_root=asset_root,
        output_dir=output_dir,
        device=device,
        workers=workers,
        torch=torch,
        nn=nn,
        DataLoader=DataLoader,
        models=models,
        transforms=transforms,
    )
    selected_validation_fruits, selected_validation_metrics = _evaluate_aggregation(
        validation_views,
        selected_method,
    )
    mean_validation_fruits, mean_validation_metrics = _evaluate_aggregation(
        validation_views,
        "MEAN_22_VIEW",
    )

    oof_view_path = output_dir / "development_oof_view_predictions.csv"
    with oof_view_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["fruit_id", "target_g", "prediction_g", "fold"],
        )
        writer.writeheader()
        writer.writerows(all_oof_views)

    oof_fruit_path = output_dir / "development_oof_fruit_predictions.csv"
    with oof_fruit_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "aggregation",
                "fruit_id",
                "actual_weight_g",
                "predicted_weight_g",
                "view_prediction_std_g",
                "view_prediction_range_g",
                "view_count",
            ],
        )
        writer.writeheader()
        for method in AGGREGATIONS:
            for row in oof_fruits_by_method[method]:
                writer.writerow({"aggregation": method, **row})

    validation_path = output_dir / "validation_fruit_predictions.csv"
    mean_by_id = {row["fruit_id"]: row for row in mean_validation_fruits}
    with validation_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fruit_id",
                "actual_weight_g",
                "selected_aggregation",
                "selected_predicted_weight_g",
                "mean22_predicted_weight_g",
            ],
        )
        writer.writeheader()
        for row in selected_validation_fruits:
            writer.writerow(
                {
                    "fruit_id": row["fruit_id"],
                    "actual_weight_g": row["actual_weight_g"],
                    "selected_aggregation": selected_method,
                    "selected_predicted_weight_g": row["predicted_weight_g"],
                    "mean22_predicted_weight_g": mean_by_id[row["fruit_id"]][
                        "predicted_weight_g"
                    ],
                }
            )

    report = {
        "status": "WEIGHT_RGB_MULTIVIEW_V002_DEVELOPMENT_COMPLETE",
        "contract": "nongtori-weight-rgb-multiview-v002.v1",
        "model": MODEL_NAME,
        "scope": "AGGREGATION_ONLY_MODEL_ARCHITECTURE_UNCHANGED",
        "official_counts": {
            "train": len(train_ids),
            "validation": len({row.fruit_id for row in validation_rows}),
            "test_locked": test_count,
        },
        "development_policy": {
            "cv": "OFFICIAL_TRAIN_FRUIT_ID_5FOLD",
            "checkpoint_selector": CHECKPOINT_AGGREGATION,
            "checkpoint_note": (
                "Mean-22 is predeclared only for fold checkpoint selection to "
                "preserve V001 training behavior; aggregation candidates are "
                "selected from OOF fruit predictions."
            ),
            "candidate_aggregations": list(AGGREGATIONS),
            "selection_order": [
                "grade_error_count",
                "threshold_crossing_count",
                "mae_g",
                "rmse_g",
                "least_aggressive_aggregation_tiebreak",
            ],
        },
        "fold_best_epochs": best_epochs,
        "final_train_epoch": final_epoch,
        "candidate_results": candidate_results,
        "selected_aggregation": selected_method,
        "official_validation_confirmation": {
            "selected_metrics": selected_validation_metrics,
            "mean22_reference_metrics": mean_validation_metrics,
            "selection_uses_official_validation": False,
            "final_model_training_uses_official_validation": False,
        },
        "test_policy": "LOCKED_NOT_EVALUATED",
        "test_predictions_written": False,
        "artifacts": {
            "development_oof_view_predictions": str(oof_view_path),
            "development_oof_fruit_predictions": str(oof_fruit_path),
            "validation_fruit_predictions": str(validation_path),
            "final_checkpoint": str(output_dir / "final" / "final_train_only.pt"),
        },
        "folds": fold_reports,
    }
    (output_dir / "rgb_multiview_v002.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _print_header("RGB V002 결과")
    print(f" 선택 aggregation  {selected_method}", flush=True)
    print(
        f" Validation         MAE {float(selected_validation_metrics['mae_g']):.3f}g · "
        f"RMSE {float(selected_validation_metrics['rmse_g']):.3f}g · "
        f"R² {float(selected_validation_metrics['r2']):.3f} · "
        f"Grade {float(selected_validation_metrics['grade_accuracy']) * 100:.1f}%",
        flush=True,
    )
    print(
        f" Mean-22 reference  MAE {float(mean_validation_metrics['mae_g']):.3f}g · "
        f"Grade {float(mean_validation_metrics['grade_accuracy']) * 100:.1f}%",
        flush=True,
    )
    print(" Test               LOCKED · 평가/튜닝 안 함", flush=True)
    print("=" * LOG_WIDTH, flush=True)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Develop RGB 22-view fruit aggregation on official-train 5-fold "
            "OOF predictions, then confirm once on official validation"
        )
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=Path("data/snapshots/WEIGHT-DRYAD-V001"),
    )
    parser.add_argument(
        "--cv-csv",
        type=Path,
        default=Path("artifacts/weight/development-cv-v1/train_folds.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/rgb-multiview-v002"),
    )
    parser.add_argument("--device", default=None)
    parser.add_argument(
        "--allow-cpu",
        action="store_true",
        help="Allow the compute-heavy 5-fold RGB training to run on CPU intentionally.",
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    try:
        report = run_rgb_multiview_v002(
            args.snapshot_dir,
            args.cv_csv,
            args.output_dir,
            device_name=args.device,
            workers=int(args.workers),
            allow_cpu=bool(args.allow_cpu),
        )
    except (
        FileNotFoundError,
        KeyError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {"status": "WEIGHT_RGB_MULTIVIEW_V002_BLOCKED", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
