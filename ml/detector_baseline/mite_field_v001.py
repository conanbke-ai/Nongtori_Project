from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import time
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any

MODEL_NAME = "fasterrcnn_mobilenet_v3_large_fpn"
SNAPSHOT_ID = "MITE-PUBLIC-FIELD-CONTEXT-V001"
DEFAULT_SNAPSHOT = Path("data/snapshots") / SNAPSHOT_ID
DEFAULT_OUTPUT = Path("artifacts/detector/mite-field-context-v001")
DEFAULT_SEED = 20261013
CLASS_NAMES = ["Tetranychus Urticae", "dry", "gray_mold", "scorch"]
MITE_LABEL = 1  # Faster R-CNN foreground labels are 1-based.


class MiteDetectorBaselineError(RuntimeError):
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
        from torchvision.transforms.functional import pil_to_tensor
    except ImportError as exc:
        raise MiteDetectorBaselineError(
            "Mite detector baseline requires torch, torchvision and Pillow."
        ) from exc
    return {
        "torch": torch,
        "Image": Image,
        "DataLoader": DataLoader,
        "Weights": FasterRCNN_MobileNet_V3_Large_FPN_Weights,
        "builder": fasterrcnn_mobilenet_v3_large_fpn,
        "FastRCNNPredictor": FastRCNNPredictor,
        "pil_to_tensor": pil_to_tensor,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_snapshot(snapshot_dir: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    snapshot_dir = Path(snapshot_dir)
    descriptor_path = snapshot_dir / "SNAPSHOT.json"
    manifest_path = snapshot_dir / "manifest.csv"
    if not descriptor_path.is_file() or not manifest_path.is_file():
        raise MiteDetectorBaselineError(f"snapshot incomplete: {snapshot_dir}")

    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    if descriptor.get("snapshot_id") != SNAPSHOT_ID:
        raise MiteDetectorBaselineError(
            f"unexpected snapshot: {descriptor.get('snapshot_id')}"
        )
    if descriptor.get("status") != "SNAPSHOT_READY":
        raise MiteDetectorBaselineError("snapshot is not ready")
    if descriptor.get("manifest_sha256") != _sha256(manifest_path):
        raise MiteDetectorBaselineError("snapshot manifest SHA-256 mismatch")

    with manifest_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    expected = {"train": 1993, "validation": 427, "test": 424}
    observed = defaultdict(int)
    for row in rows:
        observed[row["split"]] += 1
    if dict(observed) != expected:
        raise MiteDetectorBaselineError(
            f"frozen split mismatch: expected {expected}, got {dict(observed)}"
        )
    if sum(int(row["valid_bbox_count"]) for row in rows) != 9179:
        raise MiteDetectorBaselineError("frozen bbox count mismatch")
    return descriptor, rows


def _parse_yolo_multiclass(path: Path, width: int, height: int):
    boxes: list[list[float]] = []
    labels: list[int] = []
    if not path.is_file():
        raise MiteDetectorBaselineError(f"snapshot label missing: {path}")
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            raise MiteDetectorBaselineError(f"{path}:{line_no}: invalid YOLO row")
        cls, xc, yc, bw, bh = parts
        cls_id = int(cls)
        if cls_id < 0 or cls_id >= len(CLASS_NAMES):
            raise MiteDetectorBaselineError(f"{path}:{line_no}: class out of range")
        xc, yc, bw, bh = map(float, (xc, yc, bw, bh))
        x1 = max(0.0, (xc - bw / 2) * width)
        y1 = max(0.0, (yc - bh / 2) * height)
        x2 = min(float(width), (xc + bw / 2) * width)
        y2 = min(float(height), (yc + bh / 2) * height)
        if x2 <= x1 or y2 <= y1:
            raise MiteDetectorBaselineError(f"{path}:{line_no}: degenerate bbox")
        boxes.append([x1, y1, x2, y2])
        labels.append(cls_id + 1)
    return boxes, labels


class MiteFieldContextDataset:
    """Pickle-safe manifest-backed dataset for Windows workers."""

    def __init__(self, snapshot_dir: Path, split: str):
        self.snapshot_dir = Path(snapshot_dir)
        descriptor, rows = load_snapshot(self.snapshot_dir)
        self.dataset_root = Path(descriptor["dataset_root"])
        self.rows = [row for row in rows if row["split"] == split]
        self.split = split
        if not self.rows:
            raise MiteDetectorBaselineError(f"empty split: {split}")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        try:
            import torch
            from PIL import Image
            from torchvision.transforms.functional import pil_to_tensor
        except ImportError as exc:
            raise MiteDetectorBaselineError("dataset dependencies missing") from exc

        row = self.rows[index]
        image_path = self.dataset_root / Path(row["image"])
        label_path = self.snapshot_dir / "labels" / Path(row["snapshot_label"])
        warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)
        with Image.open(image_path) as pil:
            pil = pil.convert("RGB")
            width, height = pil.size
            image = pil_to_tensor(pil).float().div(255.0)

        boxes, labels = _parse_yolo_multiclass(label_path, width, height)
        box_tensor = torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4)
        label_tensor = torch.tensor(labels, dtype=torch.int64)
        target = {
            "boxes": box_tensor,
            "labels": label_tensor,
            "image_id": torch.tensor([index], dtype=torch.int64),
            "area": (
                (box_tensor[:, 2] - box_tensor[:, 0])
                * (box_tensor[:, 3] - box_tensor[:, 1])
            ),
            "iscrowd": torch.zeros((len(boxes),), dtype=torch.int64),
        }
        return image, target


