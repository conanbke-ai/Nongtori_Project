from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ml.observability import RunLogger
from ml.ripeness_baseline.train_v001 import (
    EXPECTED_ASSIGNMENT_SHA256,
    EXPECTED_PHYSICAL_IMAGES,
    EXPECTED_SAMPLES,
    EXPECTED_SPLIT_COUNTS,
    build_crop_cache,
)

SNAPSHOT_ID = "KGCV-RIPENESS-V001"
DEFAULT_CACHE_ROOT = Path("artifacts/_dataset_cache") / SNAPSHOT_ID


def _load_verified_cache(root: Path, logger: RunLogger) -> dict[str, Any] | None:
    manifest = root / "cache_manifest.json"
    if not manifest.exists():
        return None

    try:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.emit(
            "WARNING",
            "CACHE_MANIFEST_INVALID",
            "shared snapshot cache manifest could not be read",
            phase="CACHE_BUILD",
            cache_root=str(root),
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return None

    if meta.get("physical_images") != EXPECTED_PHYSICAL_IMAGES:
        return None
    if meta.get("samples") != EXPECTED_SAMPLES:
        return None
    if meta.get("split_counts") != EXPECTED_SPLIT_COUNTS:
        return None
    if meta.get("assignment_sha256") != EXPECTED_ASSIGNMENT_SHA256:
        return None
    if meta.get("errors"):
        return None

    records = meta.get("records") or []
    if len(records) != EXPECTED_SAMPLES:
        return None

    # Normalize record paths to the canonical shared cache root. This also
    # allows a previously generated crop directory to be promoted/copied into
    # the shared cache without keeping old experiment-specific path strings.
    missing: list[str] = []
    normalized: list[dict[str, Any]] = []
    for record in records:
        filename = Path(str(record.get("path", ""))).name
        if not filename:
            return None
        crop_path = root / filename
        if not crop_path.exists():
            missing.append(filename)
            if len(missing) >= 10:
                break
        updated = dict(record)
        updated["path"] = str(crop_path)
        normalized.append(updated)

    if missing:
        logger.emit(
            "WARNING",
            "CACHE_FILES_MISSING",
            "shared snapshot cache is incomplete; rebuilding",
            phase="CACHE_BUILD",
            cache_root=str(root),
            missing_examples=missing,
        )
        return None

    meta["records"] = normalized
    logger.emit(
        "INFO",
        "CACHE_REUSED",
        "reusing verified shared immutable snapshot cache",
        phase="CACHE_BUILD",
        snapshot_id=SNAPSHOT_ID,
        cache_root=str(root),
        physical_images=meta["physical_images"],
        samples=meta["samples"],
        split_counts=meta["split_counts"],
        assignment_sha256=meta["assignment_sha256"],
    )
    return meta


def get_or_build_snapshot_cache(
    logger: RunLogger,
    root: Path = DEFAULT_CACHE_ROOT,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    cached = _load_verified_cache(root, logger)
    if cached is not None:
        return cached

    logger.emit(
        "INFO",
        "CACHE_MISS",
        "verified shared snapshot cache not found; building once",
        phase="CACHE_BUILD",
        snapshot_id=SNAPSHOT_ID,
        cache_root=str(root),
    )
    return build_crop_cache(root, logger)
