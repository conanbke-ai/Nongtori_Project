from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from ml.observability import RunLogger
from ml.ripeness_baseline.cache_v001 import get_or_build_snapshot_cache
from ml.ripeness_baseline.screen_lr_v002 import _num_workers
from ml.ripeness_baseline.train_v001 import CLASS_TO_INDEX, CLASS_VALUES, metrics, seed_all

DEFAULT_SEED = 20260910


def _load_model(architecture: str, checkpoint: Path, device):
    import torch
    from torch import nn
    from torchvision import models

    if architecture == "resnet18":
        model = models.resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, len(CLASS_VALUES))
    elif architecture == "efficientnet_b0":
        model = models.efficientnet_b0(weights=None)
        model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASS_VALUES))
    else:
        raise ValueError(f"unsupported architecture={architecture}")
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.to(device).eval()
    return model


def _infer(model, records: list[dict[str, Any]], device, seed: int) -> list[dict[str, Any]]:
    import torch
    from torch.utils.data import DataLoader, Dataset
    from torchvision import transforms

    tfm = transforms.Compose([
        transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    class DS(Dataset):
        def __len__(self): return len(records)
        def __getitem__(self, i):
            r = records[i]
            return tfm(Image.open(r["path"]).convert("RGB")), i

    loader = DataLoader(DS(), batch_size=32, shuffle=False, num_workers=_num_workers(),
                        pin_memory=torch.cuda.is_available())
    rows: list[dict[str, Any]] = []
    with torch.no_grad():
        for images, indices in loader:
            logits = model(images.to(device, non_blocking=True))
            probs = torch.softmax(logits, dim=1).cpu()
            preds = probs.argmax(1)
            for j, idx in enumerate(indices.tolist()):
                r = records[idx]
                true_value = int(r["label"])
                pred_value = int(CLASS_VALUES[preds[j].item()])
                p = probs[j].tolist()
                rows.append({
                    "sample_index": idx,
                    "path": str(r["path"]),
                    "source_asset": r.get("source_asset") or r.get("source_path") or r.get("source") or "",
                    "split": r.get("split", ""),
                    "true_label": true_value,
                    "pred_label": pred_value,
                    "correct": true_value == pred_value,
                    "confidence": float(max(p)),
                    "ordinal_error": abs(pred_value - true_value),
                    "probabilities": {str(v): float(p[i]) for i, v in enumerate(CLASS_VALUES)},
                    "record": r,
                })
    return rows


def _bucket(a: dict[str, Any], b: dict[str, Any]) -> str:
    if a["correct"] and b["correct"]: return "BOTH_CORRECT"
    if not a["correct"] and not b["correct"]:
        if a["pred_label"] == b["pred_label"]: return "SHARED_SAME_ERROR"
        return "SHARED_DIFFERENT_ERROR"
    if a["correct"]: return "RESNET_ONLY_CORRECT"
    return "EFFICIENTNET_ONLY_CORRECT"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--workdir", type=Path, default=Path("artifacts/ripeness-v008-error-audit"))
    p.add_argument("--resnet-checkpoint", type=Path, required=True)
    p.add_argument("--efficientnet-checkpoint", type=Path, required=True)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = p.parse_args()
    args.workdir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(args.workdir, "ripeness_v008_error_audit")

    try:
        import torch
        seed_all(args.seed)
        cache = get_or_build_snapshot_cache(logger)
        valid = [r for r in cache["records"] if r["split"] == "valid"]
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.emit("INFO", "AUDIT_STARTED", "paired validation residual-error audit started",
                    phase="AUDIT", samples=len(valid), device=str(device), test_evaluated=False)

        resnet = _load_model("resnet18", args.resnet_checkpoint, device)
        efficient = _load_model("efficientnet_b0", args.efficientnet_checkpoint, device)
        ra = _infer(resnet, valid, device, args.seed)
        ea = _infer(efficient, valid, device, args.seed)

        audit_rows: list[dict[str, Any]] = []
        bucket_counts = Counter()
        transition_counts = Counter()
        review_candidates = []
        for r, e in zip(ra, ea):
            bucket = _bucket(r, e); bucket_counts[bucket] += 1
            if not e["correct"]:
                transition_counts[f'{e["true_label"]}->{e["pred_label"]}'] += 1
            row = {
                "sample_index": r["sample_index"], "path": r["path"], "source_asset": r["source_asset"],
                "true_label": r["true_label"], "bucket": bucket,
                "resnet_pred": r["pred_label"], "resnet_confidence": r["confidence"], "resnet_ordinal_error": r["ordinal_error"],
                "efficientnet_pred": e["pred_label"], "efficientnet_confidence": e["confidence"], "efficientnet_ordinal_error": e["ordinal_error"],
                "suggested_review_bucket": "REVIEW_REQUIRED" if bucket.startswith("SHARED_") else "MODEL_DISAGREEMENT",
            }
            audit_rows.append(row)
            if bucket != "BOTH_CORRECT": review_candidates.append(row)

        y_true = [r["true_label"] for r in ra]
        resnet_pred = [r["pred_label"] for r in ra]
        efficient_pred = [r["pred_label"] for r in ea]
        summary = {
            "status": "AUDIT_COMPLETE", "test_evaluated": False, "validation_samples": len(valid),
            "bucket_counts": dict(bucket_counts), "efficientnet_error_transitions": dict(transition_counts),
            "resnet_metrics": metrics(y_true, resnet_pred), "efficientnet_metrics": metrics(y_true, efficient_pred),
            "resnet_error_count": sum(not r["correct"] for r in ra),
            "efficientnet_error_count": sum(not r["correct"] for r in ea),
            "shared_error_count": bucket_counts["SHARED_SAME_ERROR"] + bucket_counts["SHARED_DIFFERENT_ERROR"],
            "review_candidate_count": len(review_candidates),
            "manual_review_taxonomy": ["LABEL_AMBIGUITY", "CROP_QUALITY", "DOMAIN_VARIATION", "MODEL_DISAGREEMENT", "LIKELY_MODEL_LIMIT", "REVIEW_REQUIRED"],
        }
        (args.workdir / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.workdir / "review_candidates.json").write_text(json.dumps(review_candidates, ensure_ascii=False, indent=2), encoding="utf-8")
        with (args.workdir / "audit_rows.csv").open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(audit_rows[0].keys())); writer.writeheader(); writer.writerows(audit_rows)
        logger.emit("INFO", "AUDIT_COMPLETED", "paired validation residual-error audit completed", phase="AUDIT", **summary)
        logger.finish_summary(status="SUCCESS", summary_path=args.workdir / "summaries" / "run_summary.json", final_metrics=summary)
    except Exception as exc:
        logger.exception("RUN_FAILED", "V008 residual-error audit failed", exc, phase="FAILED")
        logger.finish_summary(status="FAILED", summary_path=args.workdir / "summaries" / "run_summary.json")
        raise


if __name__ == "__main__": main()
