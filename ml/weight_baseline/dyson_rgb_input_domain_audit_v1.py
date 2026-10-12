from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from .rgb_v001 import load_weight_snapshot, _verify_assets


INPUT_SIZE = 224
RESIZE_SIZE = 256
DATASET_ROLE = "NON_COMMERCIAL_REFERENCE"


def _to_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"non-finite {field}: {value!r}")
    return number


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot compute quantile of empty values")
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("summary requires non-empty values")
    avg = sum(values) / len(values)
    var = sum((value - avg) ** 2 for value in values) / len(values)
    return {
        "count": len(values),
        "mean": avg,
        "std": math.sqrt(var),
        "min": min(values),
        "q05": _quantile(values, 0.05),
        "median": _quantile(values, 0.50),
        "q95": _quantile(values, 0.95),
        "max": max(values),
    }


def _standardized_mean_difference(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_var = sum((value - left_mean) ** 2 for value in left) / len(left)
    right_var = sum((value - right_mean) ** 2 for value in right) / len(right)
    pooled = math.sqrt((left_var + right_var) / 2.0)
    if pooled <= 1e-12:
        return 0.0 if abs(left_mean - right_mean) <= 1e-12 else math.inf
    return (right_mean - left_mean) / pooled


def _default_probe(path: Path) -> dict[str, float]:
    try:
        from PIL import Image, ImageStat
    except ImportError as exc:
        raise RuntimeError("input-domain audit requires Pillow") from exc

    with Image.open(path) as source:
        image = source.convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError(f"invalid image size: {path}")

        if width <= height:
            resized_width = RESIZE_SIZE
            resized_height = max(1, round(height * RESIZE_SIZE / width))
        else:
            resized_height = RESIZE_SIZE
            resized_width = max(1, round(width * RESIZE_SIZE / height))

        resampling = getattr(Image, "Resampling", Image).BILINEAR
        resized = image.resize((resized_width, resized_height), resample=resampling)
        left = max(0, (resized_width - INPUT_SIZE) // 2)
        top = max(0, (resized_height - INPUT_SIZE) // 2)
        cropped = resized.crop((left, top, left + INPUT_SIZE, top + INPUT_SIZE))

        rgb_stat = ImageStat.Stat(cropped)
        gray_stat = ImageStat.Stat(cropped.convert("L"))
        hsv_stat = ImageStat.Stat(cropped.convert("HSV"))

        retained = (INPUT_SIZE * INPUT_SIZE) / (resized_width * resized_height)
        return {
            "source_width": float(width),
            "source_height": float(height),
            "source_aspect_ratio": float(width) / float(height),
            "center_crop_retained_fraction": retained,
            "r_mean": rgb_stat.mean[0] / 255.0,
            "g_mean": rgb_stat.mean[1] / 255.0,
            "b_mean": rgb_stat.mean[2] / 255.0,
            "r_std": rgb_stat.stddev[0] / 255.0,
            "g_std": rgb_stat.stddev[1] / 255.0,
            "b_std": rgb_stat.stddev[2] / 255.0,
            "luminance_mean": gray_stat.mean[0] / 255.0,
            "luminance_std": gray_stat.stddev[0] / 255.0,
            "saturation_mean": hsv_stat.mean[1] / 255.0,
        }


def _probe_many(
    paths: list[Path],
    *,
    probe: Callable[[Path], dict[str, float]],
) -> list[dict[str, float]]:
    records: list[dict[str, float]] = []
    for index, path in enumerate(paths, start=1):
        records.append(probe(path))
        if index == 1 or index % 250 == 0 or index == len(paths):
            print(f"[RGB DOMAIN] {index}/{len(paths)} images", flush=True)
    return records


def _summarize_records(records: list[dict[str, float]]) -> dict[str, Any]:
    if not records:
        raise ValueError("no image-domain records")
    keys = sorted(records[0])
    return {
        "image_count": len(records),
        "metrics": {
            key: _summary([record[key] for record in records])
            for key in keys
        },
    }


def run_input_domain_audit(
    *,
    dryad_snapshot_dir: Path,
    dyson_crop_manifest: Path,
    dyson_crop_root: Path,
    output_dir: Path,
    probe: Callable[[Path], dict[str, float]] = _default_probe,
) -> dict[str, Any]:
    dryad_snapshot_dir = Path(dryad_snapshot_dir)
    dyson_crop_manifest = Path(dyson_crop_manifest)
    dyson_crop_root = Path(dyson_crop_root)
    output_dir = Path(output_dir)

    descriptor, snapshot_rows = load_weight_snapshot(dryad_snapshot_dir)
    asset_root = _verify_assets(dryad_snapshot_dir, descriptor, snapshot_rows)
    dryad_test_paths = [
        asset_root / Path(row.relative_path)
        for row in snapshot_rows
        if row.split == "test"
    ]
    if not dryad_test_paths:
        raise ValueError("Dryad test RGB set is empty")

    if not dyson_crop_manifest.is_file():
        raise FileNotFoundError(f"Dyson crop manifest missing: {dyson_crop_manifest}")
    with dyson_crop_manifest.open(encoding="utf-8", newline="") as handle:
        crop_rows = list(csv.DictReader(handle))

    eligible = [
        row for row in crop_rows
        if row.get("materialization_status") in {"MATERIALIZED", "REUSED_EXISTING_CROP"}
    ]
    if not eligible:
        raise ValueError("Dyson crop manifest has no successful crops")
    for row in eligible:
        if row.get("dataset_role") != DATASET_ROLE:
            raise ValueError(f"Dyson dataset role drifted in {row.get('berry_key')}")
        if str(row.get("commercial_training_ready")) != "False":
            raise ValueError(f"Dyson commercial guard drifted in {row.get('berry_key')}")

    dyson_paths = [dyson_crop_root / Path(row["crop_relative_path"]) for row in eligible]
    missing = [str(path) for path in dyson_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Dyson crops missing; sample={missing[:10]}")

    dryad_records = _probe_many(dryad_test_paths, probe=probe)
    dyson_records = _probe_many(dyson_paths, probe=probe)

    dryad_summary = _summarize_records(dryad_records)
    dyson_summary = _summarize_records(dyson_records)
    metric_names = sorted(dryad_records[0])
    shifts = {}
    for metric in metric_names:
        left = [row[metric] for row in dryad_records]
        right = [row[metric] for row in dyson_records]
        shifts[metric] = {
            "mean_delta": mean(right) - mean(left),
            "standardized_mean_difference": _standardized_mean_difference(left, right),
        }

    ranked = sorted(
        (
            {
                "metric": metric,
                "standardized_mean_difference": values["standardized_mean_difference"],
                "absolute_standardized_mean_difference": abs(values["standardized_mean_difference"]),
                "mean_delta": values["mean_delta"],
            }
            for metric, values in shifts.items()
            if math.isfinite(values["standardized_mean_difference"])
        ),
        key=lambda item: item["absolute_standardized_mean_difference"],
        reverse=True,
    )

    report = {
        "status": "DYSON_RGB_INPUT_DOMAIN_AUDIT_COMPLETE",
        "comparison": "DRYAD_TEST_RGB_VIEWS_VS_DYSON_BERRY_CROPS",
        "preprocessing_contract": {
            "resize_short_edge": RESIZE_SIZE,
            "center_crop": INPUT_SIZE,
            "rgb_scale": "0_TO_1",
            "note": "Pixel statistics are measured after the same geometric eval preprocessing used by RGB V001 and before ImageNet normalization.",
        },
        "dryad_test": dryad_summary,
        "dyson": dyson_summary,
        "metric_shift": shifts,
        "largest_standardized_shifts": ranked[:8],
        "interpretation_guard": (
            "This audit quantifies low-level input-domain differences. "
            "It does not prove which visual factor causally drives the external benchmark failure "
            "and must not be used to tune the frozen RGB V001 model."
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "dyson_rgb_input_domain_audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["artifact"] = str(output)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare RGB V001 input statistics between Dryad test views and Dyson crops"
    )
    parser.add_argument(
        "--dryad-snapshot-dir",
        type=Path,
        default=Path("data/snapshots/WEIGHT-DRYAD-V001"),
    )
    parser.add_argument(
        "--dyson-crop-manifest",
        type=Path,
        default=Path("data/audit/icra-dyson-berry-crops/berry-crop-manifest.csv"),
    )
    parser.add_argument(
        "--dyson-crop-root",
        type=Path,
        default=Path("data/external/icra-dyson-berry-crops"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/weight/dyson-external-rgb-v001"),
    )
    args = parser.parse_args(argv)

    try:
        report = run_input_domain_audit(
            dryad_snapshot_dir=args.dryad_snapshot_dir,
            dyson_crop_manifest=args.dyson_crop_manifest,
            dyson_crop_root=args.dyson_crop_root,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status":"DYSON_RGB_INPUT_DOMAIN_AUDIT_BLOCKED","error":str(exc)}, ensure_ascii=False, indent=2))
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