def collate_fn(batch):
    return tuple(zip(*batch))


def build_model(mods):
    model = mods["builder"](
        weights=mods["Weights"].DEFAULT,
        min_size=640,
        max_size=1024,
    )
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = mods["FastRCNNPredictor"](
        in_features, len(CLASS_NAMES) + 1
    )
    return model


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _ap_from_pr(recalls, precisions) -> float:
    if not recalls:
        return 0.0
    return sum(
        max([p for r2, p in zip(recalls, precisions) if r2 >= r], default=0.0)
        for r in (i / 100 for i in range(101))
    ) / 101.0


def _class_ap(records, class_label: int, iou_threshold: float) -> float:
    total_gt = sum(
        sum(1 for label in row["gt_labels"] if label == class_label)
        for row in records
    )
    detections = []
    for image_index, row in enumerate(records):
        for box, score, label in zip(
            row["pred_boxes"], row["scores"], row["pred_labels"]
        ):
            if label == class_label:
                detections.append((float(score), image_index, box))
    detections.sort(reverse=True, key=lambda x: x[0])

    matched = defaultdict(set)
    tp, fp = [], []
    for _, image_index, box in detections:
        row = records[image_index]
        candidates = [
            (idx, gt)
            for idx, (gt, label) in enumerate(zip(row["gt_boxes"], row["gt_labels"]))
            if label == class_label and idx not in matched[image_index]
        ]
        if not candidates:
            tp.append(0); fp.append(1); continue
        best_idx, best_iou = -1, -1.0
        for idx, gt in candidates:
            value = _iou(box, gt)
            if value > best_iou:
                best_idx, best_iou = idx, value
        if best_iou >= iou_threshold:
            matched[image_index].add(best_idx)
            tp.append(1); fp.append(0)
        else:
            tp.append(0); fp.append(1)

    cum_tp = cum_fp = 0
    recalls, precisions = [], []
    for t, f in zip(tp, fp):
        cum_tp += t; cum_fp += f
        recalls.append(cum_tp / total_gt if total_gt else 0.0)
        precisions.append(cum_tp / max(1, cum_tp + cum_fp))
    return _ap_from_pr(recalls, precisions)


