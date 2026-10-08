from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import shutil
import stat
import subprocess
import sys
import zipfile
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SOURCE_ID = "DATA-WEIGHT-003"
SOURCE_NAME = "ICRA 2022 Dyson Strawberry Weight Dataset"
SOURCE_REPO = "https://github.com/imanlab/strawberry-pp-w-r-dataset"
DATASET_URL = "https://drive.google.com/drive/folders/1meEKYLgdQpUgkpeqM6VgzHmJg0gNTCx0?usp=sharing"
LICENSE = "CC-BY-NC-SA"
DATASET_ROLE = "NON_COMMERCIAL_REFERENCE"
PUBLISHED_REFERENCE = {
    "sets": 532,
    "images": 1588,
    "berries": 2413,
    "weight_annotations": 1910,
    "source": "Tafuro et al., ICRA 2022, Tables I-II",
}

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


def is_macos_metadata_path(path: Path) -> bool:
    parts = path.parts
    return (
        "__MACOSX" in parts
        or path.name.startswith("._")
        or path.name == ".DS_Store"
    )


def classify_sample_file(path: Path) -> tuple[str, str] | None:
    name = path.name
    lowered = name.lower()
    for suffix, role in SUFFIX_ROLES:
        if lowered.endswith(suffix):
            stem = name[: len(name) - len(suffix)]
            if not stem:
                raise DysonPipelineError(f"empty sample stem for file: {path}")
            return stem, role
    if lowered.endswith(".json") and lowered.startswith("strawberry_dyson_"):
        return name[:-5], "instance_annotation_json"
    return None


def canonical_sample_id(path: Path, raw_root: Path, stem: str) -> str:
    relative_parent = path.parent.relative_to(raw_root).as_posix()
    return stem if relative_parent in {"", "."} else f"{relative_parent}/{stem}"


def sample_partition(path: Path, raw_root: Path) -> str:
    parts = path.relative_to(raw_root).parts
    if len(parts) >= 2 and parts[0] == "extracted":
        return parts[1]
    return "root"


VIEW_SUFFIX_RE = re.compile(r"^(?P<scene>.+)_(?P<view>\d+)$")


def split_scene_view(stem: str) -> tuple[str, int | None]:
    match = VIEW_SUFFIX_RE.match(stem)
    if match is None:
        return stem, None
    return match.group("scene"), int(match.group("view"))


def canonical_scene_id(path: Path, raw_root: Path, stem: str) -> str:
    scene_stem, _ = split_scene_view(stem)
    relative_parent = path.parent.relative_to(raw_root).as_posix()
    return scene_stem if relative_parent in {"", "."} else f"{relative_parent}/{scene_stem}"


def _gdown_available() -> bool:
    return importlib.util.find_spec("gdown") is not None


def _crc32_file(path: Path) -> int:
    value = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value = zlib.crc32(chunk, value)
    return value & 0xFFFFFFFF


def _safe_member_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
    member = PurePosixPath(info.filename)
    if member.is_absolute() or ".." in member.parts:
        raise DysonPipelineError(
            f"unsafe path in Dyson archive: {info.filename!r}"
        )
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        raise DysonPipelineError(
            f"symlink member is not allowed in Dyson archive: {info.filename!r}"
        )
    parts = tuple(part for part in member.parts if part not in {"", "."})
    if not parts:
        raise DysonPipelineError(
            f"empty member path in Dyson archive: {info.filename!r}"
        )
    return parts


