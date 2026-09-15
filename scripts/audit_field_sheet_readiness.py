from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

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


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _to_int(value: Any) -> int | None:
    if _blank(value):
        return None
    try:
        number = float(str(value).strip())
        if not number.is_integer():
            return None
        return int(number)
    except (TypeError, ValueError):
        return None


def classify(row: dict[str, Any], source_row: int) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []
    invalid = False

    cls = str(row.get("Class", "")).strip()
    farm = str(row.get("Farm", "")).strip()
    dtype = str(row.get("DataType", "")).strip()
    view = str(row.get("View_Type", "")).strip()
    grade = str(row.get("Grade", "")).strip()
    occ = _to_int(row.get("Occlusion"))
    maturity = _to_int(row.get("Maturity"))

    required = list(COMMON_REQUIRED)
    if cls == "STR":
        required.append("Maturity")

    missing = [name for name in required if _blank(row.get(name))]
    if missing:
        reasons.append("MISSING_REQUIRED:" + ",".join(missing))

    if farm and farm not in ALLOWED_FARMS:
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
    if not _blank(row.get("Occlusion")) and occ not in ALLOWED_OCCLUSION:
        invalid = True
        reasons.append(f"INVALID_OCCLUSION:{row.get('Occlusion')}")
    if grade and grade not in ALLOWED_GRADES:
        invalid = True
        reasons.append(f"INVALID_GRADE:{grade}")
    if cls == "STR" and not _blank(row.get("Maturity")) and maturity not in ALLOWED_MATURITY:
        invalid = True
        reasons.append(f"INVALID_MATURITY:{row.get('Maturity')}")

    if farm == "C":
        invalid = True
        reasons.append("GROUP_SCOPE_C_NOT_STORED_FARM")

    original_no = str(row.get("Original_No", "")).strip()
    date = str(row.get("Date", "")).strip().replace(".", "").replace("-", "")
    if original_no and len(date) == 8 and original_no[:8].isdigit() and original_no[:8] != date:
        warnings.append("DATE_ORIGINAL_NO_TIMESTAMP_MISMATCH")

    if invalid:
        readiness = "INVALID_FOR_TRAINING"
    elif missing:
        readiness = "PARTIAL"
    else:
        readiness = "READY_METADATA"

    return {
        "source_row": source_row,
        "id": str(row.get("ID", "")).strip(),
        "group_id": str(row.get("Group_ID", "")).strip(),
        "class": cls,
        "farm": farm,
        "readiness": readiness,
        "reason_codes": reasons,
        "warnings": warnings,
    }


def audit(csv_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_out: list[dict[str, Any]] = []
    readiness_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    farm_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError("CSV header is missing")
        for source_row, row in enumerate(reader, start=2):
            if all(_blank(v) for v in row.values()):
                continue
            result = classify(row, source_row)
            rows_out.append(result)
            readiness_counts[result["readiness"]] += 1
            if result["class"]:
                class_counts[result["class"]] += 1
            if result["farm"]:
                farm_counts[result["farm"]] += 1
            for reason in result["reason_codes"]:
                reason_counts[reason] += 1
            for warning in result["warnings"]:
                warning_counts[warning] += 1

    summary = {
        "source": str(csv_path),
        "rows_evaluated": len(rows_out),
        "readiness_counts": dict(readiness_counts),
        "by_class": dict(class_counts),
        "by_farm": dict(farm_counts),
        "reason_counts": dict(reason_counts),
        "warning_counts": dict(warning_counts),
        "training_ready_claimed": False,
        "note": "READY_METADATA does not imply physical media existence or TRAINING_READY.",
    }

    (output_dir / "readiness_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "readiness_rows.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["source_row", "id", "group_id", "class", "farm", "readiness", "reason_codes", "warnings"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows_out:
            writer.writerow({
                **row,
                "reason_codes": "|".join(row["reason_codes"]),
                "warnings": "|".join(row["warnings"]),
            })
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Nongtori field Sheet CSV readiness without modifying source data.")
    parser.add_argument("csv", type=Path, help="CSV export of 농가_딸기데이터")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/field-data-readiness"))
    args = parser.parse_args()
    summary = audit(args.csv, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
