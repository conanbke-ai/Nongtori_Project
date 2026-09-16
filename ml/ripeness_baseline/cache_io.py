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
    missing = [r.get("path") for r in records if not r.get("path") or not Path(r["path"]).is_file()]
    if missing:
        return None, f"crop files missing: {len(missing)}"
    return meta, None


def load_or_build_crop_cache(
    cache_root: Path,
    logger: RunLogger,
    *,
    allow_download: bool = True,
) -> dict[str, Any]:
    meta, reason = _validate_cache(cache_root)
    if meta is not None:
        logger.emit(
            "INFO",
            "CACHE_REUSED",
            "verified immutable KGCV crop cache; remote download skipped",
            phase="CACHE",
            cache_root=str(cache_root),
            physical_images=meta["physical_images"],
            samples=meta["samples"],
            split_counts=meta["split_counts"],
            assignment_sha256=meta["assignment_sha256"],
        )
        return meta

    if not allow_download:
        raise RuntimeError(
            f"verified cache unavailable at {cache_root}: {reason}. "
            "Build it once or pass the correct --cache-root."
        )

    logger.emit(
        "WARNING",
        "CACHE_BUILD_REQUIRED",
        "verified cache unavailable; building it once from remote source",
        phase="CACHE",
        cache_root=str(cache_root),
        reason=reason,
    )
    meta = build_crop_cache(cache_root, logger)
    verified, verify_reason = _validate_cache(cache_root)
    if verified is None:
        raise RuntimeError(f"newly built cache failed verification: {verify_reason}")
    return verified
