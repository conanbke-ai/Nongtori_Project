from __future__ import annotations

import json
import shutil
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

PREFERRED_LEGACY_CACHE_ROOTS = [
    Path("artifacts/ripeness-v002-lr-screening/crops"),
    Path("artifacts/ripeness-v003-patience/crops"),
    Path("artifacts/ripeness-baseline-v001/crops"),
]


def _resolve_record_path(root: Path, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    original = Path(raw_path)
    if original.is_file():
        return original
    rebased = root / original.name
    return rebased if rebased.is_file() else None


def _validate_cache(
    root: Path,
    *,
    persist_rebased_paths: bool = True,
) -> tuple[dict[str, Any] | None, str | None]:
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

    if rebased_count and persist_rebased_paths:
        manifest_path.write_text(
            json.dumps(meta, ensure_ascii=False),
            encoding="utf-8",
        )
    if rebased_count:
        meta["local_paths_rebased"] = rebased_count

    return meta, None


def _legacy_candidates(canonical_root: Path) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    for candidate in PREFERRED_LEGACY_CACHE_ROOTS:
        resolved = candidate.resolve()
        if candidate != canonical_root and resolved not in seen:
            seen.add(resolved)
            candidates.append(candidate)

    artifacts = Path("artifacts")
    if artifacts.exists():
        for manifest in sorted(artifacts.glob("**/crops/cache_manifest.json")):
            candidate = manifest.parent
            resolved = candidate.resolve()
            if candidate != canonical_root and resolved not in seen:
                seen.add(resolved)
                candidates.append(candidate)

    return candidates


def _adopt_existing_cache(
    canonical_root: Path,
    logger: RunLogger,
) -> dict[str, Any] | None:
    for candidate in _legacy_candidates(canonical_root):
        meta, reason = _validate_cache(candidate, persist_rebased_paths=False)
        if meta is None:
            logger.emit(
                "INFO",
                "LEGACY_CACHE_SKIPPED",
                "legacy crop cache candidate was not eligible for adoption",
                phase="CACHE",
                candidate=str(candidate),
                reason=reason,
            )
            continue

        if canonical_root.exists():
            if canonical_root.is_dir() and not any(canonical_root.iterdir()):
                canonical_root.rmdir()
            else:
                raise RuntimeError(
                    f"canonical cache target already exists but is not a verified cache: "
                    f"{canonical_root}. Refusing to overwrite it."
                )

        canonical_root.parent.mkdir(parents=True, exist_ok=True)
        logger.emit(
            "INFO",
            "LEGACY_CACHE_ADOPTING",
            "moving verified legacy crop materialization into canonical snapshot directory",
            phase="CACHE",
            source=str(candidate),
            target=str(canonical_root),
            samples=meta["samples"],
            assignment_sha256=meta["assignment_sha256"],
        )
        shutil.move(str(candidate), str(canonical_root))

        adopted, adopted_reason = _validate_cache(canonical_root)
        if adopted is None:
            raise RuntimeError(
                f"adopted cache failed canonical verification: {adopted_reason}"
            )
        logger.emit(
            "INFO",
            "LEGACY_CACHE_ADOPTED",
            "verified legacy crop materialization promoted to canonical snapshot cache",
            phase="CACHE",
            source=str(candidate),
            target=str(canonical_root),
            samples=adopted["samples"],
            assignment_sha256=adopted["assignment_sha256"],
            local_paths_rebased=adopted.get("local_paths_rebased", 0),
        )
        return adopted

    return None


def load_or_build_crop_cache(
    cache_root: Path = CANONICAL_CACHE_ROOT,
    logger: RunLogger | None = None,
    *,
    allow_download: bool = False,
    auto_adopt_legacy: bool = True,
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

    if auto_adopt_legacy:
        adopted = _adopt_existing_cache(cache_root, logger)
        if adopted is not None:
            return adopted

    if not allow_download:
        searched = [str(p) for p in _legacy_candidates(cache_root)]
        raise RuntimeError(
            f"verified canonical snapshot cache unavailable at {cache_root}: {reason}. "
            f"No adoptable verified legacy cache was found. Searched: {searched}. "
            "Use --allow-download only if no local verified materialization exists."
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
