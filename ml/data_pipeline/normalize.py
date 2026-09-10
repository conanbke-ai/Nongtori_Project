from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FIELD_MAPPING_VERSION = "MAP-FIELD-001-v1"
ALLOWED_GRADES = {"SP", "HI", "MD", "JM", "NA"}
ALLOWED_HEALTH = {"NOR", "MIT", "MIT_R", "ANT", "MAL", "OTH"}
FIELD_STAGE_BY_MATURITY = {0: "GREEN", 1: "WHITE", 2: "TURNING_MID", 3: "TURNING_LATE", 4: "RED_RIPE"}

NORMALIZED_COLUMNS = [
    "sample_id", "source_id", "source_type", "asset_path", "content_sha256", "atomic_group",
    "source_label", "canonical_stage", "nongtori_maturity", "nongtori_grade", "health",
    "observed_harvest", "grade_reason", "mapping_version", "mapping_confidence", "mapping_basis",
    "task_eligible", "exclusion_reason", "source_payload_json",
]


class LabelContractError(ValueError):
    pass


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _optional_int(value: Any) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError as exc:
        raise LabelContractError(f"invalid integer label: {value!r}") from exc


def normalize_field_row(row: dict[str, Any], *, source_id: str = "DATA-FIELD-001", mapping_version: str = FIELD_MAPPING_VERSION) -> dict[str, str]:
    sample_id = _text(row.get("ID"))
    if not sample_id:
        raise LabelContractError("field row requires ID")
    maturity = _optional_int(row.get("Maturity"))
    if maturity not in FIELD_STAGE_BY_MATURITY:
        raise LabelContractError(f"field row {sample_id}: Maturity must be 0..4")
    grade = _text(row.get("Grade")).upper()
    if grade not in ALLOWED_GRADES:
        raise LabelContractError(f"field row {sample_id}: unsupported Grade {grade!r}")
    health = _text(row.get("Health")).upper()
    if health and health not in ALLOWED_HEALTH:
        raise LabelContractError(f"field row {sample_id}: unsupported Health {health!r}")
    if health == "MAL" and grade != "JM":
        raise LabelContractError(f"field row {sample_id}: Health=MAL requires Grade=JM by field contract")

    return {
        "sample_id": sample_id,
        "source_id": source_id,
        "source_type": "FIELD",
        "asset_path": _text(row.get("Final_Name")) or _text(row.get("Original_No")),
        "content_sha256": _text(row.get("content_sha256")).lower(),
        "atomic_group": _text(row.get("Group_ID")) or sample_id,
        "source_label": _text(row.get("Maturity")),
        "canonical_stage": FIELD_STAGE_BY_MATURITY[maturity],
        "nongtori_maturity": str(maturity),
        "nongtori_grade": grade,
        "health": health,
        "observed_harvest": "true" if grade != "NA" else "false",
        "grade_reason": "MALFORMED" if health == "MAL" else "",
        "mapping_version": mapping_version,
        "mapping_confidence": "HIGH",
        "mapping_basis": "FIELD_POLICY",
        "task_eligible": "true",
        "exclusion_reason": "",
        "source_payload_json": json.dumps(row, ensure_ascii=False, sort_keys=True),
    }


@dataclass(frozen=True)
class ExternalMapping:
    source_id: str
    mapping_version: str
    labels: dict[str, dict[str, Any]]

    @classmethod
    def from_json(cls, path: Path) -> "ExternalMapping":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(str(data["source_id"]), str(data["mapping_version"]), {str(k): dict(v) for k, v in data["labels"].items()})


def normalize_external_row(row: dict[str, Any], mapping: ExternalMapping, *, label_column: str = "label", sample_id_column: str = "sample_id", asset_column: str = "asset_path", hash_column: str = "content_sha256", group_column: str = "group_id") -> dict[str, str]:
    source_label = _text(row.get(label_column))
    spec = mapping.labels.get(source_label) or {
        "canonical_stage": "", "maturity": None, "grade": "", "confidence": "UNMAPPED",
        "basis": "SOURCE_DEFINITION", "task_eligible": False, "exclusion_reason": "UNMAPPED_SOURCE_LABEL",
    }
    sample_id = _text(row.get(sample_id_column)) or _text(row.get(asset_column))
    if not sample_id:
        raise LabelContractError("external row requires sample_id or asset_path")

    canonical_stage = _text(spec.get("canonical_stage"))
    maturity = spec.get("maturity")
    grade = _text(spec.get("grade")).upper()
    if canonical_stage == "OVERRIPE":
        maturity = 4
        grade = "JM"

    return {
        "sample_id": sample_id,
        "source_id": mapping.source_id,
        "source_type": "EXTERNAL",
        "asset_path": _text(row.get(asset_column)),
        "content_sha256": _text(row.get(hash_column)).lower(),
        "atomic_group": _text(row.get(group_column)) or sample_id,
        "source_label": source_label,
        "canonical_stage": canonical_stage,
        "nongtori_maturity": "" if maturity is None else str(int(maturity)),
        "nongtori_grade": grade,
        "health": "",
        "observed_harvest": "",
        "grade_reason": _text(spec.get("grade_reason")) or ("OVERRIPE" if canonical_stage == "OVERRIPE" else ""),
        "mapping_version": mapping.mapping_version,
        "mapping_confidence": _text(spec.get("confidence")) or "MEDIUM",
        "mapping_basis": _text(spec.get("basis")) or "SOURCE_DEFINITION",
        "task_eligible": "true" if bool(spec.get("task_eligible", maturity is not None)) else "false",
        "exclusion_reason": _text(spec.get("exclusion_reason")),
        "source_payload_json": json.dumps(row, ensure_ascii=False, sort_keys=True),
    }


def write_normalized(rows: Iterable[dict[str, str]], output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=NORMALIZED_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in NORMALIZED_COLUMNS})
    return output_path


def normalize_field_csv(input_path: Path, output_path: Path, *, source_id: str = "DATA-FIELD-001") -> Path:
    with Path(input_path).open(encoding="utf-8-sig", newline="") as f:
        rows = [normalize_field_row(row, source_id=source_id) for row in csv.DictReader(f)]
    return write_normalized(rows, output_path)


def normalize_external_csv(input_path: Path, output_path: Path, mapping_path: Path, *, label_column: str = "label", sample_id_column: str = "sample_id", asset_column: str = "asset_path", hash_column: str = "content_sha256", group_column: str = "group_id") -> Path:
    mapping = ExternalMapping.from_json(mapping_path)
    with Path(input_path).open(encoding="utf-8-sig", newline="") as f:
        rows = [normalize_external_row(row, mapping, label_column=label_column, sample_id_column=sample_id_column, asset_column=asset_column, hash_column=hash_column, group_column=group_column) for row in csv.DictReader(f)]
    return write_normalized(rows, output_path)
