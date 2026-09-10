from __future__ import annotations

from typing import Any, Iterable

CANONICAL_FARM_CODES = frozenset({"M", "C1", "C2", "U"})


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def validate_farm_code(value: Any, *, field_name: str = "Farm") -> str:
    farm = _text(value).upper()
    if farm not in CANONICAL_FARM_CODES:
        allowed = ", ".join(sorted(CANONICAL_FARM_CODES))
        raise ValueError(f"{field_name} must be one of {{{allowed}}}; got {value!r}")
    return farm


def audit_farm_codes(rows: Iterable[dict[str, Any]]) -> dict[str, object]:
    counts = {code: 0 for code in sorted(CANONICAL_FARM_CODES)}
    invalid: list[dict[str, str]] = []
    rows_with_id = 0
    for row in rows:
        if not _text(row.get("ID")):
            continue
        rows_with_id += 1
        raw = _text(row.get("Farm"))
        try:
            farm = validate_farm_code(raw)
        except ValueError:
            invalid.append({"id": _text(row.get("ID")), "farm": raw})
            continue
        counts[farm] += 1
    return {
        "status": "PASS" if not invalid else "REVIEW_REQUIRED",
        "rows_with_id": rows_with_id,
        "farm_counts": counts,
        "invalid_farm_rows": invalid,
    }
