from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

FRUIT_CLASS = "STR"
LEAF_CLASS = "LEF"
VALID_GRADES = {"SP", "HI", "MD", "JM", "NA"}
VALID_MATURITY = {"0", "1", "2", "3", "4"}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def audit_field_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [dict(row) for row in rows if _text(row.get("ID"))]
    class_counts = Counter(_text(row.get("Class")).upper() or "UNKNOWN" for row in rows)
    fruit_rows = [row for row in rows if _text(row.get("Class")).upper() == FRUIT_CLASS]
    leaf_rows = [row for row in rows if _text(row.get("Class")).upper() == LEAF_CLASS]
    maturity_counts = Counter(_text(row.get("Maturity")) or "EMPTY" for row in fruit_rows)
    grade_counts = Counter(_text(row.get("Grade")).upper() or "EMPTY" for row in fruit_rows)
    mal_jm_violations = [
        _text(row.get("ID")) for row in fruit_rows
        if _text(row.get("Health")).upper() == "MAL" and _text(row.get("Grade")).upper() != "JM"
    ]
    ripeness_eligible = [
        row for row in fruit_rows
        if _text(row.get("Maturity")) in VALID_MATURITY and _text(row.get("Grade")).upper() in VALID_GRADES
    ]
    harvested = [row for row in fruit_rows if _text(row.get("Grade")).upper() in {"SP", "HI", "MD", "JM"}]
    not_harvested = [row for row in fruit_rows if _text(row.get("Grade")).upper() == "NA"]
    maturity3 = [row for row in fruit_rows if _text(row.get("Maturity")) == "3"]
    maturity3_harvested = [row for row in maturity3 if _text(row.get("Grade")).upper() != "NA"]
    maturity3_wait = [row for row in maturity3 if _text(row.get("Grade")).upper() == "NA"]

    return {
        "status": "PASS" if not mal_jm_violations else "REVIEW_REQUIRED",
        "rows_with_id": len(rows),
        "class_counts": dict(sorted(class_counts.items())),
        "fruit_rows": len(fruit_rows),
        "leaf_rows": len(leaf_rows),
        "fruit_ripeness_eligible": len(ripeness_eligible),
        "fruit_harvested": len(harvested),
        "fruit_not_harvested": len(not_harvested),
        "fruit_maturity_counts": dict(sorted(maturity_counts.items())),
        "fruit_grade_counts": dict(sorted(grade_counts.items())),
        "maturity3_total": len(maturity3),
        "maturity3_harvested": len(maturity3_harvested),
        "maturity3_not_harvested": len(maturity3_wait),
        "mal_requires_jm_violations": mal_jm_violations,
        "ripeness_excluded_nonfruit": len(rows) - len(fruit_rows),
    }


def audit_field_csv(input_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    with Path(input_path).open(encoding="utf-8-sig", newline="") as f:
        report = audit_field_rows(csv.DictReader(f))
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
