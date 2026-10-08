from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

DATASET_ROLE = "NON_COMMERCIAL_REFERENCE"
MODEL_NAME = "EFFICIENTNET_B0_IMAGENET"
INPUT_SIZE = 224
RESIZE_SIZE = 256


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    errors = [p - a for a, p in zip(actual, predicted, strict=True)]
    abs_errors = [abs(e) for e in errors]
    squared = [e * e for e in errors]
    mean_actual = sum(actual) / len(actual)
    ss_total = sum((x - mean_actual) ** 2 for x in actual)
    ss_residual = sum(squared)
    return {
        "mae_g": sum(abs_errors) / len(abs_errors),
        "rmse_g": math.sqrt(sum(squared) / len(squared)),
        "r2": 1.0 - ss_residual / ss_total if ss_total > 1e-12 else 0.0,
        "bias_g": sum(errors) / len(errors),
        "max_abs_error_g": max(abs_errors),
    }


def _grade_metrics(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    expected = [_grade(v) for v in actual]
    observed = [_grade(v) for v in predicted]
    correct = sum(a == b for a, b in zip(expected, observed, strict=True))
    confusion = Counter(
        f"{a}->{b}" for a, b in zip(expected, observed, strict=True)
    )
    return {
        "grade_accuracy": correct / len(expected),
        "grade_error_count": len(expected) - correct,
        "grade_confusion": dict(sorted(confusion.items())),
    }


def aggregate_view_predictions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["berry_key"])].append(record)

    output: list[dict[str, Any]] = []
    for berry_key in sorted(grouped):
        rows = grouped[berry_key]
        targets = {_to_float(row["actual_weight_g"], "actual_weight_g") for row in rows}
        if len(targets) != 1:
            raise ValueError(f"inconsistent target for berry {berry_key}")
        target = next(iter(targets))
        predictions = [_to_float(row["predicted_weight_g"], "predicted_weight_g") for row in rows]
        output.append(
            {
                "berry_key": berry_key,
                "actual_weight_g": target,
                "predicted_weight_g": sum(predictions) / len(predictions),
                "view_count": len(predictions),
            }
        )
    return output


def _runtime():
    try:
        import torch
        from torch import nn
        from torchvision import models, transforms
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Dyson RGB benchmark requires torch, torchvision, and Pillow"
        ) from exc
    return torch, nn, models, transforms, Image


def _default_predictor(
    rows: list[dict[str, str]],
    *,
    crop_root: Path,
    checkpoint_path: Path,
    device_name: str | None,
) -> list[dict[str, Any]]:
    torch, nn, models, transforms, Image = _runtime()

    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    normalize = transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    )
    eval_transform = transforms.Compose(
        [
            transforms.Resize(RESIZE_SIZE),
            transforms.CenterCrop(INPUT_SIZE),
            transforms.ToTensor(),
            normalize,
        ]
    )

    model = models.efficientnet_b0(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, 1)

    try:
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    except TypeError:
        checkpoint = torch.load(checkpoint_path, map_location=device)

    if checkpoint.get("model_name") != MODEL_NAME:
        raise ValueError(
            f"unexpected checkpoint model: {checkpoint.get('model_name')!r}"
        )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    output: list[dict[str, Any]] = []
    with torch.no_grad():
        for index, row in enumerate(rows, start=1):
            crop_path = crop_root / Path(row["crop_relative_path"])
            if not crop_path.is_file():
                raise FileNotFoundError(f"missing Dyson crop: {crop_path}")

            expected_hash = str(row.get("crop_sha256") or "").strip()
            actual_hash = _sha256_file(crop_path)
            if expected_hash and actual_hash != expected_hash:
                raise ValueError(
                    f"crop hash mismatch: {crop_path} expected={expected_hash} actual={actual_hash}"
                )

            with Image.open(crop_path) as source:
                image = source.convert("RGB")
                tensor = eval_transform(image).unsqueeze(0).to(device)
            prediction = float(model(tensor).squeeze().detach().cpu().item())
            output.append(
                {
                    "berry_key": row["berry_key"],
                    "view_index": row["view_index"],
                    "actual_weight_g": _to_float(row["weight_g"], "weight_g"),
                    "predicted_weight_g": prediction,
                    "category_id": row.get("category_id", ""),
                    "crop_relative_path": row["crop_relative_path"],
                }
            )

            if index == 1 or index % 100 == 0 or index == len(rows):
                print(f"[DYSON RGB] {index}/{len(rows)} views", flush=True)
    return output


