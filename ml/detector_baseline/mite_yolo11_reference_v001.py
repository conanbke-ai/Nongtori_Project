from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

SNAPSHOT_ID = "MITE-PUBLIC-MORPHOLOGY-V001"
DEFAULT_SNAPSHOT = Path("data/snapshots") / SNAPSHOT_ID
DEFAULT_OUTPUT = Path("artifacts/detector/mite-yolo11-reference-v001")
CLASS_NAMES = ["Adult_female", "Immature", "Viable_egg"]

SOURCE_CONTRACT = {
    "project": "miteVision",
    "reference_version": 210,
    "architecture": "YOLO11-Large",
    "weights": "yolo11l.pt",
    "epochs": 100,
    "patience": 25,
    "imgsz": 1024,
    "batch": 16,
    "seed": 42,
    "synthetic_data": True,
}
EXPECTED_SPLIT = {"train": 854, "validation": 203, "test": 192}
EXPECTED_BOXES = 17364


class YoloReferenceError(RuntimeError):
    pass


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
        raise YoloReferenceError(f"snapshot incomplete: {snapshot_dir}")

    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    if descriptor.get("snapshot_id") != SNAPSHOT_ID:
        raise YoloReferenceError(
            f"unexpected snapshot: {descriptor.get('snapshot_id')}"
        )
    if descriptor.get("status") != "SNAPSHOT_READY":
        raise YoloReferenceError("snapshot is not ready")
    if descriptor.get("manifest_sha256") != _sha256(manifest_path):
        raise YoloReferenceError("snapshot manifest SHA-256 mismatch")

    with manifest_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    split_counts: dict[str, int] = {}
    for split in ("train", "validation", "test"):
        split_counts[split] = sum(row["split"] == split for row in rows)
    if split_counts != EXPECTED_SPLIT:
        raise YoloReferenceError(
            f"frozen split mismatch: expected {EXPECTED_SPLIT}, got {split_counts}"
        )
    if sum(int(row["valid_bbox_count"]) for row in rows) != EXPECTED_BOXES:
        raise YoloReferenceError("frozen bbox count mismatch")
    return descriptor, rows


def _safe_link_or_copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_file() and _sha256(destination) == _sha256(source):
            return "REUSED"
        raise YoloReferenceError(f"destination collision: {destination}")
    try:
        os.link(source, destination)
        return "HARDLINK"
    except OSError:
        shutil.copy2(source, destination)
        return "COPY"


