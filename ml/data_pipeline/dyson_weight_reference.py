from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_ID = "DATA-WEIGHT-003"
SOURCE_NAME = "ICRA 2022 Dyson Strawberry Weight Dataset"
SOURCE_REPO = "https://github.com/imanlab/strawberry-pp-w-r-dataset"
DATASET_URL = "https://drive.google.com/drive/folders/1meEKYLgdQpUgkpeqM6VgzHmJg0gNTCx0?usp=sharing"
LICENSE = "CC-BY-NC-SA"
DATASET_ROLE = "NON_COMMERCIAL_REFERENCE"

DEFAULT_RAW_ROOT = Path("data/external/icra-dyson")
DEFAULT_AUDIT_ROOT = Path("data/audit/icra-dyson")

SUFFIX_ROLES = (
    ("_bgremoved.png", "bgremoved_rgb"),
    ("_rdepth.npy", "raw_depth"),
    ("_odepth.png", "odepth"),
    ("_pdepth.png", "pdepth"),
    ("_label.npy", "weight_label"),
    ("_rgb.png", "rgb"),
    ("_pc.ply", "point_cloud"),
)

REQUIRED_REFERENCE_ROLES = ("rgb", "weight_label")


class DysonPipelineError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_sample_file(path: Path) -> tuple[str, str] | None:
    name = path.name
    lowered = name.lower()
    for suffix, role in SUFFIX_ROLES:
        if lowered.endswith(suffix):
            stem = name[: len(name) - len(suffix)]
            if not stem:
                raise DysonPipelineError(f"empty sample stem for file: {path}")
            return stem, role
    return None


def _gdown_available() -> bool:
    return importlib.util.find_spec("gdown") is not None


def acquire_dyson_dataset(
    raw_root: Path = DEFAULT_RAW_ROOT,
    audit_root: Path = DEFAULT_AUDIT_ROOT,
    *,
    dataset_url: str = DATASET_URL,
    runner=subprocess.run,
) -> dict[str, Any]:
    raw_root = Path(raw_root)
    audit_root = Path(audit_root)
    audit_root.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(parents=True, exist_ok=True)

    if not _gdown_available():
        raise DysonPipelineError(
            "gdown is required for public Google Drive folder acquisition. "
            f"Install it in the active environment with: {sys.executable} -m pip install gdown"
        )

    before = {
        path.relative_to(raw_root).as_posix(): path.stat().st_size
        for path in raw_root.rglob("*")
        if path.is_file()
    }

    command = [
        sys.executable,
        "-m",
        "gdown",
        "--folder",
        dataset_url,
        "-O",
        str(raw_root),
        "--continue",
        "--remaining-ok",
        "--fuzzy",
    ]

    print("=" * 88)
    print(" ICRA/DYSON DATASET #1 · ACQUISITION")
    print("=" * 88)
    print(f" source      {dataset_url}")
    print(f" license     {LICENSE} · {DATASET_ROLE}")
    print(f" destination {raw_root}")
    print(f" reuse       {len(before):,} existing files detected")
    print(f" command     {' '.join(command)}")
    print("-" * 88)

    completed = runner(command, check=False)
    if int(getattr(completed, "returncode", 1)) != 0:
        raise DysonPipelineError(
            "gdown folder acquisition failed. Common causes are Google Drive quota, "
            "public-folder access changes, or an interrupted connection. Rerun the same "
            "command after the issue clears; --continue preserves resumable behavior."
        )

    after_paths = sorted(path for path in raw_root.rglob("*") if path.is_file())
    after = {
        path.relative_to(raw_root).as_posix(): path.stat().st_size
        for path in after_paths
    }
    reused = sum(
        1 for relative, size in after.items()
        if before.get(relative) == size
    )
    new_or_changed = len(after) - reused

    manifest = {
        "status": "DYSON_ACQUISITION_COMPLETE",
        "contract": "nongtori-dyson-acquisition.v1",
        "source_id": SOURCE_ID,
        "source_repo": SOURCE_REPO,
        "dataset_url": dataset_url,
        "dataset_role": DATASET_ROLE,
        "license": LICENSE,
        "commercial_training_ready": False,
        "retrieved_at": utc_now(),
        "raw_root": str(raw_root),
        "file_count": len(after),
        "reused_same_size_count": reused,
        "new_or_changed_count": new_or_changed,
        "note": (
            "Acquisition completion does not imply RGB/weight join validity. "
            "Run dyson-audit before any reference use."
        ),
    }
    output = audit_root / "acquisition-manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f" files       {len(after):,}")
    print(f" reused      {reused:,}")
    print(f" new/changed {new_or_changed:,}")
    print(f" manifest    {output}")
    print("=" * 88)
    return manifest


