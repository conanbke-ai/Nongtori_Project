from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .dyson_weight_reference import DATASET_ROLE, LICENSE, SOURCE_ID, DysonPipelineError, sha256_file

DEFAULT_SNAPSHOT_ID = "DYSON-REFERENCE-V001"
SNAPSHOT_SCHEMA_VERSION = 1
EXPECTED_STRICT_BERRY_COUNT = 637


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DysonPipelineError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DysonPipelineError(f"{label} must be a JSON object")
    return payload


def _safe_asset_path(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(str(relative_path).replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise DysonPipelineError(f"unsafe Dyson relative path: {relative_path!r}")
    return Path(root, *relative.parts)


def _canonical_rows_sha256(rows: list[dict[str, str]]) -> str:
    payload = "\n".join(
        "|".join(
            [
                row["berry_key"],
                row["scene_id"],
                row["berry_instance_id"],
                row["weight_g"],
                row["matched_view_indices"],
                row["source_schema"],
            ]
        )
        for row in sorted(rows, key=lambda item: item["berry_key"])
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def freeze_dyson_reference_snapshot(
    *,
    raw_root: Path,
    audit_root: Path,
    snapshot_root: Path,
    snapshot_id: str = DEFAULT_SNAPSHOT_ID,
    expected_strict_berry_count: int = EXPECTED_STRICT_BERRY_COUNT,
) -> dict[str, Any]:
    raw_root = Path(raw_root)
    audit_root = Path(audit_root)
    snapshot_root = Path(snapshot_root)
    snapshot_dir = snapshot_root / snapshot_id
    temp_dir = snapshot_root / f".{snapshot_id}.tmp"

    if snapshot_dir.exists():
        raise DysonPipelineError(
            f"immutable Dyson reference snapshot already exists: {snapshot_dir}"
        )

    physical_csv = audit_root / "physical-berry-manifest.csv"
    physical_json = audit_root / "physical-berry-manifest.json"
    scene_json = audit_root / "scene-schema-audit.json"
    exceptions_json = audit_root / "scene-schema-exceptions.json"
    acquisition_json = audit_root / "acquisition-manifest.json"
    extraction_json = audit_root / "extraction-manifest.json"

    for path, label in [
        (physical_csv, "physical berry CSV"),
        (physical_json, "physical berry summary"),
        (scene_json, "scene schema audit"),
        (exceptions_json, "scene exception audit"),
        (acquisition_json, "acquisition manifest"),
        (extraction_json, "extraction manifest"),
    ]:
        if not path.is_file():
            raise DysonPipelineError(f"missing {label}: {path}")

    summary = _load_json(physical_json, "physical berry summary")
    if summary.get("status") != "DYSON_STRICT_PHYSICAL_BERRY_MANIFEST_READY":
        raise DysonPipelineError(
            f"physical berry manifest is not ready: {summary.get('status')!r}"
        )
    if summary.get("dataset_role") != DATASET_ROLE:
        raise DysonPipelineError("Dyson dataset role drifted from NON_COMMERCIAL_REFERENCE")
    if summary.get("commercial_training_ready") is not False:
        raise DysonPipelineError("Dyson commercial training guard must remain false")

    berry_count = int(summary.get("strict_berry_count") or 0)
    if berry_count != expected_strict_berry_count:
        raise DysonPipelineError(
            f"strict berry count drifted: {berry_count}/{expected_strict_berry_count}"
        )
    if int(summary.get("excluded_six_column_row_count") or 0) != 4:
        raise DysonPipelineError("expected four excluded 6-column exception rows")

    with physical_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != berry_count:
        raise DysonPipelineError(
            f"physical berry CSV row count mismatch: {len(rows)}/{berry_count}"
        )

    berry_keys: set[str] = set()
    unique_asset_paths: set[str] = set()
    view_coverage = Counter()
    for row in rows:
        berry_key = str(row.get("berry_key") or "").strip()
        if not berry_key or berry_key in berry_keys:
            raise DysonPipelineError(f"invalid or duplicate berry_key: {berry_key!r}")
        berry_keys.add(berry_key)
        if row.get("source_schema") != "STRICT_7_COLUMN":
            raise DysonPipelineError(f"non-strict source schema in {berry_key}")
        if row.get("dataset_role") != DATASET_ROLE:
            raise DysonPipelineError(f"dataset role mismatch in {berry_key}")
        if str(row.get("commercial_training_ready")) != "False":
            raise DysonPipelineError(f"commercial training guard mismatch in {berry_key}")
        try:
            weight_g = float(row["weight_g"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DysonPipelineError(f"invalid weight in {berry_key}") from exc
        if weight_g <= 0:
            raise DysonPipelineError(f"non-positive weight in {berry_key}: {weight_g}")

        matched_views = [
            token for token in str(row.get("matched_view_indices") or "").split(",") if token
        ]
        if len(matched_views) not in {2, 3}:
            raise DysonPipelineError(
                f"unexpected matched-view count in {berry_key}: {matched_views}"
            )
        view_coverage[str(len(matched_views))] += 1

        for view in (1, 2, 3):
            relative_path = str(row.get(f"view_{view}_rgb_path") or "").strip()
            if not relative_path:
                continue
            unique_asset_paths.add(relative_path)

    expected_distribution = {
        str(key): int(value)
        for key, value in dict(summary.get("matched_view_count_distribution") or {}).items()
    }
    if dict(sorted(view_coverage.items())) != dict(sorted(expected_distribution.items())):
        raise DysonPipelineError(
            f"view coverage drifted: {dict(view_coverage)} != {expected_distribution}"
        )

    asset_rows: list[dict[str, Any]] = []
    for relative_path in sorted(unique_asset_paths):
        asset_path = _safe_asset_path(raw_root, relative_path)
        if not asset_path.is_file():
            raise DysonPipelineError(f"referenced Dyson RGB asset is missing: {asset_path}")
        asset_rows.append(
            {
                "relative_path": relative_path,
                "size_bytes": asset_path.stat().st_size,
                "sha256": sha256_file(asset_path),
            }
        )

    snapshot_root.mkdir(parents=True, exist_ok=True)
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    try:
        frozen_manifest = temp_dir / "physical-berry-manifest.csv"
        frozen_manifest.write_bytes(physical_csv.read_bytes())

        asset_manifest = temp_dir / "rgb-asset-manifest.csv"
        with asset_manifest.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["relative_path", "size_bytes", "sha256"],
            )
            writer.writeheader()
            writer.writerows(asset_rows)

        descriptor = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "snapshot_type": "NON_COMMERCIAL_REFERENCE",
            "task": "STRAWBERRY_WEIGHT_REFERENCE",
            "status": "DYSON_REFERENCE_SNAPSHOT_FROZEN",
            "source_id": SOURCE_ID,
            "dataset_role": DATASET_ROLE,
            "license": LICENSE,
            "commercial_training_ready": False,
            "canonical_commercial_training_merge_allowed": False,
            "strict_berry_count": berry_count,
            "strict_scene_count": int(summary.get("strict_scene_count") or 0),
            "matched_view_count_distribution": dict(sorted(view_coverage.items())),
            "all_view_1_2_3_berry_count": int(summary.get("all_view_1_2_3_berry_count") or 0),
            "excluded_six_column_row_count": 4,
            "referenced_unique_rgb_asset_count": len(asset_rows),
            "berry_rows_sha256": _canonical_rows_sha256(rows),
            "upstream_artifact_hashes": {
                "physical-berry-manifest.csv": sha256_file(physical_csv),
                "physical-berry-manifest.json": sha256_file(physical_json),
                "scene-schema-audit.json": sha256_file(scene_json),
                "scene-schema-exceptions.json": sha256_file(exceptions_json),
                "acquisition-manifest.json": sha256_file(acquisition_json),
                "extraction-manifest.json": sha256_file(extraction_json),
            },
            "artifact_hashes": {
                "physical-berry-manifest.csv": sha256_file(frozen_manifest),
                "rgb-asset-manifest.csv": sha256_file(asset_manifest),
            },
            "materialized_asset_root": str(raw_root),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "note": (
                "Immutable reference-only freeze. No train/validation/test split is created, "
                "and this snapshot must not be merged into commercial/canonical training assets."
            ),
        }
        (temp_dir / "REFERENCE_SNAPSHOT.json").write_text(
            json.dumps(descriptor, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_dir.replace(snapshot_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return {
        **descriptor,
        "snapshot_dir": str(snapshot_dir),
    }
