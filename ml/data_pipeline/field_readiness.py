from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ALLOWED_FARMS = {"M", "C1", "C2", "U"}
ALLOWED_CLASSES = {"STR", "LEF"}
ALLOWED_DATA_TYPES = {"R", "T", "M", "V"}
ALLOWED_VIEW_TYPES = {"RT45", "F"}
ALLOWED_OCCLUSION = {0, 1, 2}
ALLOWED_GRADES = {"SP", "HI", "MD", "JM", "NA"}
ALLOWED_MATURITY = {0, 1, 2, 3, 4}

COMMON_REQUIRED = [
    "Date", "ID", "Group_ID", "Original_No", "Farm", "Zone", "Variety",
    "Class", "DataType", "View_Type", "Occlusion", "Grade", "Final_Name",
]


def blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def to_int(value: Any) -> int | None:
    if blank(value):
        return None
    try:
        number = float(str(value).strip())
        return int(number) if number.is_integer() else None
    except (TypeError, ValueError):
        return None


def classify_row(row: dict[str, Any], source_row: int) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []
    invalid = False

    cls = str(row.get("Class", "") or "").strip()
    farm = str(row.get("Farm", "") or "").strip()
    dtype = str(row.get("DataType", "") or "").strip()
    view = str(row.get("View_Type", "") or "").strip()
    grade = str(row.get("Grade", "") or "").strip()
    occ = to_int(row.get("Occlusion"))
    maturity = to_int(row.get("Maturity"))

    required = list(COMMON_REQUIRED)
    if cls == "STR":
        required.append("Maturity")

    missing = [name for name in required if blank(row.get(name))]
    if missing:
        reasons.append("MISSING_REQUIRED:" + ",".join(missing))

    if farm == "C":
        invalid = True
        reasons.append("GROUP_SCOPE_C_NOT_STORED_FARM")
    elif farm and farm not in ALLOWED_FARMS:
        invalid = True
        reasons.append(f"INVALID_FARM:{farm}")

    if cls and cls not in ALLOWED_CLASSES:
        invalid = True
        reasons.append(f"INVALID_CLASS:{cls}")
    if dtype and dtype not in ALLOWED_DATA_TYPES:
        invalid = True
        reasons.append(f"INVALID_DATATYPE:{dtype}")
    if view and view not in ALLOWED_VIEW_TYPES:
        invalid = True
        reasons.append(f"INVALID_VIEW_TYPE:{view}")
    if not blank(row.get("Occlusion")) and occ not in ALLOWED_OCCLUSION:
        invalid = True
        reasons.append(f"INVALID_OCCLUSION:{row.get('Occlusion')}")
    if grade and grade not in ALLOWED_GRADES:
        invalid = True
        reasons.append(f"INVALID_GRADE:{grade}")
    if cls == "STR" and not blank(row.get("Maturity")) and maturity not in ALLOWED_MATURITY:
        invalid = True
        reasons.append(f"INVALID_MATURITY:{row.get('Maturity')}")

    original_no = str(row.get("Original_No", "") or "").strip()
    date = str(row.get("Date", "") or "").strip().replace(".", "").replace("-", "")
    if original_no and len(date) == 8 and original_no[:8].isdigit() and original_no[:8] != date:
        warnings.append("DATE_ORIGINAL_NO_TIMESTAMP_MISMATCH")

    readiness = "INVALID_FOR_TRAINING" if invalid else "PARTIAL" if missing else "READY_METADATA"
    return {
        "source_row": source_row,
        "id": str(row.get("ID", "") or "").strip(),
        "group_id": str(row.get("Group_ID", "") or "").strip(),
        "original_no": original_no,
        "final_name": str(row.get("Final_Name", "") or "").strip(),
        "class": cls,
        "farm": farm,
        "readiness": readiness,
        "reason_codes": reasons,
        "warnings": warnings,
    }


def evaluate_rows(rows: Iterable[dict[str, Any]], first_source_row: int = 2) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evaluated: list[dict[str, Any]] = []
    original_index: defaultdict[str, list[int]] = defaultdict(list)
    final_name_index: defaultdict[str, list[int]] = defaultdict(list)

    for offset, row in enumerate(rows):
        if all(blank(v) for v in row.values()):
            continue
        result = classify_row(row, first_source_row + offset)
        evaluated.append(result)
        if result["original_no"]:
            original_index[result["original_no"]].append(len(evaluated) - 1)
        if result["final_name"]:
            final_name_index[result["final_name"]].append(len(evaluated) - 1)

    for value, indexes in original_index.items():
        if len(indexes) > 1:
            for index in indexes:
                evaluated[index]["warnings"].append(f"DUPLICATE_ORIGINAL_NO:{value}")
    for value, indexes in final_name_index.items():
        if len(indexes) > 1:
            for index in indexes:
                evaluated[index]["warnings"].append(f"DUPLICATE_FINAL_NAME:{value}")

    readiness_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    farm_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()

    for result in evaluated:
        readiness_counts[result["readiness"]] += 1
        if result["class"]:
            class_counts[result["class"]] += 1
        if result["farm"]:
            farm_counts[result["farm"]] += 1
        reason_counts.update(result["reason_codes"])
        warning_counts.update(result["warnings"])

    summary = {
        "rows_evaluated": len(evaluated),
        "readiness_counts": dict(readiness_counts),
        "by_class": dict(class_counts),
        "by_farm": dict(farm_counts),
        "reason_counts": dict(reason_counts),
        "warning_counts": dict(warning_counts),
        "training_ready_claimed": False,
        "note": "READY_METADATA does not imply physical media existence or TRAINING_READY.",
    }
    return evaluated, summary


def audit_csv(csv_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError("CSV header is missing")
        evaluated, summary = evaluate_rows(reader)

    summary = {"source": str(csv_path), **summary}
    (output_dir / "readiness_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "readiness_rows.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = [
            "source_row", "id", "group_id", "original_no", "final_name", "class", "farm",
            "readiness", "reason_codes", "warnings",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in evaluated:
            writer.writerow({
                **row,
                "reason_codes": "|".join(row["reason_codes"]),
                "warnings": "|".join(row["warnings"]),
            })
    return summary
