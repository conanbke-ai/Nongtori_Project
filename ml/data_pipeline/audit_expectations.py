from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_expectation(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_audit_expectation(report: dict[str, Any], expectation: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, expected: Any, actual: Any, *, required: bool = True) -> None:
        matched = actual == expected
        checks.append({"name": name, "expected": expected, "actual": actual, "required": required, "matched": matched})

    expected_source = expectation.get("source_id")
    if expected_source:
        add("source_id", expected_source, report.get("source_id"))

    raw = expectation.get("raw_audit_expectation", {})
    file_count_field = raw.get("file_count_field")
    if file_count_field and "file_count" in raw:
        add(file_count_field, raw["file_count"], report.get(file_count_field))
    if "annotation_count" in raw:
        add("annotation_count", raw["annotation_count"], report.get("annotation_count"))

    expected_classes = raw.get("class_counts", {})
    actual_classes = report.get("class_counts", {}) or {}
    for label, expected_count in expected_classes.items():
        add(f"class_counts.{label}", expected_count, actual_classes.get(label, 0))

    required_checks = [check for check in checks if check["required"]]
    mismatches = [check for check in required_checks if not check["matched"]]
    if not checks:
        status = "NO_EXPECTATIONS"
    elif mismatches:
        status = "MISMATCH"
    else:
        status = "MATCH"

    return {
        "source_id": expected_source or report.get("source_id", ""),
        "expectation_id": expectation.get("expectation_id", ""),
        "status": status,
        "checks": checks,
        "mismatches": mismatches,
        "provenance": expectation.get("provenance", {}),
        "notes": expectation.get("notes", ""),
    }


def verify_audit_files(report_path: Path, expectation_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    expectation = load_expectation(expectation_path)
    result = verify_audit_expectation(report, expectation)
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
