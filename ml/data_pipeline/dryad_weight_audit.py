from __future__ import annotations

import argparse
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable
from xml.etree import ElementTree as ET

DRYAD_DATASET_DOI = "10.25338/B8V308"
EXPECTED_FRUITS = 1611
EXPECTED_VIEWS_PER_FRUIT = 22

NONGTORI_WEIGHT_PROTOCOL = "WITH_CALYX"
PRIMARY_WEIGHT_FIELD = "weight_with_calyx"
AUXILIARY_WEIGHT_FIELD = "weight_without_calyx"

_XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _col_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref or "")
    if not match:
        return 0
    result = 0
    for char in match.group(1):
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    name = "xl/sharedStrings.xml"
    if name not in archive.namelist():
        return []
    root = ET.fromstring(archive.read(name))
    values: list[str] = []
    for item in root.findall("m:si", _XLSX_NS):
        values.append("".join(node.text or "" for node in item.findall(".//m:t", _XLSX_NS)))
    return values


def _sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relation_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("r:Relationship", _REL_NS)}
    result: list[tuple[str, str]] = []
    for sheet in workbook.findall("m:sheets/m:sheet", _XLSX_NS):
        name = sheet.attrib.get("name", "")
        rel_id = sheet.attrib.get(f"{{{_OFFICE_REL_NS}}}id", "")
        target = relation_map.get(rel_id)
        if not target:
            continue
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target.lstrip('./')}"
        result.append((name, path))
    return result