def evaluate_model(model, loader, device, score_threshold=0.5):
    torch = _lazy_imports()["torch"]
    model.eval()
    records = []
    with torch.inference_mode():
        for images, targets in loader:
            outputs = model([image.to(device) for image in images])
            for output, target in zip(outputs, targets):
                records.append({
                    "pred_boxes": output["boxes"].detach().cpu().tolist(),
                    "scores": output["scores"].detach().cpu().tolist(),
                    "pred_labels": output["labels"].detach().cpu().tolist(),
                    "gt_boxes": target["boxes"].detach().cpu().tolist(),
                    "gt_labels": target["labels"].detach().cpu().tolist(),
                })

    ious = [0.50 + 0.05 * i for i in range(10)]
    per_class = {}
    for label, name in enumerate(CLASS_NAMES, start=1):
        aps = {f"ap{int(iou*100)}": _class_ap(records, label, iou) for iou in ious}
        per_class[name] = {
            "map50": aps["ap50"],
            "map50_95": sum(aps.values()) / len(aps),
            "per_iou_ap": aps,
        }

    # Operational P/R for the mite class at fixed score and IoU=0.5.
    tp = fp = fn = 0
    for row in records:
        gt_indices = [
            i for i, label in enumerate(row["gt_labels"]) if label == MITE_LABEL
        ]
        used = set()
        detections = [
            (box, score)
            for box, score, label in zip(
                row["pred_boxes"], row["scores"], row["pred_labels"]
            )
            if label == MITE_LABEL and score >= score_threshold
        ]
        for box, _ in detections:
            best_idx, best_iou = -1, -1.0
            for idx in gt_indices:
                if idx in used:
                    continue
                value = _iou(box, row["gt_boxes"][idx])
                if value > best_iou:
                    best_idx, best_iou = idx, value
            if best_iou >= 0.5:
                used.add(best_idx); tp += 1
            else:
                fp += 1
        fn += len(gt_indices) - len(used)

    macro50 = sum(v["map50"] for v in per_class.values()) / len(per_class)
    macro5095 = sum(v["map50_95"] for v in per_class.values()) / len(per_class)
    return {
        "mite_map50": per_class[CLASS_NAMES[0]]["map50"],
        "mite_map50_95": per_class[CLASS_NAMES[0]]["map50_95"],
        "mite_precision_at_0_5": tp / max(1, tp + fp),
        "mite_recall_at_0_5": tp / max(1, tp + fn),
        "macro_map50": macro50,
        "macro_map50_95": macro5095,
        "per_class": per_class,
        "score_threshold": score_threshold,
        "image_count": len(records),
        "gt_box_count": sum(len(r["gt_boxes"]) for r in records),
    }