def _load_numpy_label(path: Path) -> tuple[dict[str, Any], list[float]]:
    try:
        import numpy as np
    except ImportError as exc:
        raise DysonPipelineError(
            "NumPy is required to audit Dyson *_label.npy weight files."
        ) from exc

    try:
        value = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise DysonPipelineError(f"cannot load NumPy label {path}: {exc}") from exc

    array = np.asarray(value)
    flat = array.reshape(-1)
    numeric_values: list[float] = []
    invalid_non_finite = 0
    invalid_non_positive = 0

    for item in flat:
        try:
            number = float(item)
        except (TypeError, ValueError) as exc:
            raise DysonPipelineError(
                f"weight label contains non-numeric value in {path}: {item!r}"
            ) from exc
        if not math.isfinite(number):
            invalid_non_finite += 1
            continue
        if number <= 0:
            invalid_non_positive += 1
        numeric_values.append(number)

    return (
        {
            "dtype": str(array.dtype),
            "shape": list(array.shape),
            "ndim": int(array.ndim),
            "size": int(array.size),
            "kind": (
                "SCALAR"
                if array.ndim == 0 or array.size == 1
                else "VECTOR_OR_ARRAY"
            ),
            "finite_count": len(numeric_values),
            "non_finite_count": invalid_non_finite,
            "non_positive_count": invalid_non_positive,
        },
        numeric_values,
    )