def materialize_yolo_dataset(
    snapshot_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    descriptor, rows = load_snapshot(snapshot_dir)
    dataset_root = Path(descriptor["dataset_root"])
    output_dir = Path(output_dir)
    dataset_dir = output_dir / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    split_alias = {"train": "train", "validation": "val", "test": "test"}
    modes: dict[str, int] = {"HARDLINK": 0, "COPY": 0, "REUSED": 0}
    box_counts = {"train": 0, "val": 0, "test": 0}

    for row in rows:
        split = split_alias[row["split"]]
        src_image = dataset_root / Path(row["image"])
        src_label = Path(snapshot_dir) / "labels" / Path(row["snapshot_label"])
        if not src_image.is_file():
            raise YoloReferenceError(f"source image missing: {src_image}")
        if not src_label.is_file():
            raise YoloReferenceError(f"snapshot label missing: {src_label}")

        image_name = Path(row["image"]).name
        label_name = Path(row["snapshot_label"]).name
        dst_image = dataset_dir / split / "images" / image_name
        dst_label = dataset_dir / split / "labels" / label_name

        mode = _safe_link_or_copy(src_image, dst_image)
        modes[mode] += 1
        label_mode = _safe_link_or_copy(src_label, dst_label)
        modes[label_mode] += 1
        box_counts[split] += int(row["valid_bbox_count"])

    yaml_path = dataset_dir / "data.yaml"
    yaml_path.write_text(
        "\n".join([
            f"path: {dataset_dir.resolve().as_posix()}",
            "train: train/images",
            "val: val/images",
            "test: test/images",
            "names:",
            "  0: Adult_female",
            "  1: Immature",
            "  2: Viable_egg",
            "",
        ]),
        encoding="utf-8",
    )

    report = {
        "status": "MITE_YOLO11_REFERENCE_DATA_READY",
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_manifest_sha256": descriptor["manifest_sha256"],
        "dataset_yaml": str(yaml_path),
        "split_image_counts": {
            "train": EXPECTED_SPLIT["train"],
            "val": EXPECTED_SPLIT["validation"],
            "test": EXPECTED_SPLIT["test"],
        },
        "split_box_counts": box_counts,
        "materialization_modes": modes,
        "test_policy": "LOCKED_DURING_MODEL_SELECTION",
    }
    (output_dir / "dataset-materialization.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _resolve_trained_batch(results: Any, configured_batch: int | float) -> int | str:
    # Ultralytics AutoBatch resolves batch=-1 internally. Prefer trainer args when available.
    trainer = getattr(results, "trainer", None)
    args = getattr(trainer, "args", None)
    batch = getattr(args, "batch", None)
    if isinstance(batch, int) and batch > 0:
        return batch
    if configured_batch == -1:
        return "auto"
    return int(configured_batch)


def _require_ultralytics():
    try:
        import ultralytics
        from ultralytics import YOLO
    except ImportError as exc:
        raise YoloReferenceError(
            "ultralytics is required for this reference track. "
            "Install intentionally with: python -m pip install ultralytics"
        ) from exc
    return ultralytics, YOLO


def train(args) -> int:
    if not args.acknowledge_reference_only:
        raise YoloReferenceError(
            "This Ultralytics YOLO11 track is reference/portfolio-only. "
            "Re-run with --acknowledge-reference-only after reviewing license scope."
        )

    ultralytics, YOLO = _require_ultralytics()
    report = materialize_yolo_dataset(args.snapshot, args.output)
    data_yaml = Path(report["dataset_yaml"])

    try:
        import torch
    except ImportError as exc:
        raise YoloReferenceError("PyTorch is required") from exc
    if not torch.cuda.is_available():
        raise YoloReferenceError(
            "CUDA unavailable. Activate the nongtori_gpu environment before training."
        )

    args.output.mkdir(parents=True, exist_ok=True)
    run_dir = args.output / "runs"
    started = time.time()

    actual_batch: int | float
    if args.batch == "auto":
        actual_batch = -1
    else:
        actual_batch = int(args.batch)

    execution_contract = {
        "status": "MITE_YOLO11_REFERENCE_TRAINING_CONFIGURED",
        "role": "SOURCE_REFERENCE_PORTFOLIO_ONLY",
        "source_contract": SOURCE_CONTRACT,
        "actual_config": {
            "weights": "yolo11l.pt",
            "epochs": 100,
            "patience": 25,
            "imgsz": 1024,
            "batch": "auto" if actual_batch == -1 else actual_batch,
            "seed": 42,
            "device": 0,
            "workers": args.workers,
        },
        "known_deviations": [
            {
                "field": "batch",
                "source": 16,
                "nongtori": "auto" if actual_batch == -1 else actual_batch,
                "reason": "RTX 4060 VRAM constraint; source used A100 40GB",
            },
            {
                "field": "split",
                "source": "original Roboflow split",
                "nongtori": "leakage-safe connected origin/hash group split",
                "reason": "source audit found cross-split duplicate/origin overlap",
            },
        ],
        "ultralytics_version": getattr(ultralytics, "__version__", "unknown"),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_manifest_sha256": report["snapshot_manifest_sha256"],
        "test_policy": "LOCKED_NOT_EVALUATED_DURING_SELECTION",
    }
    (args.output / "execution-contract.json").write_text(
        json.dumps(execution_contract, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        "MITE YOLO11 SOURCE REFERENCE V001 | "
        "model=yolo11l.pt | imgsz=1024 | epochs=100 | patience=25 | "
        f"batch={execution_contract['actual_config']['batch']} | test=LOCKED",
        flush=True,
    )
    print(
        "role=SOURCE_REFERENCE_PORTFOLIO_ONLY | "
        "split=NONGTORI_LEAKAGE_SAFE | selection=validation",
        flush=True,
    )

    model = YOLO("yolo11l.pt")
    results = model.train(
        data=str(data_yaml),
        epochs=100,
        patience=25,
        imgsz=1024,
        batch=actual_batch,
        seed=42,
        device=0,
        workers=args.workers,
        project=str(run_dir),
        name="morphology_v001",
        exist_ok=False,
        pretrained=True,
        val=True,
        plots=True,
        save=True,
        save_period=-1,
        verbose=True,
    )

    save_dir = Path(results.save_dir)
    best_path = save_dir / "weights" / "best.pt"
    if not best_path.is_file():
        raise YoloReferenceError(f"best checkpoint missing: {best_path}")

    metrics = dict(getattr(results, "results_dict", {}) or {})
    summary = {
        "status": "MITE_YOLO11_REFERENCE_V001_TRAINED",
        "role": "SOURCE_REFERENCE_PORTFOLIO_ONLY",
        "selection_split": "validation",
        "test_status": "LOCKED_NOT_EVALUATED",
        "source_contract": SOURCE_CONTRACT,
        "actual_batch": _resolve_trained_batch(results, actual_batch),
        "best_checkpoint": str(best_path),
        "best_checkpoint_sha256": _sha256(best_path),
        "validation_results": metrics,
        "save_dir": str(save_dir),
        "elapsed_sec": time.time() - started,
        "field_readiness": "NOT_ESTABLISHED",
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0



def evaluate_test(args) -> int:
    if not args.acknowledge_test_once:
        raise YoloReferenceError(
            "Public test is a one-time frozen evaluation. "
            "Re-run with --acknowledge-test-once after validation freeze review."
        )

    ultralytics, YOLO = _require_ultralytics()
    report = materialize_yolo_dataset(args.snapshot, args.output)

    checkpoint = Path(args.checkpoint)
    if not checkpoint.is_file():
        raise YoloReferenceError(f"checkpoint missing: {checkpoint}")

    expected_sha = args.expected_checkpoint_sha256.strip().lower()
    actual_sha = _sha256(checkpoint)
    if expected_sha and actual_sha != expected_sha:
        raise YoloReferenceError(
            f"checkpoint SHA-256 mismatch: expected {expected_sha}, got {actual_sha}"
        )

    model = YOLO(str(checkpoint))
    results = model.val(
        data=str(report["dataset_yaml"]),
        split="test",
        imgsz=1024,
        batch=args.batch,
        device=0,
        workers=args.workers,
        plots=True,
        verbose=True,
    )
    metrics = dict(getattr(results, "results_dict", {}) or {})
    output = {
        "status": "MITE_YOLO11_REFERENCE_V001_TEST_EVALUATED",
        "role": "SOURCE_REFERENCE_PORTFOLIO_ONLY",
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": actual_sha,
        "selection_prohibited": True,
        "test_split": "public_test_once",
        "test_results": metrics,
        "field_readiness": "NOT_ESTABLISHED",
        "policy": "DO_NOT_TUNE_OR_SELECT_FROM_THIS_TEST_RESULT",
        "ultralytics_version": getattr(ultralytics, "__version__", "unknown"),
    }
    out_path = Path(args.output) / "test-summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Nongtori YOLO11-Large TSSM source-reference V001"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)

    p = sub.add_parser("train")
    p.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--batch", default="auto")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--acknowledge-reference-only", action="store_true")

    p = sub.add_parser("test")
    p.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--expected-checkpoint-sha256", default="")
    p.add_argument("--batch", type=int, default=2)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--acknowledge-test-once", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            report = materialize_yolo_dataset(args.snapshot, args.output)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if args.command == "test":
            return evaluate_test(args)
        return train(args)
    except (YoloReferenceError, ValueError) as exc:
        print(json.dumps({
            "status": "MITE_YOLO11_REFERENCE_V001_BLOCKED",
            "error": str(exc),
        }, ensure_ascii=False, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
