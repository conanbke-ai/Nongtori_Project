from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import time
from pathlib import Path
from typing import Any

MODEL_NAME = "fasterrcnn_mobilenet_v3_large_fpn"
DEFAULT_DATA_ROOT = Path("data/external/DATA-RIP-001/1/materialized")
DEFAULT_AUDIT = Path("data/audit/strawberry-detector-v001/detector-data-audit.json")
DEFAULT_OUTPUT = Path("artifacts/detector/fasterrcnn-v001")
DEFAULT_SEED = 20261013


class DetectorBaselineError(RuntimeError):
    pass


def _lazy_imports():
    try:
        import torch
        from PIL import Image
        from torch.utils.data import DataLoader
        from torchvision.models.detection import (
            FasterRCNN_MobileNet_V3_Large_FPN_Weights,
            fasterrcnn_mobilenet_v3_large_fpn,
        )
        from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
        from torchvision.ops import box_iou
        from torchvision.transforms.functional import pil_to_tensor
    except ImportError as exc:
        raise DetectorBaselineError(
            "Detector baseline requires torch, torchvision and Pillow in the active "
            "environment. Install matching CUDA builds before training."
        ) from exc
    return {
        "torch": torch,
        "Image": Image,
        "DataLoader": DataLoader,
        "Weights": FasterRCNN_MobileNet_V3_Large_FPN_Weights,
        "builder": fasterrcnn_mobilenet_v3_large_fpn,
        "FastRCNNPredictor": FastRCNNPredictor,
        "box_iou": box_iou,
        "pil_to_tensor": pil_to_tensor,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_audit(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DetectorBaselineError(f"detector audit missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "STRAWBERRY_DETECTOR_DATA_READY":
        raise DetectorBaselineError(
            f"detector audit is not training-ready: {payload.get('status')}"
        )
    return payload


def _image_files(root: Path, split: str) -> list[Path]:
    folder = root / "images" / split
    if not folder.is_dir():
        raise DetectorBaselineError(f"image split missing: {folder}")
    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    if not files:
        raise DetectorBaselineError(f"no images in split: {split}")
    return files


def _parse_yolo(label_path: Path, width: int, height: int) -> list[list[float]]:
    boxes: list[list[float]] = []
    if not label_path.is_file():
        raise DetectorBaselineError(f"label missing: {label_path}")
    for line_no, raw in enumerate(label_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            raise DetectorBaselineError(f"{label_path}:{line_no}: invalid YOLO row")
        _, xc, yc, bw, bh = parts
        xc, yc, bw, bh = map(float, (xc, yc, bw, bh))
        x1 = max(0.0, (xc - bw / 2.0) * width)
        y1 = max(0.0, (yc - bh / 2.0) * height)
        x2 = min(float(width), (xc + bw / 2.0) * width)
        y2 = min(float(height), (yc + bh / 2.0) * height)
        if x2 <= x1 or y2 <= y1:
            raise DetectorBaselineError(f"{label_path}:{line_no}: degenerate bbox")
        boxes.append([x1, y1, x2, y2])
    return boxes


class StrawberryDetectionDataset:
    """Pickle-safe dataset for Windows spawn-based DataLoader workers."""

    def __init__(self, root: Path, split: str):
        self.root = Path(root)
        self.split = split
        self.images = _image_files(self.root, split)

    def __len__(self):
        return len(self.images)

    def __getitem__(self, index):
        try:
            import torch
            from PIL import Image
            from torchvision.transforms.functional import pil_to_tensor
        except ImportError as exc:
            raise DetectorBaselineError(
                "Dataset loading requires torch, torchvision and Pillow."
            ) from exc

        image_path = self.images[index]
        label_path = (
            self.root / "labels" / self.split / f"{image_path.stem}.txt"
        )
        with Image.open(image_path) as pil:
            pil = pil.convert("RGB")
            width, height = pil.size
            image = pil_to_tensor(pil).float().div(255.0)

        boxes = _parse_yolo(label_path, width, height)
        box_tensor = torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4)
        target = {
            "boxes": box_tensor,
            "labels": torch.ones((len(boxes),), dtype=torch.int64),
            "image_id": torch.tensor([index], dtype=torch.int64),
            "area": (
                (box_tensor[:, 2] - box_tensor[:, 0])
                * (box_tensor[:, 3] - box_tensor[:, 1])
            ),
            "iscrowd": torch.zeros((len(boxes),), dtype=torch.int64),
        }
        return image, target


def build_dataset_class(mods):
    # Kept as a compatibility seam for train/eval construction.
    # The returned class is module-level so Windows multiprocessing can pickle it.
    return StrawberryDetectionDataset


def collate_fn(batch):
    return tuple(zip(*batch))


def build_model(mods):
    weights = mods["Weights"].DEFAULT
    model = mods["builder"](
        weights=weights,
        min_size=640,
        max_size=1024,
    )
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = mods["FastRCNNPredictor"](in_features, 2)
    return model


def _ap_from_pr(recalls: list[float], precisions: list[float]) -> float:
    if not recalls:
        return 0.0
    ap = 0.0
    for r in [i / 100.0 for i in range(101)]:
        candidates = [p for rr, p in zip(recalls, precisions) if rr >= r]
        ap += max(candidates) if candidates else 0.0
    return ap / 101.0


def _evaluate_threshold(records, iou_threshold: float) -> dict[str, float]:
    total_gt = sum(len(item["gt_boxes"]) for item in records)
    detections = []
    for image_index, item in enumerate(records):
        for box, score in zip(item["pred_boxes"], item["scores"]):
            detections.append((float(score), image_index, box))
    detections.sort(key=lambda row: row[0], reverse=True)

    matched = {i: set() for i in range(len(records))}
    tp: list[int] = []
    fp: list[int] = []

    for score, image_index, pred_box in detections:
        gt_boxes = records[image_index]["gt_boxes"]
        if not gt_boxes:
            tp.append(0); fp.append(1); continue

        best_iou = -1.0
        best_idx = -1
        px1, py1, px2, py2 = pred_box
        p_area = max(0.0, px2 - px1) * max(0.0, py2 - py1)
        for idx, gt in enumerate(gt_boxes):
            if idx in matched[image_index]:
                continue
            gx1, gy1, gx2, gy2 = gt
            ix1, iy1 = max(px1, gx1), max(py1, gy1)
            ix2, iy2 = min(px2, gx2), min(py2, gy2)
            iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
            inter = iw * ih
            g_area = max(0.0, gx2 - gx1) * max(0.0, gy2 - gy1)
            union = p_area + g_area - inter
            iou = inter / union if union > 0 else 0.0
            if iou > best_iou:
                best_iou, best_idx = iou, idx

        if best_iou >= iou_threshold and best_idx >= 0:
            matched[image_index].add(best_idx)
            tp.append(1); fp.append(0)
        else:
            tp.append(0); fp.append(1)

    cum_tp = 0
    cum_fp = 0
    recalls: list[float] = []
    precisions: list[float] = []
    for t, f in zip(tp, fp):
        cum_tp += t; cum_fp += f
        recalls.append(cum_tp / total_gt if total_gt else 0.0)
        precisions.append(cum_tp / max(1, cum_tp + cum_fp))

    return {
        "ap": _ap_from_pr(recalls, precisions),
        "recall_all_scores": recalls[-1] if recalls else 0.0,
    }


def evaluate_model(model, loader, device, score_threshold: float = 0.5):
    torch = _lazy_imports()["torch"]
    model.eval()
    records = []
    score_tp = score_fp = score_fn = 0

    with torch.inference_mode():
        for images, targets in loader:
            images = [img.to(device) for img in images]
            outputs = model(images)
            for output, target in zip(outputs, targets):
                pred_boxes = output["boxes"].detach().cpu().tolist()
                scores = output["scores"].detach().cpu().tolist()
                gt_boxes = target["boxes"].detach().cpu().tolist()
                records.append({
                    "pred_boxes": pred_boxes,
                    "scores": scores,
                    "gt_boxes": gt_boxes,
                })

                selected = [
                    (box, score)
                    for box, score in zip(pred_boxes, scores)
                    if score >= score_threshold
                ]
                used = set()
                for box, _ in selected:
                    px1, py1, px2, py2 = box
                    p_area = max(0.0, px2-px1) * max(0.0, py2-py1)
                    best_iou, best_idx = -1.0, -1
                    for idx, gt in enumerate(gt_boxes):
                        if idx in used:
                            continue
                        gx1, gy1, gx2, gy2 = gt
                        ix1, iy1 = max(px1,gx1), max(py1,gy1)
                        ix2, iy2 = min(px2,gx2), min(py2,gy2)
                        inter = max(0.0, ix2-ix1) * max(0.0, iy2-iy1)
                        g_area = max(0.0,gx2-gx1) * max(0.0,gy2-gy1)
                        union = p_area + g_area - inter
                        iou = inter / union if union > 0 else 0.0
                        if iou > best_iou:
                            best_iou, best_idx = iou, idx
                    if best_iou >= 0.5 and best_idx >= 0:
                        used.add(best_idx); score_tp += 1
                    else:
                        score_fp += 1
                score_fn += max(0, len(gt_boxes) - len(used))

    thresholds = [0.50 + 0.05 * i for i in range(10)]
    aps = {}
    for threshold in thresholds:
        aps[f"ap{int(round(threshold*100))}"] = _evaluate_threshold(
            records, threshold
        )["ap"]

    precision = score_tp / max(1, score_tp + score_fp)
    recall = score_tp / max(1, score_tp + score_fn)
    return {
        "map50": aps["ap50"],
        "map50_95": sum(aps.values()) / len(aps),
        "precision_at_0_5": precision,
        "recall_at_0_5": recall,
        "score_threshold": score_threshold,
        "per_iou_ap": aps,
        "image_count": len(records),
        "gt_box_count": sum(len(r["gt_boxes"]) for r in records),
    }


def _seed_everything(torch, seed: int):
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def train(args) -> int:
    mods = _lazy_imports()
    torch = mods["torch"]
    DataLoader = mods["DataLoader"]

    audit = _load_audit(args.audit)
    expected = {"train": 172, "validation": 49, "test": 26}
    if audit.get("split_counts") != expected:
        raise DetectorBaselineError(
            f"frozen split mismatch: expected {expected}, got {audit.get('split_counts')}"
        )
    if audit.get("eligible_object_count") != 1083:
        raise DetectorBaselineError(
            f"expected 1083 eligible boxes, got {audit.get('eligible_object_count')}"
        )

    if not torch.cuda.is_available() and not args.allow_cpu:
        raise DetectorBaselineError(
            "CUDA is unavailable. Training is blocked by default; pass --allow-cpu only intentionally."
        )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _seed_everything(torch, args.seed)

    Dataset = build_dataset_class(mods)
    train_ds = Dataset(args.data_root, "train")
    val_ds = Dataset(args.data_root, "validation")
    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        num_workers=args.workers, collate_fn=collate_fn,
        pin_memory=device.type == "cuda",
    )
    val_loader = DataLoader(
        val_ds, batch_size=1, shuffle=False,
        num_workers=args.workers, collate_fn=collate_fn,
        pin_memory=device.type == "cuda",
    )

    model = build_model(mods).to(device)
    optimizer = torch.optim.SGD(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.lr, momentum=0.9, weight_decay=0.0005,
    )
    scheduler = torch.optim.lr_scheduler.StepLR(
        optimizer, step_size=args.lr_step, gamma=0.1
    )

    args.output.mkdir(parents=True, exist_ok=True)
    metrics_path = args.output / "metrics.jsonl"
    run_log = args.output / "run.log"
    audit_sha = _sha256(args.audit)

    start = time.time()
    best_key = (-1.0, -1.0, -1.0)
    best_epoch = 0
    stale = 0

    def log(message: str):
        print(message, flush=True)
        with run_log.open("a", encoding="utf-8") as f:
            f.write(message + "\n")

    log(
        f"STRAWBERRY DETECTOR V001 | model={MODEL_NAME} | device={device} | "
        f"train={len(train_ds)} val={len(val_ds)} test=LOCKED"
    )
    log(
        f"torch={torch.__version__} cuda={torch.version.cuda} "
        f"gpu={torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'}"
    )

    for epoch in range(1, args.epochs + 1):
        model.train()
        loss_sum = 0.0
        batches = 0
        epoch_start = time.time()

        for images, targets in train_loader:
            images = [img.to(device) for img in images]
            targets = [
                {k: v.to(device) for k, v in target.items()}
                for target in targets
            ]
            losses = model(images, targets)
            loss = sum(losses.values())
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.detach().cpu())
            batches += 1

        scheduler.step()
        val_metrics = evaluate_model(
            model, val_loader, device, score_threshold=args.score_threshold
        )
        row = {
            "epoch": epoch,
            "train_loss": loss_sum / max(1, batches),
            "lr": optimizer.param_groups[0]["lr"],
            "validation": val_metrics,
            "elapsed_sec": time.time() - epoch_start,
        }
        with metrics_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

        key = (
            val_metrics["map50_95"],
            val_metrics["map50"],
            val_metrics["recall_at_0_5"],
        )
        improved = key > best_key
        if improved:
            best_key = key
            best_epoch = epoch
            stale = 0
            torch.save(
                {
                    "model_name": MODEL_NAME,
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "validation_metrics": val_metrics,
                    "audit_sha256": audit_sha,
                    "seed": args.seed,
                    "split_counts": expected,
                    "class_names": ["background", "strawberry"],
                    "min_size": 640,
                    "max_size": 1024,
                },
                args.output / "best.pt",
            )
        else:
            stale += 1

        log(
            f"EPOCH {epoch:02d}/{args.epochs} "
            f"loss={row['train_loss']:.4f} "
            f"mAP50={val_metrics['map50']:.4f} "
            f"mAP50-95={val_metrics['map50_95']:.4f} "
            f"P={val_metrics['precision_at_0_5']:.4f} "
            f"R={val_metrics['recall_at_0_5']:.4f} "
            f"best={best_epoch:02d} stale={stale}/{args.patience}"
        )

        if stale >= args.patience:
            log("EARLY_STOP validation metric did not improve")
            break

    checkpoint = torch.load(args.output / "best.pt", map_location="cpu", weights_only=False)
    summary = {
        "status": "STRAWBERRY_DETECTOR_V001_TRAINED",
        "model_name": MODEL_NAME,
        "selection_split": "validation",
        "test_status": "LOCKED_NOT_EVALUATED",
        "best_epoch": checkpoint["epoch"],
        "validation_metrics": checkpoint["validation_metrics"],
        "data_audit_sha256": audit_sha,
        "split_counts": expected,
        "eligible_object_count": 1083,
        "elapsed_sec": time.time() - start,
        "checkpoint": str(args.output / "best.pt"),
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(
        f"TRAINING_COMPLETE best_epoch={best_epoch} "
        f"mAP50-95={best_key[0]:.4f} test=LOCKED"
    )
    return 0


def evaluate_test(args) -> int:
    mods = _lazy_imports()
    torch = mods["torch"]
    DataLoader = mods["DataLoader"]
    audit = _load_audit(args.audit)

    if not args.checkpoint.is_file():
        raise DetectorBaselineError(f"checkpoint missing: {args.checkpoint}")
    if not torch.cuda.is_available() and not args.allow_cpu:
        raise DetectorBaselineError(
            "CUDA is unavailable. Evaluation is blocked by default; pass --allow-cpu intentionally."
        )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    if checkpoint.get("audit_sha256") != _sha256(args.audit):
        raise DetectorBaselineError("checkpoint/audit provenance mismatch")

    Dataset = build_dataset_class(mods)
    test_ds = Dataset(args.data_root, "test")
    loader = DataLoader(
        test_ds, batch_size=1, shuffle=False,
        num_workers=args.workers, collate_fn=collate_fn,
        pin_memory=device.type == "cuda",
    )
    model = build_model(mods)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)

    metrics = evaluate_model(
        model, loader, device, score_threshold=args.score_threshold
    )
    payload = {
        "status": "STRAWBERRY_DETECTOR_V001_TEST_EVALUATED",
        "selection_prohibited": True,
        "checkpoint": str(args.checkpoint),
        "checkpoint_epoch": checkpoint["epoch"],
        "test_metrics": metrics,
        "split_counts": audit["split_counts"],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "test-metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Nongtori Strawberry Detector V001 baseline"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    common.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    common.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    common.add_argument("--workers", type=int, default=4)
    common.add_argument("--score-threshold", type=float, default=0.5)
    common.add_argument("--allow-cpu", action="store_true")

    p = sub.add_parser("train", parents=[common])
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--lr", type=float, default=0.005)
    p.add_argument("--lr-step", type=int, default=8)
    p.add_argument("--patience", type=int, default=5)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)

    p = sub.add_parser("evaluate-test", parents=[common])
    p.add_argument(
        "--checkpoint", type=Path,
        default=DEFAULT_OUTPUT / "best.pt"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "train":
            return train(args)
        return evaluate_test(args)
    except DetectorBaselineError as exc:
        print(json.dumps({
            "status": "STRAWBERRY_DETECTOR_V001_BLOCKED",
            "error": str(exc),
        }, ensure_ascii=False, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
