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

from .mite_field_v001 import (
    CLASS_NAMES as FIELD_CLASS_NAMES,
    MITE_LABEL,
    _ap_from_pr,
    _iou,
    evaluate_model as evaluate_field_model,
)

MODEL_NAME = "fasterrcnn_mobilenet_v3_large_fpn"
MORPH_SNAPSHOT_ID = "MITE-PUBLIC-MORPHOLOGY-V001"
FIELD_SNAPSHOT_ID = "MITE-PUBLIC-FIELD-CONTEXT-V001"
MORPH_CLASS_NAMES = ["Adult_female", "Immature", "Viable_egg"]
DEFAULT_MORPH_SNAPSHOT = Path("data/snapshots") / MORPH_SNAPSHOT_ID
DEFAULT_FIELD_SNAPSHOT = Path("data/snapshots") / FIELD_SNAPSHOT_ID
DEFAULT_OUTPUT = Path("artifacts/detector/mite-morph-transfer-v002")
DEFAULT_SEED = 20261014

EXPECTED_MORPH_SPLIT = {"train": 854, "validation": 203, "test": 192}
EXPECTED_FIELD_SPLIT = {"train": 1993, "validation": 427, "test": 424}
EXPECTED_MORPH_BOXES = 17364
EXPECTED_FIELD_BOXES = 9179

V001_VALIDATION_REFERENCE = {
    "mite_map50": 0.8536,
    "mite_map50_95": 0.6840,
    "mite_precision_at_0_5": 0.8021,
    "mite_recall_at_0_5": 0.7973,
    "macro_map50_95": 0.7057,
}