def run_dyson_external_rgb_benchmark(
    *,
    crop_manifest: Path,
    crop_root: Path,
    rgb_baseline_dir: Path,
    output_dir: Path,
    device_name: str | None = None,
    predictor: Callable[..., list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    crop_manifest = Path(crop_manifest)
    crop_root = Path(crop_root)
    rgb_baseline_dir = Path(rgb_baseline_dir)
    output_dir = Path(output_dir)

    checkpoint_path = rgb_baseline_dir / "best.pt"
    baseline_report_path = rgb_baseline_dir / "rgb_baseline.json"
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"RGB V001 checkpoint missing: {checkpoint_path}")
    if not baseline_report_path.is_file():
        raise FileNotFoundError(f"RGB V001 report missing: {baseline_report_path}")

    baseline_report = json.loads(baseline_report_path.read_text(encoding="utf-8"))
    if baseline_report.get("status") != "RGB_BASELINE_COMPLETE":
        raise ValueError("RGB V001 baseline result is not complete")
    if baseline_report.get("model") != MODEL_NAME:
        raise ValueError("RGB V001 model contract mismatch")

    with crop_manifest.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    eligible = [
        row
        for row in rows
        if row.get("materialization_status") in {"MATERIALIZED", "REUSED_EXISTING_CROP"}
    ]
    if not eligible:
        raise ValueError("Dyson crop manifest has no successful crop rows")

    for row in eligible:
        if row.get("dataset_role") != DATASET_ROLE:
            raise ValueError(f"dataset role drifted in {row.get('berry_key')}")
        if str(row.get("commercial_training_ready")) != "False":
            raise ValueError(f"commercial guard drifted in {row.get('berry_key')}")

    predict = predictor or _default_predictor
    view_records = predict(
        eligible,
        crop_root=crop_root,
        checkpoint_path=checkpoint_path,
        device_name=device_name,
    )
    berry_records = aggregate_view_predictions(view_records)

    actual = [float(row["actual_weight_g"]) for row in berry_records]
    predicted = [float(row["predicted_weight_g"]) for row in berry_records]
    metrics = _metrics(actual, predicted)
    metrics.update(_grade_metrics(actual, predicted))
    metrics["n_berries"] = len(berry_records)
    metrics["n_views"] = len(view_records)

    output_dir.mkdir(parents=True, exist_ok=True)
    view_path = output_dir / "dyson_rgb_view_predictions.csv"
    with view_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "berry_key",
                "view_index",
                "actual_weight_g",
                "predicted_weight_g",
                "category_id",
                "crop_relative_path",
            ],
        )
        writer.writeheader()
        writer.writerows(view_records)

    berry_path = output_dir / "dyson_rgb_berry_predictions.csv"
    with berry_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "berry_key",
                "actual_weight_g",
                "predicted_weight_g",
                "view_count",
            ],
        )
        writer.writeheader()
        writer.writerows(berry_records)

    report = {
        "status": "DYSON_EXTERNAL_RGB_BENCHMARK_COMPLETE",
        "dataset_role": DATASET_ROLE,
        "commercial_training_ready": False,
        "benchmark_role": "EXTERNAL_NON_COMMERCIAL_REFERENCE",
        "training_policy": "NO_RETRAINING_NO_TUNING",
        "source_model": MODEL_NAME,
        "source_checkpoint": str(checkpoint_path),
        "source_checkpoint_sha256": _sha256_file(checkpoint_path),
        "aggregation": "MEAN_AVAILABLE_CROP_VIEWS",
        "eval_transform": {
            "resize": RESIZE_SIZE,
            "center_crop": INPUT_SIZE,
            "normalize": "IMAGENET1K_V1",
        },
        "eligible_crop_view_count": len(eligible),
        "evaluated_berry_count": len(berry_records),
        "metrics": metrics,
        "view_predictions": str(view_path),
        "berry_predictions": str(berry_path),
        "interpretation_guard": (
            "This is an external non-commercial generalization benchmark. "
            "Dyson data does not tune, retrain, or select the Dryad RGB V001 model."
        ),
    }
    (output_dir / "dyson_external_rgb_benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate frozen RGB V001 on Dyson berry crops without retraining"
    )
    parser.add_argument(
        "--crop-manifest",
        type=Path,
        default=Path("data/audit/icra-dyson-berry-crops/berry-crop-manifest.csv"),
    )
    parser.add_argument(
        "--crop-root",
        type=Path,
        default=Path("data/external/icra-dyson-berry-crops"),
    )
    parser.add_argument(
        "--rgb-baseline-dir",
        type=Path,
        default=Path("artifacts/weight/rgb-v001"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/dyson-external-rgb-v001"),
    )
    parser.add_argument("--device")
    args = parser.parse_args(argv)

    try:
        report = run_dyson_external_rgb_benchmark(
            crop_manifest=args.crop_manifest,
            crop_root=args.crop_root,
            rgb_baseline_dir=args.rgb_baseline_dir,
            output_dir=args.output_dir,
            device_name=args.device,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "DYSON_EXTERNAL_RGB_BENCHMARK_BLOCKED", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