def _seed_everything(torch, seed):
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def train(args) -> int:
    mods = _lazy_imports()
    torch, DataLoader = mods["torch"], mods["DataLoader"]
    descriptor, _ = load_snapshot(args.snapshot)

    if not torch.cuda.is_available() and not args.allow_cpu:
        raise MiteDetectorBaselineError(
            "CUDA unavailable; pass --allow-cpu only intentionally."
        )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _seed_everything(torch, args.seed)

    train_ds = MiteFieldContextDataset(args.snapshot, "train")
    val_ds = MiteFieldContextDataset(args.snapshot, "validation")
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
    manifest_sha = descriptor["manifest_sha256"]
    best_key = (-1.0, -1.0, -1.0)
    best_epoch = 0
    stale = 0
    start = time.time()

    def log(message):
        print(message, flush=True)
        with run_log.open("a", encoding="utf-8") as f:
            f.write(message + "\n")

    log(
        f"MITE FIELD DETECTOR V001 | model={MODEL_NAME} | device={device} | "
        f"train={len(train_ds)} val={len(val_ds)} test=LOCKED"
    )
    log(
        f"selection=mite_mAP50-95>mite_mAP50>mite_recall | "
        f"classes={','.join(CLASS_NAMES)}"
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
        metrics = evaluate_model(model, val_loader, device, args.score_threshold)
        row = {
            "epoch": epoch,
            "train_loss": loss_sum / max(1, batches),
            "lr": optimizer.param_groups[0]["lr"],
            "validation": metrics,
            "elapsed_sec": time.time() - epoch_start,
        }
        with metrics_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

        key = (
            metrics["mite_map50_95"],
            metrics["mite_map50"],
            metrics["mite_recall_at_0_5"],
        )
        if key > best_key:
            best_key = key
            best_epoch = epoch
            stale = 0
            torch.save({
                "model_name": MODEL_NAME,
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "validation_metrics": metrics,
                "manifest_sha256": manifest_sha,
                "snapshot_id": SNAPSHOT_ID,
                "class_names": CLASS_NAMES,
                "seed": args.seed,
            }, args.output / "best.pt")
        else:
            stale += 1

        log(
            f"E{epoch:02d}/{args.epochs} | "
            f"loss {row['train_loss']:.4f} | "
            f"mite AP50 {metrics['mite_map50']:.4f} | "
            f"AP50-95 {metrics['mite_map50_95']:.4f} | "
            f"P {metrics['mite_precision_at_0_5']:.4f} | "
            f"R {metrics['mite_recall_at_0_5']:.4f} | "
            f"macro {metrics['macro_map50_95']:.4f} | "
            f"best E{best_epoch:02d} | stale {stale}/{args.patience}"
        )
        if stale >= args.patience:
            log("EARLY_STOP validation metric did not improve")
            break

    checkpoint = torch.load(args.output / "best.pt", map_location="cpu", weights_only=False)
    summary = {
        "status": "MITE_FIELD_DETECTOR_V001_TRAINED",
        "snapshot_id": SNAPSHOT_ID,
        "selection_split": "validation",
        "selection_metric": "mite_map50_95",
        "test_status": "LOCKED_NOT_EVALUATED",
        "best_epoch": checkpoint["epoch"],
        "validation_metrics": checkpoint["validation_metrics"],
        "manifest_sha256": manifest_sha,
        "elapsed_sec": time.time() - start,
        "checkpoint": str(args.output / "best.pt"),
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(
        f"TRAINING_COMPLETE best_epoch={best_epoch} "
        f"mite_mAP50-95={best_key[0]:.4f} test=LOCKED"
    )
    return 0


def evaluate_test(args) -> int:
    mods = _lazy_imports()
    torch, DataLoader = mods["torch"], mods["DataLoader"]
    descriptor, _ = load_snapshot(args.snapshot)

    if not args.checkpoint.is_file():
        raise MiteDetectorBaselineError(f"checkpoint missing: {args.checkpoint}")
    if not torch.cuda.is_available() and not args.allow_cpu:
        raise MiteDetectorBaselineError("CUDA unavailable")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    if checkpoint.get("manifest_sha256") != descriptor["manifest_sha256"]:
        raise MiteDetectorBaselineError("checkpoint/snapshot provenance mismatch")

    ds = MiteFieldContextDataset(args.snapshot, "test")
    loader = DataLoader(
        ds, batch_size=1, shuffle=False, num_workers=args.workers,
        collate_fn=collate_fn, pin_memory=device.type == "cuda",
    )
    model = build_model(mods)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    metrics = evaluate_model(model, loader, device, args.score_threshold)
    payload = {
        "status": "MITE_FIELD_DETECTOR_V001_TEST_EVALUATED",
        "selection_prohibited": True,
        "checkpoint_epoch": checkpoint["epoch"],
        "snapshot_id": SNAPSHOT_ID,
        "test_metrics": metrics,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "test-metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Nongtori mite field detector V001")
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
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
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_OUTPUT / "best.pt")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return train(args) if args.command == "train" else evaluate_test(args)
    except MiteDetectorBaselineError as exc:
        print(json.dumps({
            "status": "MITE_FIELD_DETECTOR_V001_BLOCKED",
            "error": str(exc),
        }, ensure_ascii=False, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