class MiteTransferError(RuntimeError):
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
        raise MiteTransferError(
            "V002 requires torch, torchvision and Pillow in the active environment."
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
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_snapshot(
    snapshot_dir: Path,
    *,
    expected_id: str,
    expected_split: dict[str, int],
    expected_boxes: int,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    snapshot_dir = Path(snapshot_dir)
    descriptor_path = snapshot_dir / "SNAPSHOT.json"
    manifest_path = snapshot_dir / "manifest.csv"
    if not descriptor_path.is_file() or not manifest_path.is_file():
        raise MiteTransferError(f"snapshot incomplete: {snapshot_dir}")

    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    if descriptor.get("snapshot_id") != expected_id:
        raise MiteTransferError(
            f"unexpected snapshot: expected {expected_id}, got {descriptor.get('snapshot_id')}"
        )
    if descriptor.get("status") != "SNAPSHOT_READY":
        raise MiteTransferError(f"snapshot not ready: {expected_id}")
    if descriptor.get("manifest_sha256") != _sha256(manifest_path):
        raise MiteTransferError(f"manifest SHA-256 mismatch: {expected_id}")

    with manifest_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["split"]] += 1
    if dict(counts) != expected_split:
        raise MiteTransferError(
            f"{expected_id} split mismatch: expected {expected_split}, got {dict(counts)}"
        )
    if sum(int(row["valid_bbox_count"]) for row in rows) != expected_boxes:
        raise MiteTransferError(f"{expected_id} bbox count mismatch")
    return descriptor, rows


def _parse_yolo(path: Path, width: int, height: int, class_count: int):
    boxes: list[list[float]] = []
    labels: list[int] = []
    if not path.is_file():
        raise MiteTransferError(f"snapshot label missing: {path}")
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        parts = raw.strip().split()
        if not parts:
            continue
        if len(parts) != 5:
            raise MiteTransferError(f"{path}:{line_no}: invalid YOLO row")
        cls_id = int(parts[0])
        if not 0 <= cls_id < class_count:
            raise MiteTransferError(f"{path}:{line_no}: class out of range")
        xc, yc, bw, bh = map(float, parts[1:])
        x1 = max(0.0, (xc - bw / 2.0) * width)
        y1 = max(0.0, (yc - bh / 2.0) * height)
        x2 = min(float(width), (xc + bw / 2.0) * width)
        y2 = min(float(height), (yc + bh / 2.0) * height)
        if x2 <= x1 or y2 <= y1:
            raise MiteTransferError(f"{path}:{line_no}: degenerate bbox")
        boxes.append([x1, y1, x2, y2])
        labels.append(cls_id + 1)
    return boxes, labels


class SnapshotDetectionDataset:
    """Pickle-safe manifest-backed dataset for both V002 stages."""

    def __init__(
        self,
        snapshot_dir: Path,
        split: str,
        *,
        expected_id: str,
        expected_split: dict[str, int],
        expected_boxes: int,
        class_names: list[str],
    ):
        self.snapshot_dir = Path(snapshot_dir)
        descriptor, rows = _load_snapshot(
            self.snapshot_dir,
            expected_id=expected_id,
            expected_split=expected_split,
            expected_boxes=expected_boxes,
        )
        self.dataset_root = Path(descriptor["dataset_root"])
        self.rows = [row for row in rows if row["split"] == split]
        self.class_names = list(class_names)
        if not self.rows:
            raise MiteTransferError(f"empty split: {expected_id}/{split}")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        try:
            import torch
            from PIL import Image
            from torchvision.transforms.functional import pil_to_tensor
        except ImportError as exc:
            raise MiteTransferError("dataset dependencies missing") from exc

        row = self.rows[index]
        image_path = self.dataset_root / Path(row["image"])
        label_path = self.snapshot_dir / "labels" / Path(row["snapshot_label"])
        warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)
        with Image.open(image_path) as pil:
            pil = pil.convert("RGB")
            width, height = pil.size
            image = pil_to_tensor(pil).float().div(255.0)

        boxes, labels = _parse_yolo(
            label_path, width, height, len(self.class_names)
        )
        box_tensor = torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4)
        target = {
            "boxes": box_tensor,
            "labels": torch.tensor(labels, dtype=torch.int64),
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


def build_model(mods, class_names: list[str]):
    model = mods["builder"](
        weights=mods["Weights"].DEFAULT,
        min_size=640,
        max_size=1024,
    )
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = mods["FastRCNNPredictor"](
        in_features, len(class_names) + 1
    )
    return model


def transferable_state_dict(state_dict: dict[str, Any]) -> dict[str, Any]:
    """Transfer all learned detector representation except class-specific predictor."""
    return {
        key: value
        for key, value in state_dict.items()
        if not key.startswith("roi_heads.box_predictor.")
    }


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
    detections.sort(reverse=True, key=lambda item: item[0])

    matched = defaultdict(set)
    tp: list[int] = []
    fp: list[int] = []
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
    recalls: list[float] = []
    precisions: list[float] = []
    for t, f in zip(tp, fp):
        cum_tp += t; cum_fp += f
        recalls.append(cum_tp / total_gt if total_gt else 0.0)
        precisions.append(cum_tp / max(1, cum_tp + cum_fp))
    return _ap_from_pr(recalls, precisions)


def evaluate_multiclass(model, loader, device, class_names: list[str]):
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
    for label, name in enumerate(class_names, start=1):
        aps = {
            f"ap{int(round(iou * 100))}": _class_ap(records, label, iou)
            for iou in ious
        }
        per_class[name] = {
            "map50": aps["ap50"],
            "map50_95": sum(aps.values()) / len(aps),
            "per_iou_ap": aps,
        }
    return {
        "macro_map50": sum(v["map50"] for v in per_class.values()) / len(per_class),
        "macro_map50_95": sum(v["map50_95"] for v in per_class.values()) / len(per_class),
        "per_class": per_class,
        "image_count": len(records),
        "gt_box_count": sum(len(row["gt_boxes"]) for row in records),
    }


def _seed_everything(torch, seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _make_loader(mods, dataset, *, batch_size: int, shuffle: bool, workers: int, device):
    return mods["DataLoader"](
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=workers,
        collate_fn=collate_fn,
        pin_memory=device.type == "cuda",
    )


def _train_epoch(model, loader, optimizer, device) -> float:
    model.train()
    loss_sum = 0.0
    batches = 0
    for images, targets in loader:
        images = [image.to(device) for image in images]
        targets = [
            {key: value.to(device) for key, value in target.items()}
            for target in targets
        ]
        losses = model(images, targets)
        loss = sum(losses.values())
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        loss_sum += float(loss.detach().cpu())
        batches += 1
    return loss_sum / max(1, batches)


def pretrain_morphology(args, mods, device) -> Path:
    torch = mods["torch"]
    train_ds = SnapshotDetectionDataset(
        args.morph_snapshot, "train",
        expected_id=MORPH_SNAPSHOT_ID,
        expected_split=EXPECTED_MORPH_SPLIT,
        expected_boxes=EXPECTED_MORPH_BOXES,
        class_names=MORPH_CLASS_NAMES,
    )
    val_ds = SnapshotDetectionDataset(
        args.morph_snapshot, "validation",
        expected_id=MORPH_SNAPSHOT_ID,
        expected_split=EXPECTED_MORPH_SPLIT,
        expected_boxes=EXPECTED_MORPH_BOXES,
        class_names=MORPH_CLASS_NAMES,
    )
    train_loader = _make_loader(
        mods, train_ds, batch_size=args.batch_size, shuffle=True,
        workers=args.workers, device=device,
    )
    val_loader = _make_loader(
        mods, val_ds, batch_size=1, shuffle=False,
        workers=args.workers, device=device,
    )

    stage_dir = args.output / "morphology"
    stage_dir.mkdir(parents=True, exist_ok=True)
    model = build_model(mods, MORPH_CLASS_NAMES).to(device)
    optimizer = torch.optim.SGD(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.morph_lr, momentum=0.9, weight_decay=0.0005,
    )
    scheduler = torch.optim.lr_scheduler.StepLR(
        optimizer, step_size=args.morph_lr_step, gamma=0.1
    )
    best_key = (-1.0, -1.0)
    best_epoch = 0
    stale = 0

    print(
        f"[MORPH] train={len(train_ds)} val={len(val_ds)} test=LOCKED "
        f"classes={','.join(MORPH_CLASS_NAMES)}",
        flush=True,
    )
    for epoch in range(1, args.morph_epochs + 1):
        loss = _train_epoch(model, train_loader, optimizer, device)
        scheduler.step()
        metrics = evaluate_multiclass(model, val_loader, device, MORPH_CLASS_NAMES)
        key = (metrics["macro_map50_95"], metrics["macro_map50"])
        if key > best_key:
            best_key = key
            best_epoch = epoch
            stale = 0
            torch.save({
                "stage": "morphology_pretrain",
                "model_name": MODEL_NAME,
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "validation_metrics": metrics,
                "snapshot_id": MORPH_SNAPSHOT_ID,
                "class_names": MORPH_CLASS_NAMES,
            }, stage_dir / "best.pt")
        else:
            stale += 1

        print(
            f"M{epoch:02d}/{args.morph_epochs} | loss {loss:.4f} | "
            f"macro AP50 {metrics['macro_map50']:.4f} | "
            f"AP50-95 {metrics['macro_map50_95']:.4f} | "
            f"best M{best_epoch:02d} | stale {stale}/{args.patience}",
            flush=True,
        )
        if stale >= args.patience:
            print("[MORPH] EARLY_STOP", flush=True)
            break

    return stage_dir / "best.pt"


def finetune_field(args, mods, device, morph_checkpoint: Path) -> Path:
    torch = mods["torch"]
    train_ds = SnapshotDetectionDataset(
        args.field_snapshot, "train",
        expected_id=FIELD_SNAPSHOT_ID,
        expected_split=EXPECTED_FIELD_SPLIT,
        expected_boxes=EXPECTED_FIELD_BOXES,
        class_names=FIELD_CLASS_NAMES,
    )
    val_ds = SnapshotDetectionDataset(
        args.field_snapshot, "validation",
        expected_id=FIELD_SNAPSHOT_ID,
        expected_split=EXPECTED_FIELD_SPLIT,
        expected_boxes=EXPECTED_FIELD_BOXES,
        class_names=FIELD_CLASS_NAMES,
    )
    train_loader = _make_loader(
        mods, train_ds, batch_size=args.batch_size, shuffle=True,
        workers=args.workers, device=device,
    )
    val_loader = _make_loader(
        mods, val_ds, batch_size=1, shuffle=False,
        workers=args.workers, device=device,
    )

    morph = torch.load(morph_checkpoint, map_location="cpu", weights_only=False)
    model = build_model(mods, FIELD_CLASS_NAMES)
    transfer = transferable_state_dict(morph["model_state_dict"])
    result = model.load_state_dict(transfer, strict=False)
    unexpected = list(result.unexpected_keys)
    missing = list(result.missing_keys)
    allowed_missing_prefix = "roi_heads.box_predictor."
    if unexpected or any(not key.startswith(allowed_missing_prefix) for key in missing):
        raise MiteTransferError(
            f"unsafe transfer state: unexpected={unexpected}, missing={missing}"
        )
    model.to(device)

    stage_dir = args.output / "field"
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "transfer-report.json").write_text(
        json.dumps({
            "source_checkpoint": str(morph_checkpoint),
            "source_epoch": morph["epoch"],
            "transferred_parameter_keys": len(transfer),
            "missing_reinitialized_keys": missing,
            "unexpected_keys": unexpected,
            "policy": "TRANSFER_ALL_EXCEPT_CLASS_SPECIFIC_BOX_PREDICTOR",
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    optimizer = torch.optim.SGD(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.field_lr, momentum=0.9, weight_decay=0.0005,
    )
    scheduler = torch.optim.lr_scheduler.StepLR(
        optimizer, step_size=args.field_lr_step, gamma=0.1
    )
    best_key = (-1.0, -1.0, -1.0)
    best_epoch = 0
    stale = 0

    print(
        f"[FIELD] transferred from morphology epoch {morph['epoch']} | "
        f"train={len(train_ds)} val={len(val_ds)} test=LOCKED",
        flush=True,
    )
    for epoch in range(1, args.field_epochs + 1):
        loss = _train_epoch(model, train_loader, optimizer, device)
        scheduler.step()
        metrics = evaluate_field_model(
            model, val_loader, device, score_threshold=args.score_threshold
        )
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
                "stage": "field_finetune",
                "model_name": MODEL_NAME,
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "validation_metrics": metrics,
                "field_snapshot_id": FIELD_SNAPSHOT_ID,
                "morph_snapshot_id": MORPH_SNAPSHOT_ID,
                "morph_checkpoint_epoch": morph["epoch"],
                "class_names": FIELD_CLASS_NAMES,
            }, stage_dir / "best.pt")
        else:
            stale += 1

        delta = metrics["mite_map50_95"] - V001_VALIDATION_REFERENCE["mite_map50_95"]
        print(
            f"F{epoch:02d}/{args.field_epochs} | loss {loss:.4f} | "
            f"mite AP50 {metrics['mite_map50']:.4f} | "
            f"AP50-95 {metrics['mite_map50_95']:.4f} | "
            f"P {metrics['mite_precision_at_0_5']:.4f} | "
            f"R {metrics['mite_recall_at_0_5']:.4f} | "
            f"macro {metrics['macro_map50_95']:.4f} | "
            f"vsV001 {delta:+.4f} | best F{best_epoch:02d} | "
            f"stale {stale}/{args.patience}",
            flush=True,
        )
        if stale >= args.patience:
            print("[FIELD] EARLY_STOP", flush=True)
            break

    return stage_dir / "best.pt"


def train(args) -> int:
    mods = _lazy_imports()
    torch = mods["torch"]
    if not torch.cuda.is_available() and not args.allow_cpu:
        raise MiteTransferError(
            "CUDA unavailable; activate nongtori_gpu or pass --allow-cpu intentionally."
        )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _seed_everything(torch, args.seed)
    args.output.mkdir(parents=True, exist_ok=True)

    print(
        f"MITE MORPHOLOGY TRANSFER V002 | model={MODEL_NAME} | device={device}",
        flush=True,
    )
    print(
        "policy=morphology validation pretrain -> field validation finetune | "
        "all public test splits LOCKED",
        flush=True,
    )
    start = time.time()
    morph_checkpoint = pretrain_morphology(args, mods, device)
    field_checkpoint = finetune_field(args, mods, device, morph_checkpoint)

    morph = torch.load(morph_checkpoint, map_location="cpu", weights_only=False)
    field = torch.load(field_checkpoint, map_location="cpu", weights_only=False)
    field_metrics = field["validation_metrics"]
    delta = {
        key: field_metrics[key] - V001_VALIDATION_REFERENCE[key]
        for key in V001_VALIDATION_REFERENCE
        if key in field_metrics
    }
    summary = {
        "status": "MITE_MORPHOLOGY_TRANSFER_V002_TRAINED",
        "test_status": "LOCKED_NOT_EVALUATED",
        "selection_split": "field_validation",
        "selection_metric": "mite_map50_95",
        "morphology": {
            "snapshot_id": MORPH_SNAPSHOT_ID,
            "best_epoch": morph["epoch"],
            "validation_metrics": morph["validation_metrics"],
            "checkpoint": str(morph_checkpoint),
        },
        "field": {
            "snapshot_id": FIELD_SNAPSHOT_ID,
            "best_epoch": field["epoch"],
            "validation_metrics": field_metrics,
            "checkpoint": str(field_checkpoint),
        },
        "v001_validation_reference": V001_VALIDATION_REFERENCE,
        "v002_minus_v001_validation": delta,
        "elapsed_sec": time.time() - start,
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"TRAINING_COMPLETE | field best F{field['epoch']:02d} | "
        f"mite AP50-95 {field_metrics['mite_map50_95']:.4f} | "
        f"vsV001 {delta.get('mite_map50_95', 0.0):+.4f} | test=LOCKED",
        flush=True,
    )
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Nongtori morphology-transfer mite detector V002"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("train")
    p.add_argument("--morph-snapshot", type=Path, default=DEFAULT_MORPH_SNAPSHOT)
    p.add_argument("--field-snapshot", type=Path, default=DEFAULT_FIELD_SNAPSHOT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--morph-epochs", type=int, default=15)
    p.add_argument("--field-epochs", type=int, default=20)
    p.add_argument("--morph-lr", type=float, default=0.005)
    p.add_argument("--field-lr", type=float, default=0.0025)
    p.add_argument("--morph-lr-step", type=int, default=6)
    p.add_argument("--field-lr-step", type=int, default=8)
    p.add_argument("--patience", type=int, default=5)
    p.add_argument("--score-threshold", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--allow-cpu", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return train(args)
    except MiteTransferError as exc:
        print(json.dumps({
            "status": "MITE_MORPHOLOGY_TRANSFER_V002_BLOCKED",
            "error": str(exc),
        }, ensure_ascii=False, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
