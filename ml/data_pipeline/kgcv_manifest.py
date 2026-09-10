from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .hf_metadata_audit import KGCV_CLASS_NAMES, KGCV_CONFIG, KGCV_DATASET, KGCV_SPLIT, _fetch_page

MAPPING_VERSION = "MAP-RIP-002-v2"
MANIFEST_COLUMNS = [
    "sample_id", "source_id", "source_type", "source_dataset", "source_row_idx", "source_object_idx",
    "asset_path", "content_sha256", "atomic_group", "source_label", "source_decimal_stage",
    "canonical_stage", "nongtori_maturity", "nongtori_grade", "observed_harvest", "grade_reason",
    "mapping_version", "mapping_confidence", "mapping_basis", "mapping_status", "task_eligible",
    "exclusion_reason", "asset_status", "snapshot_eligible", "source_payload_json",
]

STAGE_MAPPING: dict[str, dict[str, Any]] = {
    "flower": {"canonical_stage": "FLOWER", "maturity": None, "eligible": False, "reason": "NON_FRUIT_RIPENESS_TARGET"},
    "small g": {"canonical_stage": "GREEN_SMALL", "maturity": 0, "eligible": True},
    "green": {"canonical_stage": "GREEN", "maturity": 0, "eligible": True},
    "white": {"canonical_stage": "WHITE", "maturity": 1, "eligible": True},
    "turning red": {"canonical_stage": "TURNING_UNRESOLVED", "maturity": None, "eligible": False, "reason": "UNRESOLVED_TURNING_BOUNDARY"},
    "red": {"canonical_stage": "RED_RIPE", "maturity": 4, "eligible": True},
    "overripe": {"canonical_stage": "OVERRIPE", "maturity": 4, "eligible": True, "grade": "JM", "grade_reason": "OVERRIPE"},
}


def _value_at(values: Any, index: int) -> Any:
    return values[index] if isinstance(values, list) and index < len(values) else None


def normalize_kgcv_object(*, row_idx: int, object_idx: int, source: str, objects: dict[str, Any]) -> dict[str, str]:
    raw_class = _value_at(objects.get("categories"), object_idx)
    try:
        stage = KGCV_CLASS_NAMES[int(raw_class)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"unknown KGCV class id at row={row_idx} object={object_idx}: {raw_class!r}") from exc
    spec = STAGE_MAPPING[stage]
    decimal = _value_at(objects.get("decimal_stage"), object_idx)
    payload = {"row_idx": row_idx, "object_idx": object_idx, "source": source, "source_label": stage, "decimal_stage": decimal}
    for key, values in objects.items():
        if key in {"categories", "decimal_stage"}:
            continue
        value = _value_at(values, object_idx)
        if value is not None:
            payload[key] = value

    maturity = spec.get("maturity")
    eligible = bool(spec.get("eligible"))
    mapping_status = "MAPPED" if maturity is not None else ("EXCLUDED_NON_FRUIT" if stage == "flower" else "UNRESOLVED")
    asset_status = "ASSET_NOT_MATERIALIZED"
    return {
        "sample_id": f"kgcv:{row_idx}:{object_idx}",
        "source_id": "DATA-RIP-002",
        "source_type": "EXTERNAL",
        "source_dataset": KGCV_DATASET,
        "source_row_idx": str(row_idx),
        "source_object_idx": str(object_idx),
        "asset_path": f"hf://{KGCV_DATASET}/{KGCV_CONFIG}/{KGCV_SPLIT}/row/{row_idx}",
        "content_sha256": "",
        "atomic_group": f"kgcv-row:{row_idx}",
        "source_label": stage,
        "source_decimal_stage": "" if decimal is None else str(decimal),
        "canonical_stage": str(spec["canonical_stage"]),
        "nongtori_maturity": "" if maturity is None else str(maturity),
        "nongtori_grade": str(spec.get("grade", "")),
        "observed_harvest": "",
        "grade_reason": str(spec.get("grade_reason", "")),
        "mapping_version": MAPPING_VERSION,
        "mapping_confidence": "UNMAPPED" if stage == "turning red" else "HIGH",
        "mapping_basis": "SOURCE_DEFINITION",
        "mapping_status": mapping_status,
        "task_eligible": "true" if eligible else "false",
        "exclusion_reason": str(spec.get("reason", "")),
        "asset_status": asset_status,
        "snapshot_eligible": "false",
        "source_payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
    }


def build_manifest_from_pages(pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for page in pages:
        for wrapped in page.get("rows", []):
            row_idx = int(wrapped.get("row_idx"))
            row = wrapped.get("row", {}) or {}
            objects = row.get("objects", {}) or {}
            categories = objects.get("categories", []) or []
            for object_idx in range(len(categories)):
                rows.append(normalize_kgcv_object(row_idx=row_idx, object_idx=object_idx, source=str(row.get("source", "UNKNOWN")), objects=objects))
    return rows


def fetch_all_pages(page_size: int = 100) -> list[dict[str, Any]]:
    first = _fetch_page(offset=0, length=page_size)
    total = int(first.get("num_rows_total", 0))
    pages = [first]
    for offset in range(page_size, total, page_size):
        pages.append(_fetch_page(offset=offset, length=min(page_size, total - offset)))
    return pages


def write_manifest(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def build_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    labels = Counter(row["source_label"] for row in rows)
    mapping = Counter(row["mapping_status"] for row in rows)
    eligible = sum(row["task_eligible"] == "true" for row in rows)
    return {
        "source_id": "DATA-RIP-002",
        "mapping_version": MAPPING_VERSION,
        "manifest_rows": len(rows),
        "source_label_counts": dict(sorted(labels.items())),
        "mapping_status_counts": dict(sorted(mapping.items())),
        "task_eligible_rows": eligible,
        "excluded_or_unresolved_rows": len(rows) - eligible,
        "asset_status": "ASSET_NOT_MATERIALIZED",
        "snapshot_eligible": False,
        "note": "Metadata is normalized, but image content hashes are not materialized yet. turning red stays unresolved until field calibration.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build actual object-level KGCV normalized metadata manifest.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args()
    rows = build_manifest_from_pages(fetch_all_pages(args.page_size))
    write_manifest(rows, args.output)
    summary = build_summary(rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if len(rows) == 3997 else 2


if __name__ == "__main__":
    raise SystemExit(main())
