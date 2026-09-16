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
CANONICAL_CACHE_ROOT = (
    Path("data")
    / "snapshots"
    / SNAPSHOT_ID
    / "materialized"
    / "ripeness-crops"
)


def _resolve_record_path(root: Path, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    original = Path(raw_path)
    if original.is_file():
        return original

    # Legacy experiment manifests stored paths such as
    # artifacts/ripeness-v002-lr-screening/crops/123_0.jpg.
    # After moving the immutable crop set into the canonical snapshot
    # materialization directory, resolve by the stable crop filename.
    rebased = root / original.name
    return rebased if rebased.is_file() else None


def _validate_cache(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    manifest_path = root / "cache_manifest.json"
    if not manifest_path.exists():
        return None, "manifest missing"
    try:
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"manifest unreadable: {exc}"
    if meta.get("errors"):
        return None, f"manifest contains {len(meta['errors'])} errors"
    if meta.get("physical_images") != EXPECTED_PHYSICAL_IMAGES:
        return None, "physical image count mismatch"
    if meta.get("samples") != EXPECTED_SAMPLES:
        return None, "sample count mismatch"
    if meta.get("split_counts") != EXPECTED_SPLIT_COUNTS:
        return None, "split count mismatch"
    if meta.get("assignment_sha256") != EXPECTED_ASSIGNMENT_SHA256:
        return None, "assignment checksum mismatch"

    records = meta.get("records") or []
    if len(records) != EXPECTED_SAMPLES:
        return None, "record count mismatch"

    rebased_count = 0
    missing: list[str | None] = []
    for record in records:
        raw_path = record.get("path")
        resolved = _resolve_record_path(root, raw_path)
        if resolved is None:
            missing.append(raw_path)
            continue
        resolved_text = str(resolved)
        if raw_path != resolved_text:
            record["path"] = resolved_text
            rebased_count += 1

    if missing:
        return None, f"crop files missing: {len(missing)}"

    # Path relocation is not part of the immutable assignment identity.
    # Persisting rebased local paths lets a previously materialized snapshot
    # move from an experiment artifact directory into data/snapshots safely.
    if rebased_count:
        manifest_path.write_text(
            json.dumps(meta, ensure_ascii=False),
            encoding="utf-8",
        )
        meta["local_paths_rebased"] = rebased_count

    return meta, None


def load_or_build_crop_cache(
    cache_root: Path = CANONICAL_CACHE_ROOT,
    logger: RunLogger | None = None,
    *,
    allow_download: bool = False,
) -> dict[str, Any]:
    if logger is None:
        raise ValueError("logger is required")

    meta, reason = _validate_cache(cache_root)
    if meta is not None:
        logger.emit(
            "INFO",
            "CACHE_REUSED",
            "verified immutable snapshot materialization; remote download skipped",
            phase="CACHE",
            snapshot_id=SNAPSHOT_ID,
            cache_root=str(cache_root),
            physical_images=meta["physical_images"],
            samples=meta["samples"],
            split_counts=meta["split_counts"],
            assignment_sha256=meta["assignment_sha256"],
            local_paths_rebased=meta.get("local_paths_rebased", 0),
        )
        return meta

    if not allow_download:
        raise RuntimeError(
            f"verified canonical snapshot cache unavailable at {cache_root}: {reason}. "
            "Move/adopt an existing verified crop materialization there, or explicitly "
            "pass --allow-download to build it once."
        )

    logger.emit(
        "WARNING",
        "CACHE_BUILD_REQUIRED",
        "canonical snapshot materialization unavailable; building it once from remote source",
        phase="CACHE",
        snapshot_id=SNAPSHOT_ID,
        cache_root=str(cache_root),
        reason=reason,
    )
    build_crop_cache(cache_root, logger)
    verified, verify_reason = _validate_cache(cache_root)
    if verified is None:
        raise RuntimeError(f"newly built cache failed verification: {verify_reason}")
    return verified