def _decode_cell(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//m:t", _XLSX_NS))
    value_node = cell.find("m:v", _XLSX_NS)
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw


def read_xlsx_sheets(path: Path) -> dict[str, list[list[str]]]:
    with zipfile.ZipFile(Path(path)) as archive:
        shared = _shared_strings(archive)
        sheets: dict[str, list[list[str]]] = {}
        for sheet_name, sheet_path in _sheet_paths(archive):
            if sheet_path not in archive.namelist():
                continue
            root = ET.fromstring(archive.read(sheet_path))
            rows: list[list[str]] = []
            for row in root.findall(".//m:sheetData/m:row", _XLSX_NS):
                cells: dict[int, str] = {}
                for cell in row.findall("m:c", _XLSX_NS):
                    cells[_col_index(cell.attrib.get("r", ""))] = _decode_cell(cell, shared)
                if not cells:
                    rows.append([])
                    continue
                width = max(cells) + 1
                rows.append([cells.get(index, "") for index in range(width)])
            sheets[sheet_name] = rows
        return sheets


def _header_semantic(header: str) -> str | None:
    key = _norm(header)
    if not key:
        return None
    if key in {
        "id",
        "idno",
        "idnumber",
        "fruitid",
        "strawberryid",
        "berryid",
        "fruitnumber",
        "strawberrynumber",
        "berrynumber",
    }:
        return "fruit_id"
    if "variety" in key or "cultivar" in key:
        return "variety"
    if "shape" in key:
        return "shape"
    if "width" in key or "diameter" in key:
        return "width"
    if "height" in key or "length" in key:
        return "height"
    has_weight = "weight" in key or "mass" in key or key.startswith("wt")
    if not has_weight:
        return None
    if any(
        token in key
        for token in (
            "withoutcalyx",
            "wocalyx",
            "nocalyx",
            "calyxremoved",
            "withoutstem",
            "wostem",
            "nostem",
            "fleshweight",
        )
    ):
        return AUXILIARY_WEIGHT_FIELD
    if any(token in key for token in ("withcalyx", "wcalyx", "wholeweight", "totalweight", "withstem", "wstem")):
        return PRIMARY_WEIGHT_FIELD
    return "weight_generic"


def _header_score(row: list[str]) -> tuple[int, dict[str, int]]:
    mapping: dict[str, int] = {}
    score = 0
    for index, value in enumerate(row):
        semantic = _header_semantic(value)
        if semantic and semantic not in mapping:
            mapping[semantic] = index
            score += 3 if semantic in {"fruit_id", PRIMARY_WEIGHT_FIELD, AUXILIARY_WEIGHT_FIELD, "weight_generic"} else 1
    if "fruit_id" in mapping:
        score += 2
    if PRIMARY_WEIGHT_FIELD in mapping:
        score += 4
    elif any(key.startswith("weight_") for key in mapping):
        score += 1
    return score, mapping


def detect_table(sheets: dict[str, list[list[str]]], *, scan_rows: int = 25) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for sheet_name, rows in sheets.items():
        for row_index, row in enumerate(rows[:scan_rows]):
            score, mapping = _header_score(row)
            if score:
                candidates.append({"sheet": sheet_name, "header_row_index": row_index, "score": score, "mapping": mapping, "headers": row})
    if not candidates:
        return {"status": "HEADER_NOT_FOUND", "candidates": []}
    candidates.sort(key=lambda item: (item["score"], len(item["mapping"])), reverse=True)
    return {"status": "FOUND", "best": candidates[0], "candidates": candidates[:5]}


def _detect_sheet_tables(
    sheets: dict[str, list[list[str]]],
    *,
    scan_rows: int = 25,
) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for sheet_name, rows in sheets.items():
        candidates: list[dict[str, Any]] = []
        for row_index, row in enumerate(rows[:scan_rows]):
            score, mapping = _header_score(row)
            if not score:
                continue
            candidates.append(
                {
                    "sheet": sheet_name,
                    "header_row_index": row_index,
                    "score": score,
                    "mapping": mapping,
                    "headers": row,
                }
            )
        if not candidates:
            continue
        candidates.sort(key=lambda item: (item["score"], len(item["mapping"])), reverse=True)
        best = candidates[0]
        mapping = best["mapping"]
        if "fruit_id" not in mapping or PRIMARY_WEIGHT_FIELD not in mapping:
            continue
        raw_rows = rows[int(best["header_row_index"]) + 1 :]
        nonempty_rows = [row for row in raw_rows if any(str(cell).strip() for cell in row)]
        fruit_id_index = mapping["fruit_id"]
        data_rows = [row for row in nonempty_rows if _value_at(row, fruit_id_index)]
        tables.append(
            {
                **best,
                "rows": data_rows,
                "raw_nonempty_row_count": len(nonempty_rows),
                "excluded_non_fruit_row_count": len(nonempty_rows) - len(data_rows),
            }
        )
    return tables


def _value_at(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _numeric_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {"count": len(values), "min": ordered[0], "mean": mean(values), "median": median(values), "max": ordered[-1]}


def _grade_bins(values: Iterable[float]) -> dict[str, int]:
    counts = Counter()
    for value in values:
        if value >= 22:
            counts["SP_WEIGHT"] += 1
        elif value >= 16:
            counts["HI_WEIGHT"] += 1
        elif value >= 12:
            counts["MD_WEIGHT"] += 1
        else:
            counts["JM_WEIGHT_CANDIDATE"] += 1
    return dict(counts)


def audit_datasheet(path: Path) -> dict[str, Any]:
    sheets = read_xlsx_sheets(path)
    tables = _detect_sheet_tables(sheets)

    if not tables:
        table = detect_table(sheets)
        if table["status"] != "FOUND":
            return {
                "source_id": "DATA-QUAL-002",
                "status": "REVIEW_REQUIRED",
                "datasheet_status": table["status"],
                "weight_training_ready": False,
                "image_join_status": "NOT_RUN",
                "target_alignment": "WITH_CALYX_PRIMARY",
                "primary_weight_field": PRIMARY_WEIGHT_FIELD,
                "auxiliary_weight_field": AUXILIARY_WEIGHT_FIELD,
                "field_weight_protocol": NONGTORI_WEIGHT_PROTOCOL,
            }

        best = table["best"]
        sheet_name = best["sheet"]
        header_row_index = int(best["header_row_index"])
        mapping: dict[str, int] = best["mapping"]
        headers: list[str] = best["headers"]
        raw_rows = sheets[sheet_name][header_row_index + 1 :]
        rows = [row for row in raw_rows if any(str(cell).strip() for cell in row)]
        table_summaries = [
            {
                "sheet": sheet_name,
                "header_row": header_row_index + 1,
                "headers": headers,
                "resolved_columns": mapping,
                "data_row_count": len(rows),
                "raw_nonempty_row_count": len(rows),
                "excluded_non_fruit_row_count": 0,
            }
        ]
    else:
        rows: list[list[str]] = []
        table_summaries: list[dict[str, Any]] = []
        for table in tables:
            table_rows = table["rows"]
            rows.extend(table_rows)
            table_summaries.append(
                {
                    "sheet": table["sheet"],
                    "header_row": int(table["header_row_index"]) + 1,
                    "headers": table["headers"],
                    "resolved_columns": table["mapping"],
                    "data_row_count": len(table_rows),
                    "raw_nonempty_row_count": int(table.get("raw_nonempty_row_count", len(table_rows))),
                    "excluded_non_fruit_row_count": int(table.get("excluded_non_fruit_row_count", 0)),
                }
            )

        mapping = tables[0]["mapping"]
        headers = tables[0]["headers"]
        sheet_name = tables[0]["sheet"] if len(tables) == 1 else "MULTI_SHEET"
        header_row_index = int(tables[0]["header_row_index"])

        incompatible = [
            item["sheet"]
            for item in tables
            if item["mapping"] != mapping
        ]
        if incompatible:
            return {
                "source_id": "DATA-QUAL-002",
                "dataset_doi": DRYAD_DATASET_DOI,
                "status": "REVIEW_REQUIRED",
                "datasheet_status": "INCOMPATIBLE_TABLE_SCHEMAS",
                "tables": table_summaries,
                "incompatible_sheets": incompatible,
                "weight_training_ready": False,
                "image_join_status": "NOT_RUN",
                "target_alignment": "WITH_CALYX_PRIMARY",
                "primary_weight_field": PRIMARY_WEIGHT_FIELD,
                "auxiliary_weight_field": AUXILIARY_WEIGHT_FIELD,
                "field_weight_protocol": NONGTORI_WEIGHT_PROTOCOL,
            }

    if tables:
        row_records = [
            (str(table["sheet"]), row)
            for table in tables
            for row in table["rows"]
        ]
    else:
        row_records = [(sheet_name, row) for row in rows]

    fruit_ids = [_value_at(row, mapping.get("fruit_id")) for row in rows]
    fruit_ids = [value for value in fruit_ids if value]
    duplicate_ids = sorted(value for value, count in Counter(fruit_ids).items() if count > 1)

    numeric_fields = ["width", "height", PRIMARY_WEIGHT_FIELD, AUXILIARY_WEIGHT_FIELD, "weight_generic"]
    numeric_values: dict[str, list[float]] = defaultdict(list)
    numeric_missing: dict[str, int] = defaultdict(int)
    numeric_missing_samples: dict[str, list[dict[str, str]]] = defaultdict(list)
    for source_sheet, row in row_records:
        fruit_id = _value_at(row, mapping.get("fruit_id"))
        for field in numeric_fields:
            if field not in mapping:
                continue
            parsed = _to_float(_value_at(row, mapping[field]))
            if parsed is None or parsed <= 0:
                numeric_missing[field] += 1
                if fruit_id:
                    numeric_missing_samples[field].append(
                        {"fruit_id": fruit_id, "sheet": source_sheet}
                    )
            else:
                numeric_values[field].append(parsed)

    relation_checked = 0
    relation_violations = 0
    calyx_delta: list[float] = []
    calyx_relation_violation_samples: list[dict[str, Any]] = []
    calyx_delta_samples: list[dict[str, Any]] = []
    if PRIMARY_WEIGHT_FIELD in mapping and AUXILIARY_WEIGHT_FIELD in mapping:
        for source_sheet, row in row_records:
            fruit_id = _value_at(row, mapping.get("fruit_id"))
            with_calyx = _to_float(_value_at(row, mapping[PRIMARY_WEIGHT_FIELD]))
            without_calyx = _to_float(_value_at(row, mapping[AUXILIARY_WEIGHT_FIELD]))
            if with_calyx is None or without_calyx is None:
                continue
            relation_checked += 1
            delta = with_calyx - without_calyx
            calyx_delta.append(delta)
            sample = {
                "fruit_id": fruit_id,
                "sheet": source_sheet,
                "weight_with_calyx": with_calyx,
                "weight_without_calyx": without_calyx,
                "delta_with_minus_without": delta,
            }
            calyx_delta_samples.append(sample)
            if delta < -1e-6:
                relation_violations += 1
                calyx_relation_violation_samples.append(sample)

    largest_calyx_deltas = sorted(
        calyx_delta_samples,
        key=lambda item: float(item["delta_with_minus_without"]),
        reverse=True,
    )[:20]

    required_semantics = {
        "fruit_id": "fruit_id" in mapping,
        "primary_weight_with_calyx": PRIMARY_WEIGHT_FIELD in mapping,
        "width": "width" in mapping,
        "height": "height" in mapping,
    }
    schema_ok = required_semantics["fruit_id"] and required_semantics["primary_weight_with_calyx"]
    fruit_count = len(set(fruit_ids)) if fruit_ids else 0
    official_count_match = fruit_count == EXPECTED_FRUITS if fruit_ids else False
    primary_values = numeric_values[PRIMARY_WEIGHT_FIELD]
    primary_weight_complete = bool(primary_values) and len(primary_values) == len(rows)
    status = "AUDITED_METADATA" if schema_ok and fruit_count > 0 and not duplicate_ids and primary_weight_complete else "REVIEW_REQUIRED"

    weight_fields = [field for field in (PRIMARY_WEIGHT_FIELD, AUXILIARY_WEIGHT_FIELD, "weight_generic") if field in mapping]
    weight_grade_bins = {field: _grade_bins(numeric_values[field]) for field in weight_fields}

    next_gate = "IMAGE_FILENAME_TO_FRUIT_ID_JOIN_AUDIT" if status == "AUDITED_METADATA" else "DATASHEET_SCHEMA_OR_VALUE_REVIEW"

    return {
        "source_id": "DATA-QUAL-002",
        "dataset_doi": DRYAD_DATASET_DOI,
        "status": status,
        "datasheet_status": "PARSED",
        "sheet": sheet_name,
        "header_row": header_row_index + 1,
        "headers": headers,
        "resolved_columns": mapping,
        "tables": table_summaries,
        "table_count": len(table_summaries),
        "required_semantics": required_semantics,
        "data_row_count": len(rows),
        "raw_nonempty_row_count": sum(item.get("raw_nonempty_row_count", item["data_row_count"]) for item in table_summaries),
        "excluded_non_fruit_row_count": sum(item.get("excluded_non_fruit_row_count", 0) for item in table_summaries),
        "fruit_id_count": fruit_count,
        "expected_fruit_count": EXPECTED_FRUITS,
        "official_count_match": official_count_match,
        "duplicate_fruit_ids": duplicate_ids[:100],
        "duplicate_fruit_id_count": len(duplicate_ids),
        "numeric_summary": {field: _numeric_summary(numeric_values[field]) for field in numeric_fields if field in mapping},
        "numeric_missing": {field: numeric_missing[field] for field in numeric_fields if field in mapping},
        "numeric_missing_samples": {
            field: numeric_missing_samples[field]
            for field in numeric_fields
            if field in mapping and numeric_missing_samples[field]
        },
        "weight_grade_bins": weight_grade_bins,
        "primary_weight_grade_bins": weight_grade_bins.get(PRIMARY_WEIGHT_FIELD, {}),
        "calyx_weight_relation": {
            "checked": relation_checked,
            "violations_without_gt_with": relation_violations,
            "violation_samples": calyx_relation_violation_samples,
            "delta_with_minus_without": _numeric_summary(calyx_delta),
            "largest_positive_deltas": largest_calyx_deltas,
        },
        "target_alignment": "WITH_CALYX_PRIMARY",
        "primary_weight_field": PRIMARY_WEIGHT_FIELD,
        "auxiliary_weight_field": AUXILIARY_WEIGHT_FIELD,
        "field_weight_protocol": NONGTORI_WEIGHT_PROTOCOL,
        "target_alignment_note": "Nongtori field Weight_g is measured with the strawberry calyx attached. Dryad weight_with_calyx is therefore the canonical training target; weight_without_calyx is retained only for auxiliary analysis.",
        "image_join_status": "NOT_RUN",
        "expected_views_per_fruit": EXPECTED_VIEWS_PER_FRUIT,
        "weight_training_ready": False,
        "next_gate": next_gate,
    }

def audit_image_inventory(image_names: Iterable[str], *, fruit_ids: Iterable[str], fruit_id_regex: str) -> dict[str, Any]:
    pattern = re.compile(fruit_id_regex)
    known = {str(value) for value in fruit_ids}
    counts: Counter[str] = Counter()
    unmatched: list[str] = []
    unknown_ids: Counter[str] = Counter()
    for name in image_names:
        match = pattern.search(str(name))
        if not match:
            unmatched.append(str(name))
            continue
        if "fruit_id" not in match.groupdict():
            raise ValueError("fruit_id_regex must contain a named group '(?P<fruit_id>...)'")
        fruit_id = match.group("fruit_id")
        if fruit_id not in known:
            unknown_ids[fruit_id] += 1
        counts[fruit_id] += 1
    known_counts = {fruit_id: counts.get(fruit_id, 0) for fruit_id in known}
    wrong_view_counts = {fruit_id: count for fruit_id, count in known_counts.items() if count != EXPECTED_VIEWS_PER_FRUIT}
    status = "JOIN_VERIFIED" if not unmatched and not unknown_ids and not wrong_view_counts and known else "REVIEW_REQUIRED"
    return {
        "status": status,
        "image_count": sum(counts.values()) + len(unmatched),
        "matched_image_count": sum(counts.values()),
        "unmatched_filename_count": len(unmatched),
        "unknown_fruit_id_count": len(unknown_ids),
        "wrong_view_count_fruit_count": len(wrong_view_counts),
        "wrong_view_counts_sample": dict(list(sorted(wrong_view_counts.items()))[:100]),
        "expected_views_per_fruit": EXPECTED_VIEWS_PER_FRUIT,
    }


def write_audit_report(report: dict[str, Any], output: Path | None) -> None:
    if not output:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit an already acquired UC Davis Dryad strawberry weight datasheet")
    parser.add_argument("--datasheet", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.datasheet.exists():
        raise SystemExit("datasheet does not exist; acquire it through nongtori-data dryad-weight-audit")
    report = audit_datasheet(args.datasheet)
    write_audit_report(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "AUDITED_METADATA" else 2


if __name__ == "__main__":
    raise SystemExit(main())