def extract_dyson_archives(
    raw_root: Path = DEFAULT_RAW_ROOT,
    audit_root: Path = DEFAULT_AUDIT_ROOT,
) -> dict[str, Any]:
    raw_root = Path(raw_root)
    audit_root = Path(audit_root)
    archive_paths = sorted(raw_root.glob("*.zip"))
    expected_names = {"1.zip", "2.zip", "3.zip", "4.zip"}
    actual_names = {path.name for path in archive_paths}
    if actual_names != expected_names:
        raise DysonPipelineError(
            "Dyson Dataset #1 archive set is incomplete or unexpected: "
            f"expected={sorted(expected_names)} actual={sorted(actual_names)}"
        )

    extraction_root = raw_root / "extracted"
    extraction_root.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)

    total_members = 0
    total_reused = 0
    total_extracted = 0
    total_skipped_metadata = 0
    total_uncompressed_bytes = 0
    archives: list[dict[str, Any]] = []

    print("-" * 88)
    print(" ARCHIVE MATERIALIZATION")
    print("-" * 88)

    for archive_index, archive_path in enumerate(archive_paths, start=1):
        target_root = extraction_root / archive_path.stem
        target_root.mkdir(parents=True, exist_ok=True)
        reused = 0
        extracted = 0
        skipped_metadata = 0
        member_count = 0
        uncompressed_bytes = 0

        try:
            archive_sha256 = sha256_file(archive_path)
            with zipfile.ZipFile(archive_path) as zf:
                bad_member = zf.testzip()
                if bad_member is not None:
                    raise DysonPipelineError(
                        f"CRC failure in {archive_path.name}: {bad_member}"
                    )
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    parts = _safe_member_parts(info)
                    member_path = Path(*parts)
                    if is_macos_metadata_path(member_path):
                        skipped_metadata += 1
                        continue
                    destination = target_root.joinpath(*parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    member_count += 1
                    uncompressed_bytes += int(info.file_size)

                    if (
                        destination.is_file()
                        and destination.stat().st_size == info.file_size
                        and _crc32_file(destination) == info.CRC
                    ):
                        reused += 1
                        continue

                    part = destination.with_name(destination.name + ".part")
                    try:
                        with zf.open(info, "r") as source, part.open("wb") as sink:
                            shutil.copyfileobj(source, sink, length=1024 * 1024)
                        if part.stat().st_size != info.file_size:
                            raise DysonPipelineError(
                                f"size mismatch after extracting {info.filename}: "
                                f"{part.stat().st_size}/{info.file_size}"
                            )
                        if _crc32_file(part) != info.CRC:
                            raise DysonPipelineError(
                                f"CRC mismatch after extracting {info.filename}"
                            )
                        part.replace(destination)
                        extracted += 1
                    except Exception:
                        part.unlink(missing_ok=True)
                        raise
        except (zipfile.BadZipFile, OSError) as exc:
            raise DysonPipelineError(
                f"cannot materialize Dyson archive {archive_path}: {exc}"
            ) from exc

        total_members += member_count
        total_reused += reused
        total_extracted += extracted
        total_skipped_metadata += skipped_metadata
        total_uncompressed_bytes += uncompressed_bytes
        archives.append(
            {
                "archive": archive_path.name,
                "archive_size_bytes": archive_path.stat().st_size,
                "archive_sha256": archive_sha256,
                "target_root": str(target_root),
                "member_file_count": member_count,
                "reused_member_count": reused,
                "extracted_member_count": extracted,
                "skipped_macos_metadata_count": skipped_metadata,
                "uncompressed_bytes": uncompressed_bytes,
            }
        )
        print(
            f" [{archive_index}/4] {archive_path.name} · data-members {member_count:,} · "
            f"reused {reused:,} · extracted {extracted:,} · macOS-metadata skipped {skipped_metadata:,}",
            flush=True,
        )

    report = {
        "status": "DYSON_ARCHIVES_MATERIALIZED",
        "contract": "nongtori-dyson-extraction.v1",
        "source_id": SOURCE_ID,
        "archive_count": len(archive_paths),
        "archive_names": [path.name for path in archive_paths],
        "extraction_root": str(extraction_root),
        "member_file_count": total_members,
        "reused_member_count": total_reused,
        "extracted_member_count": total_extracted,
        "skipped_macos_metadata_count": total_skipped_metadata,
        "uncompressed_bytes": total_uncompressed_bytes,
        "archives": archives,
    }
    output = audit_root / "extraction-manifest.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f" materialized {total_members:,} member files")
    print(f" manifest     {output}")
    return report


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
        path.name: path.stat().st_size
        for path in raw_root.glob("*.zip")
        if path.is_file()
    }

    command = [
        sys.executable,
        "-m",
        "gdown",
        dataset_url,
        "-O",
        str(raw_root),
        "--continue",
        "--retries",
        "3",
        "--timeout",
        "60",
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
            "command after the issue clears; --continue reuses completed/partial files and "
            "--retries 3 handles transient transfer failures."
        )

    archive_paths = sorted(path for path in raw_root.glob("*.zip") if path.is_file())
    after = {path.name: path.stat().st_size for path in archive_paths}
    reused = sum(1 for name, size in after.items() if before.get(name) == size)
    new_or_changed = len(after) - reused
    extraction = extract_dyson_archives(raw_root, audit_root)

    manifest = {
        "status": "DYSON_ACQUISITION_COMPLETE",
        "contract": "nongtori-dyson-acquisition.v2",
        "source_id": SOURCE_ID,
        "source_repo": SOURCE_REPO,
        "dataset_url": dataset_url,
        "dataset_role": DATASET_ROLE,
        "license": LICENSE,
        "commercial_training_ready": False,
        "retrieved_at": utc_now(),
        "raw_root": str(raw_root),
        "archive_file_count": len(after),
        "reused_archive_count": reused,
        "new_or_changed_archive_count": new_or_changed,
        "extraction": extraction,
        "note": (
            "Acquisition completion does not imply RGB/weight join validity. "
            "Run dyson-audit before any reference use."
        ),
    }
    output = audit_root / "acquisition-manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f" archives       {len(after):,}")
    print(f" reused archives {reused:,}")
    print(f" new/changed     {new_or_changed:,}")
    print(f" extracted files {extraction['member_file_count']:,}")
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
                f"label contains non-numeric value in {path}: {item!r}"
            ) from exc
        if not math.isfinite(number):
            invalid_non_finite += 1
            continue
        if number <= 0:
            invalid_non_positive += 1
        numeric_values.append(number)

    row_count = 0
    column_count: int | None = None
    column_stats: list[dict[str, Any]] = []
    sample_rows: list[list[float]] = []
    all_rows: list[list[float]] = []

    if array.ndim == 2:
        row_count = int(array.shape[0])
        column_count = int(array.shape[1])
        for column_index in range(column_count):
            values = []
            for item in array[:, column_index].reshape(-1):
                number = float(item)
                if math.isfinite(number):
                    values.append(number)
            column_stats.append(
                {
                    "column": column_index,
                    "count": len(values),
                    "min": min(values) if values else None,
                    "max": max(values) if values else None,
                    "mean": (sum(values) / len(values)) if values else None,
                }
            )
        all_rows = [
            [float(item) for item in row]
            for row in array.tolist()
        ]
        sample_rows = all_rows[: min(3, row_count)]
    elif array.ndim == 1:
        row_count = 0 if array.size == 0 else 1
        column_count = int(array.size) if array.size else 0
        if array.size:
            all_rows = [[float(item) for item in array.tolist()]]
            sample_rows = list(all_rows)
    elif array.ndim == 0:
        row_count = 1
        column_count = 1
        all_rows = [[float(array.item())]]
        sample_rows = list(all_rows)

    return (
        {
            "dtype": str(array.dtype),
            "shape": list(array.shape),
            "ndim": int(array.ndim),
            "numeric_value_count": int(array.size),
            "row_count": row_count,
            "column_count": column_count,
            "kind": (
                "SCALAR"
                if array.ndim == 0 or array.size == 1
                else "MATRIX"
                if array.ndim == 2
                else "VECTOR"
            ),
            "finite_count": len(numeric_values),
            "non_finite_count": invalid_non_finite,
            "non_positive_numeric_count": invalid_non_positive,
            "column_stats": column_stats,
            "sample_rows": sample_rows,
            "all_rows": all_rows,
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
    ignored_macos_metadata: list[Path] = []
    role_counts: Counter[str] = Counter()

    source_archives = [path for path in all_files if path.suffix.lower() == ".zip"]
    for path in all_files:
        if path.suffix.lower() == ".zip":
            continue
        if is_macos_metadata_path(path):
            ignored_macos_metadata.append(path)
            continue
        classified = classify_sample_file(path)
        if classified is None:
            unclassified.append(path)
            continue
        stem, role = classified
        sample_id = canonical_sample_id(path, raw_root, stem)
        grouped[sample_id][role].append(path)
        role_counts[role] += 1

    duplicate_role_rows: list[dict[str, Any]] = []
    for sample_id, roles in grouped.items():
        for role, paths in roles.items():
            if len(paths) > 1:
                duplicate_role_rows.append(
                    {
                        "sample_id": sample_id,
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
    label_column_count_counts: Counter[str] = Counter()
    total_label_rows = 0
    total_label_numeric_values = 0
    aggregate_columns: dict[int, dict[int, dict[str, float | int | None]]] = defaultdict(dict)
    sample_label_arrays: list[dict[str, Any]] = []
    invalid_non_finite_values = 0
    invalid_non_positive_values = 0
    label_value_min: float | None = None
    label_value_max: float | None = None
    label_rows: list[dict[str, Any]] = []

    exact_rgb_label = 0
    missing_rgb: list[str] = []
    missing_label: list[str] = []
    scene_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rgb_hash_to_paths: dict[str, list[str]] = defaultdict(list)

    print("=" * 88)
    print(" ICRA/DYSON WEIGHT DATA AUDIT")
    print("=" * 88)
    print(f" role        {DATASET_ROLE}")
    print(f" license     {LICENSE} · commercial_training_ready=False")
    print(f" raw root    {raw_root}")
    print(f" files       {len(all_files):,}")
    print(f" archives    {len(source_archives):,}")
    print(f" macOS meta  {len(ignored_macos_metadata):,} ignored")
    print(f" stems       {len(grouped):,}")
    print("-" * 88)

    for index, sample_id in enumerate(sorted(grouped), start=1):
        roles = grouped[sample_id]
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
            missing_rgb.append(sample_id)
        elif not has_label:
            missing_label.append(sample_id)

        label_info: dict[str, Any] | None = None
        label_values: list[float] = []
        if has_label:
            label_info, label_values = _load_numpy_label(singleton["weight_label"])
            shape_key = str(tuple(label_info["shape"]))
            label_shape_counts[shape_key] += 1
            label_dtype_counts[str(label_info["dtype"])] += 1
            label_column_count_counts[str(label_info["column_count"])] += 1
            total_label_rows += int(label_info["row_count"])
            total_label_numeric_values += int(label_info["numeric_value_count"])
            invalid_non_finite_values += int(label_info["non_finite_count"])
            invalid_non_positive_values += int(label_info["non_positive_numeric_count"])
            column_count = label_info["column_count"]
            if isinstance(column_count, int) and column_count > 0:
                for stat in label_info["column_stats"]:
                    column_index = int(stat["column"])
                    aggregate = aggregate_columns[column_count].setdefault(
                        column_index,
                        {"count": 0, "sum": 0.0, "min": None, "max": None},
                    )
                    count = int(stat["count"])
                    if count:
                        aggregate["count"] = int(aggregate["count"]) + count
                        aggregate["sum"] = float(aggregate["sum"]) + float(stat["mean"]) * count
                        local_min = float(stat["min"])
                        local_max = float(stat["max"])
                        aggregate["min"] = (
                            local_min
                            if aggregate["min"] is None
                            else min(float(aggregate["min"]), local_min)
                        )
                        aggregate["max"] = (
                            local_max
                            if aggregate["max"] is None
                            else max(float(aggregate["max"]), local_max)
                        )
            if len(sample_label_arrays) < 12:
                sample_label_arrays.append(
                    {
                        "sample_id": sample_id,
                        "path": str(singleton["weight_label"].relative_to(raw_root)),
                        "shape": label_info["shape"],
                        "rows": label_info["sample_rows"],
                    }
                )
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
                    "sample_id": sample_id,
                    **label_info,
                    "value_min": min(finite) if finite else None,
                    "value_max": max(finite) if finite else None,
                }
            )

        sample_path_for_identity = next(iter(next(iter(roles.values()))))
        sample_stem = sample_path_for_identity.name
        classified_identity = classify_sample_file(sample_path_for_identity)
        identity_stem = classified_identity[0] if classified_identity else sample_stem
        scene_id = canonical_scene_id(sample_path_for_identity, raw_root, identity_stem)
        _, view_index = split_scene_view(identity_stem)
        scene_groups[scene_id].append(
            {
                "sample_id": sample_id,
                "view_index": view_index,
                "has_rgb": has_rgb,
                "has_label": has_label,
                "label_shape": label_info["shape"] if label_info else None,
                "label_rows": label_info["all_rows"] if label_info else [],
                "rgb_path": (
                    singleton["rgb"].relative_to(raw_root).as_posix()
                    if has_rgb else None
                ),
                "bgremoved_rgb_path": (
                    singleton["bgremoved_rgb"].relative_to(raw_root).as_posix()
                    if "bgremoved_rgb" in singleton else None
                ),
            }
        )
        if has_rgb:
            rgb_path = singleton["rgb"]
            rgb_sha = sha256_file(rgb_path)
            rgb_hash_to_paths[rgb_sha].append(
                rgb_path.relative_to(raw_root).as_posix()
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
                        "sample_id": sample_id,
                        "role": role,
                        "role_index": role_index,
                        "relative_path": path.relative_to(raw_root).as_posix(),
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )

        representative_path = next(iter(next(iter(roles.values()))))
        inventory_rows.append(
            {
                "sample_id": sample_id,
                "partition": sample_partition(representative_path, raw_root),
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
                "label_row_count": (
                    int(label_info["row_count"]) if label_info else 0
                ),
                "label_numeric_value_count": (
                    int(label_info["numeric_value_count"]) if label_info else 0
                ),
                "label_non_finite_count": (
                    int(label_info["non_finite_count"]) if label_info else 0
                ),
                "label_non_positive_numeric_count": (
                    int(label_info["non_positive_numeric_count"]) if label_info else 0
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
        fieldnames = list(inventory_rows[0].keys()) if inventory_rows else ["sample_id"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(inventory_rows)

    file_manifest_path = audit_root / "file-manifest.csv"
    with file_manifest_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "sample_id",
            "role",
            "role_index",
            "relative_path",
            "size_bytes",
            "sha256",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(file_manifest_rows)

    scene_count = len(scene_groups)
    three_view_scene_count = 0
    full_label_scene_count = 0
    full_label_row_count = 0
    three_column_row_count = 0
    scene_instance_id_match_count = 0
    scene_instance_id_mismatch_count = 0
    candidate_weight_values: list[float] = []
    scene_examples: list[dict[str, Any]] = []
    mismatch_scene_details: list[dict[str, Any]] = []
    incomplete_scene_details: list[dict[str, Any]] = []
    missing_full_label_scene_details: list[dict[str, Any]] = []
    six_column_label_details: list[dict[str, Any]] = []

    for scene_id, samples in sorted(scene_groups.items()):
        by_view = {
            item["view_index"]: item
            for item in samples
            if item["view_index"] is not None
        }
        if {1, 2, 3}.issubset(by_view):
            three_view_scene_count += 1
        else:
            incomplete_scene_details.append(
                {
                    "scene_id": scene_id,
                    "views": sorted(by_view),
                    "missing_views": sorted({1, 2, 3} - set(by_view)),
                    "sample_ids": [item["sample_id"] for item in samples],
                    "label_shapes": [item["label_shape"] for item in samples],
                }
            )

        full_candidates = [
            item for item in samples
            if item["label_shape"]
            and len(item["label_shape"]) == 2
            and item["label_shape"][1] in {6, 7}
        ]
        coord_candidates = [
            item for item in samples
            if item["label_shape"]
            and len(item["label_shape"]) == 2
            and item["label_shape"][1] == 3
        ]

        if not full_candidates:
            missing_full_label_scene_details.append(
                {
                    "scene_id": scene_id,
                    "views": sorted(by_view),
                    "sample_ids": [item["sample_id"] for item in samples],
                    "label_shapes": [item["label_shape"] for item in samples],
                }
            )

        if full_candidates:
            full_label_scene_count += 1
            full_item = full_candidates[0]
            full_rows = full_item["label_rows"]
            full_label_row_count += len(full_rows)
            for row in full_rows:
                if len(row) == 7:
                    candidate_weight_values.append(float(row[1]))
                elif len(row) == 6:
                    six_column_label_details.append(
                        {
                            "scene_id": scene_id,
                            "sample_id": full_item["sample_id"],
                            "view_index": full_item["view_index"],
                            "row": row,
                        }
                    )

            full_ids = [int(round(row[0])) for row in full_rows if row]
            coord_id_sets = []
            for item in coord_candidates:
                rows = item["label_rows"]
                three_column_row_count += len(rows)
                coord_id_sets.append([int(round(row[0])) for row in rows if row])

            comparable = bool(coord_id_sets)
            if comparable and all(ids == full_ids for ids in coord_id_sets):
                scene_instance_id_match_count += 1
            elif comparable:
                scene_instance_id_mismatch_count += 1
                mismatch_scene_details.append(
                    {
                        "scene_id": scene_id,
                        "views": sorted(by_view),
                        "full_sample_id": full_item["sample_id"],
                        "full_label_shape": full_item["label_shape"],
                        "full_instance_ids": full_ids,
                        "coord_samples": [
                            {
                                "sample_id": item["sample_id"],
                                "view_index": item["view_index"],
                                "shape": item["label_shape"],
                                "instance_ids": ids,
                            }
                            for item, ids in zip(coord_candidates, coord_id_sets)
                        ],
                        "full_rows": full_rows,
                    }
                )

            if len(scene_examples) < 12:
                scene_examples.append(
                    {
                        "scene_id": scene_id,
                        "views": sorted(
                            item["view_index"]
                            for item in samples
                            if item["view_index"] is not None
                        ),
                        "full_label_shapes": [
                            item["label_shape"] for item in full_candidates
                        ],
                        "coord_label_shapes": [
                            item["label_shape"] for item in coord_candidates
                        ],
                        "full_instance_ids": full_ids[:10],
                        "coord_instance_ids": [
                            ids[:10] for ids in coord_id_sets
                        ],
                        "full_rows_sample": full_rows[:3],
                    }
                )

    physical_berry_rows: list[dict[str, Any]] = []
    view_coverage_counts: Counter[str] = Counter()
    strict_scene_ids: set[str] = set()

    for scene_id, samples in sorted(scene_groups.items()):
        full_candidates = [
            item for item in samples
            if item["label_shape"]
            and len(item["label_shape"]) == 2
            and item["label_shape"][1] == 7
        ]
        for full_item in full_candidates:
            for row in full_item["label_rows"]:
                if len(row) != 7:
                    continue
                berry_id = int(round(row[0]))
                observations: dict[int, dict[str, Any]] = {}
                for item in samples:
                    view_index = item["view_index"]
                    if view_index is None or not item["rgb_path"]:
                        continue
                    matched_row = None
                    for candidate in item["label_rows"]:
                        if candidate and int(round(candidate[0])) == berry_id:
                            matched_row = candidate
                            break
                    if matched_row is None:
                        continue
                    observations[int(view_index)] = {
                        "rgb_path": item["rgb_path"],
                        "bgremoved_rgb_path": item["bgremoved_rgb_path"],
                        "x": float(matched_row[-2]),
                        "y": float(matched_row[-1]),
                        "label_width": len(matched_row),
                    }

                matched_views = sorted(observations)
                view_coverage_counts[str(len(matched_views))] += 1
                strict_scene_ids.add(scene_id)
                physical_berry_rows.append(
                    {
                        "berry_key": f"{scene_id}#berry-{berry_id}",
                        "scene_id": scene_id,
                        "berry_instance_id": berry_id,
                        "full_sample_id": full_item["sample_id"],
                        "full_view_index": full_item["view_index"],
                        "weight_g": float(row[1]),
                        "dimension_1": float(row[2]),
                        "dimension_2": float(row[3]),
                        "dimension_3": float(row[4]),
                        "full_center_x": float(row[5]),
                        "full_center_y": float(row[6]),
                        "matched_view_count": len(matched_views),
                        "matched_view_indices": ",".join(str(v) for v in matched_views),
                        "has_view_1_2_3": all(v in observations for v in (1, 2, 3)),
                        "view_1_rgb_path": observations.get(1, {}).get("rgb_path", ""),
                        "view_1_x": observations.get(1, {}).get("x", ""),
                        "view_1_y": observations.get(1, {}).get("y", ""),
                        "view_2_rgb_path": observations.get(2, {}).get("rgb_path", ""),
                        "view_2_x": observations.get(2, {}).get("x", ""),
                        "view_2_y": observations.get(2, {}).get("y", ""),
                        "view_3_rgb_path": observations.get(3, {}).get("rgb_path", ""),
                        "view_3_x": observations.get(3, {}).get("x", ""),
                        "view_3_y": observations.get(3, {}).get("y", ""),
                        "source_schema": "STRICT_7_COLUMN",
                        "schema_interpretation": "HIGH_CONFIDENCE_INFERRED",
                        "dataset_role": DATASET_ROLE,
                        "commercial_training_ready": False,
                    }
                )

    physical_berry_manifest_path = audit_root / "physical-berry-manifest.csv"
    with physical_berry_manifest_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = (
            list(physical_berry_rows[0].keys())
            if physical_berry_rows
            else ["berry_key"]
        )
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(physical_berry_rows)

    strict_weights = [float(row["weight_g"]) for row in physical_berry_rows]
    physical_berry_summary = {
        "status": "DYSON_STRICT_PHYSICAL_BERRY_MANIFEST_READY",
        "contract": "nongtori-dyson-physical-berry-manifest.v1",
        "source_id": SOURCE_ID,
        "dataset_role": DATASET_ROLE,
        "commercial_training_ready": False,
        "schema_interpretation": {
            "columns": [
                "instance_id",
                "weight_g",
                "dimension_1",
                "dimension_2",
                "dimension_3",
                "center_x",
                "center_y",
            ],
            "confidence": "HIGH_CONFIDENCE_INFERRED",
            "basis": (
                "7-column rows repeat consistently across 498 full-label files; "
                "the second field has strawberry-plausible gram values and companion "
                "3-column rows preserve instance_id plus image coordinates."
            ),
        },
        "strict_berry_count": len(physical_berry_rows),
        "strict_scene_count": len(strict_scene_ids),
        "weight_min_g": min(strict_weights) if strict_weights else None,
        "weight_max_g": max(strict_weights) if strict_weights else None,
        "weight_mean_g": (
            sum(strict_weights) / len(strict_weights)
            if strict_weights else None
        ),
        "matched_view_count_distribution": dict(sorted(view_coverage_counts.items())),
        "all_view_1_2_3_berry_count": sum(
            1 for row in physical_berry_rows if row["has_view_1_2_3"]
        ),
        "excluded_six_column_row_count": len(six_column_label_details),
        "manifest_path": str(physical_berry_manifest_path),
        "note": (
            "Strict manifest includes only 7-column full-label rows. "
            "6-column exceptions and annotation-only samples are excluded."
        ),
    }
    (audit_root / "physical-berry-manifest.json").write_text(
        json.dumps(physical_berry_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    duplicate_rgb_hashes = {
        digest: paths
        for digest, paths in rgb_hash_to_paths.items()
        if len(paths) > 1
    }
    rgb_duplicate_file_count = sum(
        len(paths) - 1 for paths in duplicate_rgb_hashes.values()
    )
    unique_rgb_hash_count = len(rgb_hash_to_paths)

    partition_summary: dict[str, dict[str, int]] = defaultdict(lambda: {
        "sample_count": 0,
        "rgb_count": 0,
        "label_count": 0,
        "json_count": 0,
        "missing_label_count": 0,
    })
    for row in inventory_rows:
        partition = str(row["partition"])
        summary = partition_summary[partition]
        summary["sample_count"] += 1
        summary["rgb_count"] += int(bool(row["has_rgb"]))
        summary["label_count"] += int(bool(row["has_weight_label"]))
        summary["missing_label_count"] += int(
            bool(row["has_rgb"]) and not bool(row["has_weight_label"])
        )
    for sample_id, roles in grouped.items():
        representative = next(iter(next(iter(roles.values()))))
        partition = sample_partition(representative, raw_root)
        partition_summary[partition]["json_count"] += int("instance_annotation_json" in roles)

    partition_roles: dict[str, str] = {}
    for partition, summary in partition_summary.items():
        if summary["label_count"] == 0 and summary["json_count"] > 0:
            partition_roles[partition] = "ANNOTATION_ONLY_RGB_JSON"
        else:
            partition_roles[partition] = "WEIGHT_MULTIMODAL"

    paper_delta = {
        "scene_delta": scene_count - int(PUBLISHED_REFERENCE["sets"]),
        "rgb_delta": int(role_counts.get("rgb", 0)) - int(PUBLISHED_REFERENCE["images"]),
        "note": (
            "Local Google Drive package is compared to the ICRA 2022 published counts; "
            "a positive delta indicates distinct additional local package content, not SHA duplicates."
        ),
    }

    exception_report = {
        "status": "DYSON_SCENE_EXCEPTION_AUDIT_COMPLETE",
        "source_id": SOURCE_ID,
        "mismatch_scene_count": len(mismatch_scene_details),
        "mismatch_scenes": mismatch_scene_details,
        "incomplete_three_view_scene_count": len(incomplete_scene_details),
        "incomplete_three_view_scenes": incomplete_scene_details,
        "missing_full_label_scene_count": len(missing_full_label_scene_details),
        "missing_full_label_scenes": missing_full_label_scene_details,
        "six_column_row_count": len(six_column_label_details),
        "six_column_rows": six_column_label_details,
        "partition_summary": dict(sorted(partition_summary.items())),
        "partition_roles": dict(sorted(partition_roles.items())),
        "physical_berry_summary": physical_berry_summary,
        "paper_delta": paper_delta,
    }
    (audit_root / "scene-schema-exceptions.json").write_text(
        json.dumps(exception_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    scene_schema_report = {
        "status": (
            "DYSON_SCENE_SCHEMA_CANDIDATE_VERIFIED"
            if full_label_scene_count > 0
            and scene_instance_id_mismatch_count == 0
            else "DYSON_SCENE_SCHEMA_REVIEW_REQUIRED"
        ),
        "scene_count": scene_count,
        "three_view_scene_count": three_view_scene_count,
        "full_label_scene_count": full_label_scene_count,
        "full_label_row_count": full_label_row_count,
        "three_column_row_count": three_column_row_count,
        "scene_instance_id_match_count": scene_instance_id_match_count,
        "scene_instance_id_mismatch_count": scene_instance_id_mismatch_count,
        "candidate_weight_column": {
            "column_index": 1,
            "basis": (
                "7-column rows resemble [instance_id, weight_g, dimensions..., x, y]; "
                "this remains a dataset-specific schema candidate pending final acceptance."
            ),
            "count": len(candidate_weight_values),
            "min": min(candidate_weight_values) if candidate_weight_values else None,
            "max": max(candidate_weight_values) if candidate_weight_values else None,
            "mean": (
                sum(candidate_weight_values) / len(candidate_weight_values)
                if candidate_weight_values else None
            ),
        },
        "paper_delta": paper_delta,
        "partition_summary": dict(sorted(partition_summary.items())),
        "partition_roles": dict(sorted(partition_roles.items())),
        "physical_berry_summary": physical_berry_summary,
        "exception_summary": {
            "mismatch_scene_count": len(mismatch_scene_details),
            "incomplete_three_view_scene_count": len(incomplete_scene_details),
            "missing_full_label_scene_count": len(missing_full_label_scene_details),
            "six_column_row_count": len(six_column_label_details),
        },
        "rgb_identity": {
            "rgb_file_count": int(role_counts.get("rgb", 0)),
            "unique_rgb_sha256_count": unique_rgb_hash_count,
            "duplicate_rgb_file_count": rgb_duplicate_file_count,
            "duplicate_rgb_hash_group_count": len(duplicate_rgb_hashes),
            "duplicate_examples": [
                {"sha256": digest, "paths": paths[:10]}
                for digest, paths in list(duplicate_rgb_hashes.items())[:20]
            ],
        },
        "examples": scene_examples,
        "published_reference": PUBLISHED_REFERENCE,
    }
    (audit_root / "scene-schema-audit.json").write_text(
        json.dumps(scene_schema_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    aggregate_column_stats: dict[str, list[dict[str, Any]]] = {}
    for width, columns in sorted(aggregate_columns.items()):
        rows = []
        for column_index, aggregate in sorted(columns.items()):
            count = int(aggregate["count"])
            rows.append(
                {
                    "column": column_index,
                    "count": count,
                    "min": aggregate["min"],
                    "max": aggregate["max"],
                    "mean": (
                        float(aggregate["sum"]) / count
                        if count
                        else None
                    ),
                }
            )
        aggregate_column_stats[str(width)] = rows

    multi_column_present = any(
        int(width) > 1 and count > 0
        for width, count in label_column_count_counts.items()
        if width not in {"None", "0"}
    )
    label_schema_status = (
        "UNRESOLVED_MULTI_COLUMN_LABEL"
        if multi_column_present
        else "SCALAR_OR_SINGLE_COLUMN_LABEL"
    )

    label_report = {
        "status": "DYSON_WEIGHT_LABEL_AUDIT_COMPLETE",
        "source_id": SOURCE_ID,
        "dataset_role": DATASET_ROLE,
        "license": LICENSE,
        "commercial_training_ready": False,
        "label_file_count": int(role_counts.get("weight_label", 0)),
        "shape_counts": dict(sorted(label_shape_counts.items())),
        "dtype_counts": dict(sorted(label_dtype_counts.items())),
        "label_schema_status": label_schema_status,
        "total_label_rows": total_label_rows,
        "total_label_numeric_values": total_label_numeric_values,
        "column_count_counts": dict(sorted(label_column_count_counts.items())),
        "column_stats_by_width": aggregate_column_stats,
        "sample_label_arrays": sample_label_arrays,
        "published_reference": PUBLISHED_REFERENCE,
        "invalid_non_finite_values": invalid_non_finite_values,
        "non_positive_numeric_values": invalid_non_positive_values,
        "finite_numeric_min": label_value_min,
        "finite_numeric_max": label_value_max,
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
        and label_schema_status == "SCALAR_OR_SINGLE_COLUMN_LABEL"
    )

    join_report = {
        "status": (
            "DYSON_NON_COMMERCIAL_REFERENCE_READY"
            if ready
            else "DYSON_REFERENCE_SCHEMA_REVIEW_REQUIRED"
            if exact_rgb_label > 0
            else "DYSON_REFERENCE_AUDIT_WITH_EXCEPTIONS"
        ),
        "contract": "nongtori-dyson-reference-audit.v2",
        "source_id": SOURCE_ID,
        "source_repo": SOURCE_REPO,
        "dataset_url": DATASET_URL,
        "dataset_role": DATASET_ROLE,
        "license": LICENSE,
        "commercial_training_ready": False,
        "audited_at": utc_now(),
        "raw_root": str(raw_root),
        "total_files": len(all_files),
        "source_archive_count": len(source_archives),
        "source_archive_names": [path.name for path in source_archives],
        "ignored_macos_metadata_count": len(ignored_macos_metadata),
        "ignored_macos_metadata_sample": [
            path.relative_to(raw_root).as_posix()
            for path in ignored_macos_metadata[:50]
        ],
        "total_sample_ids": len(grouped),
        "published_reference": PUBLISHED_REFERENCE,
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
        "scene_schema_summary": scene_schema_report,
        "weight_label_summary": {
            "label_file_count": int(role_counts.get("weight_label", 0)),
            "shape_counts": dict(sorted(label_shape_counts.items())),
            "dtype_counts": dict(sorted(label_dtype_counts.items())),
            "label_schema_status": label_schema_status,
            "total_label_rows": total_label_rows,
            "total_label_numeric_values": total_label_numeric_values,
            "column_count_counts": dict(sorted(label_column_count_counts.items())),
            "column_stats_by_width": aggregate_column_stats,
            "sample_label_arrays": sample_label_arrays,
            "published_reference": PUBLISHED_REFERENCE,
            "invalid_non_finite_values": invalid_non_finite_values,
            "non_positive_numeric_values": invalid_non_positive_values,
            "finite_numeric_min": label_value_min,
            "finite_numeric_max": label_value_max,
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
            "scene_schema_audit": str(audit_root / "scene-schema-audit.json"),
            "scene_schema_exceptions": str(audit_root / "scene-schema-exceptions.json"),
            "physical_berry_manifest_csv": str(physical_berry_manifest_path),
            "physical_berry_manifest_json": str(audit_root / "physical-berry-manifest.json"),
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
    print(f" Label rows      {total_label_rows:,} · schema not yet assumed to be weight count")
    print(f" Numeric values  {total_label_numeric_values:,}")
    print(f" Label shapes    {dict(sorted(label_shape_counts.items()))}")
    print(f" Column widths   {dict(sorted(label_column_count_counts.items()))}")
    print(f" Schema          {label_schema_status}")
    print(
        f" Scenes          {scene_count:,} · 3-view {three_view_scene_count:,} · "
        f"full-label scenes {full_label_scene_count:,}"
    )
    print(
        f" Full-label rows {full_label_row_count:,} · 3-col rows {three_column_row_count:,} · "
        f"ID match {scene_instance_id_match_count:,} · mismatch {scene_instance_id_mismatch_count:,}"
    )
    print(
        f" RGB unique SHA  {unique_rgb_hash_count:,}/{role_counts.get('rgb', 0):,} · "
        f"duplicate files {rgb_duplicate_file_count:,}"
    )
    if candidate_weight_values:
        print(
            f" Weight cand.    column 1 · n={len(candidate_weight_values):,} · "
            f"{min(candidate_weight_values):.2f}~{max(candidate_weight_values):.2f}g · "
            f"mean {sum(candidate_weight_values)/len(candidate_weight_values):.2f}g"
        )
    print(
        f" Exceptions      ID mismatch {len(mismatch_scene_details):,} · "
        f"incomplete scenes {len(incomplete_scene_details):,} · "
        f"no-full-label {len(missing_full_label_scene_details):,} · "
        f"6-col rows {len(six_column_label_details):,}"
    )
    print(
        f" Paper delta     scenes {paper_delta['scene_delta']:+,} · "
        f"RGB {paper_delta['rgb_delta']:+,}"
    )
    print(
        f" Physical berry  strict {physical_berry_summary['strict_berry_count']:,} · "
        f"scenes {physical_berry_summary['strict_scene_count']:,} · "
        f"all 3 views {physical_berry_summary['all_view_1_2_3_berry_count']:,}"
    )
    print(
        f" View coverage   {physical_berry_summary['matched_view_count_distribution']}"
    )
    print(
        f" Paper reference images={PUBLISHED_REFERENCE['images']:,} · "
        f"berries={PUBLISHED_REFERENCE['berries']:,} · "
        f"weights={PUBLISHED_REFERENCE['weight_annotations']:,}"
    )
    print("-" * 88)
    print(f" Decision        {join_report['status']}")
    print(" Note            label columns are schema-neutral until weight column semantics are verified")
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