def audit_dyson_dataset(
    raw_root: Path = DEFAULT_RAW_ROOT,
    audit_root: Path = DEFAULT_AUDIT_ROOT,
) -> dict[str, Any]:
    raw_root = Path(raw_root)
    audit_root = Path(audit_root)
    if not raw_root.is_dir():
        raise DysonPipelineError(
            f"Dyson raw root is missing: {raw_root}. Run dyson-acquire first."
        )
    audit_root.mkdir(parents=True, exist_ok=True)

    all_files = sorted(path for path in raw_root.rglob("*") if path.is_file())
    if not all_files:
        raise DysonPipelineError(f"Dyson raw root contains no files: {raw_root}")

    grouped: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    unclassified: list[Path] = []
    role_counts: Counter[str] = Counter()

    for path in all_files:
        classified = classify_sample_file(path)
        if classified is None:
            unclassified.append(path)
            continue
        stem, role = classified
        grouped[stem][role].append(path)
        role_counts[role] += 1

    duplicate_role_rows: list[dict[str, Any]] = []
    for stem, roles in grouped.items():
        for role, paths in roles.items():
            if len(paths) > 1:
                duplicate_role_rows.append(
                    {
                        "sample_stem": stem,
                        "role": role,
                        "paths": [
                            path.relative_to(raw_root).as_posix()
                            for path in paths
                        ],
                    }
                )

    inventory_rows: list[dict[str, Any]] = []
    file_manifest_rows: list[dict[str, Any]] = []
    label_shape_counts: Counter[str] = Counter()
    label_dtype_counts: Counter[str] = Counter()
    total_weight_annotations = 0
    invalid_non_finite_values = 0
    invalid_non_positive_values = 0
    label_value_min: float | None = None
    label_value_max: float | None = None
    label_rows: list[dict[str, Any]] = []

    exact_rgb_label = 0
    missing_rgb: list[str] = []
    missing_label: list[str] = []

    print("=" * 88)
    print(" ICRA/DYSON WEIGHT DATA AUDIT")
    print("=" * 88)
    print(f" role        {DATASET_ROLE}")
    print(f" license     {LICENSE} · commercial_training_ready=False")
    print(f" raw root    {raw_root}")
    print(f" files       {len(all_files):,}")
    print(f" stems       {len(grouped):,}")
    print("-" * 88)

    for index, stem in enumerate(sorted(grouped), start=1):
        roles = grouped[stem]
        singleton = {
            role: paths[0]
            for role, paths in roles.items()
            if len(paths) == 1
        }
        has_rgb = "rgb" in singleton
        has_label = "weight_label" in singleton

        if has_rgb and has_label:
            exact_rgb_label += 1
        elif not has_rgb:
            missing_rgb.append(stem)
        elif not has_label:
            missing_label.append(stem)

        label_info: dict[str, Any] | None = None
        label_values: list[float] = []
        if has_label:
            label_info, label_values = _load_numpy_label(singleton["weight_label"])
            shape_key = str(tuple(label_info["shape"]))
            label_shape_counts[shape_key] += 1
            label_dtype_counts[str(label_info["dtype"])] += 1
            total_weight_annotations += int(label_info["size"])
            invalid_non_finite_values += int(label_info["non_finite_count"])
            invalid_non_positive_values += int(label_info["non_positive_count"])
            finite = [value for value in label_values if math.isfinite(value)]
            if finite:
                local_min = min(finite)
                local_max = max(finite)
                label_value_min = (
                    local_min if label_value_min is None else min(label_value_min, local_min)
                )
                label_value_max = (
                    local_max if label_value_max is None else max(label_value_max, local_max)
                )
            label_rows.append(
                {
                    "sample_stem": stem,
                    **label_info,
                    "value_min": min(finite) if finite else None,
                    "value_max": max(finite) if finite else None,
                }
            )

        paths_by_role = {
            role: paths[0].relative_to(raw_root).as_posix()
            for role, paths in roles.items()
            if len(paths) == 1
        }
        hashes_by_role = {
            role: sha256_file(paths[0])
            for role, paths in roles.items()
            if len(paths) == 1
        }
        for role, paths in roles.items():
            for role_index, path in enumerate(paths):
                file_manifest_rows.append(
                    {
                        "sample_stem": stem,
                        "role": role,
                        "role_index": role_index,
                        "relative_path": path.relative_to(raw_root).as_posix(),
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )

        inventory_rows.append(
            {
                "sample_stem": stem,
                "has_rgb": has_rgb,
                "has_weight_label": has_label,
                "has_bgremoved_rgb": "bgremoved_rgb" in singleton,
                "has_raw_depth": "raw_depth" in singleton,
                "has_point_cloud": "point_cloud" in singleton,
                "rgb_path": paths_by_role.get("rgb", ""),
                "weight_label_path": paths_by_role.get("weight_label", ""),
                "raw_depth_path": paths_by_role.get("raw_depth", ""),
                "point_cloud_path": paths_by_role.get("point_cloud", ""),
                "rgb_sha256": hashes_by_role.get("rgb", ""),
                "weight_label_sha256": hashes_by_role.get("weight_label", ""),
                "raw_depth_sha256": hashes_by_role.get("raw_depth", ""),
                "point_cloud_sha256": hashes_by_role.get("point_cloud", ""),
                "weight_label_shape": (
                    str(tuple(label_info["shape"])) if label_info else ""
                ),
                "weight_annotation_count": (
                    int(label_info["size"]) if label_info else 0
                ),
                "weight_non_finite_count": (
                    int(label_info["non_finite_count"]) if label_info else 0
                ),
                "weight_non_positive_count": (
                    int(label_info["non_positive_count"]) if label_info else 0
                ),
            }
        )

        if index % max(1, len(grouped) // 20) == 0 or index == len(grouped):
            pct = index / len(grouped) * 100
            print(
                f" [AUDIT] {index:,}/{len(grouped):,} ({pct:5.1f}%) · "
                f"RGB+weight={exact_rgb_label:,}",
                flush=True,
            )

    inventory_path = audit_root / "sample-inventory.csv"
    with inventory_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(inventory_rows[0].keys()) if inventory_rows else ["sample_stem"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(inventory_rows)

    file_manifest_path = audit_root / "file-manifest.csv"
    with file_manifest_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "sample_stem",
            "role",
            "role_index",
            "relative_path",
            "size_bytes",
            "sha256",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(file_manifest_rows)

    label_report = {
        "status": "DYSON_WEIGHT_LABEL_AUDIT_COMPLETE",
        "source_id": SOURCE_ID,
        "dataset_role": DATASET_ROLE,
        "license": LICENSE,
        "commercial_training_ready": False,
        "label_file_count": int(role_counts.get("weight_label", 0)),
        "shape_counts": dict(sorted(label_shape_counts.items())),
        "dtype_counts": dict(sorted(label_dtype_counts.items())),
        "total_weight_annotations": total_weight_annotations,
        "invalid_non_finite_values": invalid_non_finite_values,
        "invalid_non_positive_values": invalid_non_positive_values,
        "finite_weight_min": label_value_min,
        "finite_weight_max": label_value_max,
        "labels": label_rows,
    }
    (audit_root / "weight-label-audit.json").write_text(
        json.dumps(label_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    duplicate_count = len(duplicate_role_rows)
    ready = (
        exact_rgb_label > 0
        and not missing_rgb
        and not missing_label
        and duplicate_count == 0
        and invalid_non_finite_values == 0
        and invalid_non_positive_values == 0
    )

    join_report = {
        "status": (
            "DYSON_NON_COMMERCIAL_REFERENCE_READY"
            if ready
            else "DYSON_REFERENCE_AUDIT_WITH_EXCEPTIONS"
        ),
        "contract": "nongtori-dyson-reference-audit.v1",
        "source_id": SOURCE_ID,
        "source_repo": SOURCE_REPO,
        "dataset_url": DATASET_URL,
        "dataset_role": DATASET_ROLE,
        "license": LICENSE,
        "commercial_training_ready": False,
        "audited_at": utc_now(),
        "raw_root": str(raw_root),
        "total_files": len(all_files),
        "total_sample_stems": len(grouped),
        "role_counts": dict(sorted(role_counts.items())),
        "exact_rgb_weight_matched_count": exact_rgb_label,
        "missing_rgb_count": len(missing_rgb),
        "missing_rgb_sample": missing_rgb[:50],
        "missing_weight_count": len(missing_label),
        "missing_weight_sample": missing_label[:50],
        "duplicate_role_count": duplicate_count,
        "duplicate_roles": duplicate_role_rows[:50],
        "unclassified_file_count": len(unclassified),
        "unclassified_file_sample": [
            path.relative_to(raw_root).as_posix()
            for path in unclassified[:50]
        ],
        "weight_label_summary": {
            "label_file_count": int(role_counts.get("weight_label", 0)),
            "shape_counts": dict(sorted(label_shape_counts.items())),
            "dtype_counts": dict(sorted(label_dtype_counts.items())),
            "total_weight_annotations": total_weight_annotations,
            "invalid_non_finite_values": invalid_non_finite_values,
            "invalid_non_positive_values": invalid_non_positive_values,
            "finite_weight_min": label_value_min,
            "finite_weight_max": label_value_max,
        },
        "license_guard": {
            "canonical_commercial_training_merge_allowed": False,
            "dryad_snapshot_auto_merge_allowed": False,
            "role": DATASET_ROLE,
            "reason": (
                "Official repository declares CC-BY-NC-SA and free non-commercial use. "
                "Keep this dataset isolated from commercial/canonical training assets."
            ),
        },
        "artifacts": {
            "sample_inventory": str(inventory_path),
            "file_manifest": str(file_manifest_path),
            "weight_label_audit": str(audit_root / "weight-label-audit.json"),
            "join_audit": str(audit_root / "join-audit.json"),
        },
    }
    (audit_root / "join-audit.json").write_text(
        json.dumps(join_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("-" * 88)
    print(f" RGB files       {role_counts.get('rgb', 0):,}")
    print(f" Weight labels   {role_counts.get('weight_label', 0):,}")
    print(f" RGB+weight join {exact_rgb_label:,}")
    print(f" Missing RGB     {len(missing_rgb):,}")
    print(f" Missing weight  {len(missing_label):,}")
    print(f" Duplicate roles {duplicate_count:,}")
    print(f" Weight items    {total_weight_annotations:,}")
    print(f" Label shapes    {dict(sorted(label_shape_counts.items()))}")
    print("-" * 88)
    print(f" Decision        {join_report['status']}")
    print(f" Commercial      BLOCKED · {DATASET_ROLE}")
    print("=" * 88)

    return join_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ICRA/Dyson reference dataset pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("acquire")
    p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    p.add_argument("--audit-root", type=Path, default=DEFAULT_AUDIT_ROOT)
    p.add_argument("--dataset-url", default=DATASET_URL)

    p = sub.add_parser("audit")
    p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    p.add_argument("--audit-root", type=Path, default=DEFAULT_AUDIT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "acquire":
            acquire_dyson_dataset(
                args.raw_root,
                args.audit_root,
                dataset_url=args.dataset_url,
            )
            return 0
        report = audit_dyson_dataset(args.raw_root, args.audit_root)
        return (
            0
            if report["status"] == "DYSON_NON_COMMERCIAL_REFERENCE_READY"
            else 2
        )
    except DysonPipelineError as exc:
        print(
            json.dumps(
                {"status": "DYSON_PIPELINE_BLOCKED", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
