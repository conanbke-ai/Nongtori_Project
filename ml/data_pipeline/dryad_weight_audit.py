from __future__ import annotations

import argparse
import json
import math
import re
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable
from xml.etree import ElementTree as ET

DRYAD_DATASET_DOI = "10.25338/B8V308"
DRYAD_DATASHEET_URL = "https://datadryad.org/downloads/file_stream/141475"
EXPECTED_FRUITS = 1611
EXPECTED_VIEWS_PER_FRUIT = 22

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


def download_datasheet(output: Path, *, url: str = DRYAD_DATASHEET_URL, timeout: int = 60) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Nongtori-Dryad-Audit/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    if not payload.startswith(b"PK"):
        raise RuntimeError("Dryad datasheet download did not return an XLSX/ZIP payload")
    output.write_bytes(payload)
    return output


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
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = f"xl/{target.lstrip('./')}"
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
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
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
    raw = str(header or "").strip().lower()
    key = _norm(raw)
    if not key:
        return None

    if key in {"id", "fruitid", "strawberryid", "berryid", "fruitnumber", "strawberrynumber", "berrynumber"}:
        return "fruit_id"
    if "variety" in key or "cultivar" in key:
        return "variety"
    if "shape" in key:
        return "shape"
    if "width" in key or "diameter" in key:
        return "width"
    if "height" in key or "length" in key:
        return "height"

    has_weight = "weight" in key or "mass" in key
    if has_weight:
        if any(token in key for token in ("withoutcalyx", "nocalyx", "calyxremoved", "withoutstem", "nostem", "fleshweight")):
            return "weight_without_calyx"
        if any(token in key for token in ("withcalyx", "wholeweight", "totalweight", "withstem")):
            return "weight_with_calyx"
        return "weight_generic"
    return None


def _header_score(row: list[str]) -> tuple[int, dict[str, int]]:
    mapping: dict[str, int] = {}
    score = 0
    for index, value in enumerate(row):
        semantic = _header_semantic(value)
        if semantic and semantic not in mapping:
            mapping[semantic] = index
            score += 3 if semantic in {"fruit_id", "weight_with_calyx", "weight_without_calyx", "weight_generic"} else 1
    if "fruit_id" in mapping:
        score += 2
    if any(key.startswith("weight_") for key in mapping):
        score += 2
    return score, mapping


def detect_table(sheets: dict[str, list[list[str]]], *, scan_rows: int = 25) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for sheet_name, rows in sheets.items():
        for row_index, row in enumerate(rows[:scan_rows]):
            score, mapping = _header_score(row)
            if score:
                candidates.append({
                    "sheet": sheet_name,
                    "header_row_index": row_index,
                    "score": score,
                    "mapping": mapping,
                    "headers": row,
                })
    if not candidates:
        return {"status": "HEADER_NOT_FOUND", "candidates": []}
    candidates.sort(key=lambda item: (item["score"], len(item["mapping"])), reverse=True)
    best = candidates[0]
    return {"status": "FOUND", "best": best, "candidates": candidates[:5]}


def _value_at(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _numeric_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {
        "count": len(values),
        "min": ordered[0],
        "mean": mean(values),
        "median": median(values),
        "max": ordered[-1],
    }


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
    table = detect_table(sheets)
    if table["status"] != "FOUND":
        return {
            "source_id": "DATA-QUAL-002",
            "status": "REVIEW_REQUIRED",
            "datasheet_status": table["status"],
            "weight_training_ready": False,
            "image_join_status": "NOT_RUN",
            "target_alignment": "FIELD_PROTOCOL_REQUIRED",
        }

    best = table["best"]
    sheet_name = best["sheet"]
    header_row_index = int(best["header_row_index"])
    mapping: dict[str, int] = best["mapping"]
    headers: list[str] = best["headers"]
    raw_rows = sheets[sheet_name][header_row_index + 1 :]
    rows = [row for row in raw_rows if any(str(cell).strip() for cell in row)]

    fruit_ids = [_value_at(row, mapping.get("fruit_id")) for row in rows]
    fruit_ids = [value for value in fruit_ids if value]
    duplicate_ids = sorted(value for value, count in Counter(fruit_ids).items() if count > 1)

    numeric_fields = ["width", "height", "weight_with_calyx", "weight_without_calyx", "weight_generic"]
    numeric_values: dict[str, list[float]] = defaultdict(list)
    numeric_missing: dict[str, int] = defaultdict(int)
    for row in rows:
        for field in numeric_fields:
            if field not in mapping:
                continue
            parsed = _to_float(_value_at(row, mapping[field]))
            if parsed is None:
                numeric_missing[field] += 1
            elif parsed > 0:
                numeric_values[field].append(parsed)
            else:
                numeric_missing[field] += 1

    relation_checked = 0
    relation_violations = 0
    calyx_delta: list[float] = []
    if "weight_with_calyx" in mapping and "weight_without_calyx" in mapping:
        for row in rows:
            with_calyx = _to_float(_value_at(row, mapping["weight_with_calyx"]))
            without_calyx = _to_float(_value_at(row, mapping["weight_without_calyx"]))
            if with_calyx is None or without_calyx is None:
                continue
            relation_checked += 1
            delta = with_calyx - without_calyx
            calyx_delta.append(delta)
            if delta < -1e-6:
                relation_violations += 1

    weight_fields = [field for field in ("weight_with_calyx", "weight_without_calyx", "weight_generic") if field in mapping]
    required_semantics = {
        "fruit_id": "fruit_id" in mapping,
        "weight": bool(weight_fields),
        "width": "width" in mapping,
        "height": "height" in mapping,
    }
    schema_ok = required_semantics["fruit_id"] and required_semantics["weight"]

    fruit_count = len(set(fruit_ids)) if fruit_ids else 0
    official_count_match = fruit_count == EXPECTED_FRUITS if fruit_ids else False
    status = "AUDITED_METADATA" if schema_ok and fruit_count > 0 and not duplicate_ids else "REVIEW_REQUIRED"

    return {
        "source_id": "DATA-QUAL-002",
        "dataset_doi": DRYAD_DATASET_DOI,
        "status": status,
        "datasheet_status": "PARSED",
        "sheet": sheet_name,
        "header_row": header_row_index + 1,
        "headers": headers,
        "resolved_columns": mapping,
        "required_semantics": required_semantics,
        "data_row_count": len(rows),
        "fruit_id_count": fruit_count,
        "expected_fruit_count": EXPECTED_FRUITS,
        "official_count_match": official_count_match,
        "duplicate_fruit_ids": duplicate_ids[:100],
        "duplicate_fruit_id_count": len(duplicate_ids),
        "numeric_summary": {field: _numeric_summary(numeric_values[field]) for field in numeric_fields if field in mapping},
        "numeric_missing": {field: numeric_missing[field] for field in numeric_fields if field in mapping},
        "weight_grade_bins": {field: _grade_bins(numeric_values[field]) for field in weight_fields},
        "calyx_weight_relation": {
            "checked": relation_checked,
            "violations_without_gt_with": relation_violations,
            "delta_with_minus_without": _numeric_summary(calyx_delta),
        },
        "target_alignment": "FIELD_PROTOCOL_REQUIRED",
        "target_alignment_note": "Nongtori Weight_g is measured strawberry weight in grams but current field guide does not specify calyx inclusion. Preserve both Dryad weight targets until the field weighing protocol is frozen.",
        "image_join_status": "NOT_RUN",
        "expected_views_per_fruit": EXPECTED_VIEWS_PER_FRUIT,
        "weight_training_ready": False,
        "next_gate": "IMAGE_FILENAME_TO_FRUIT_ID_JOIN_AUDIT",
    }


def audit_image_inventory(
    image_names: Iterable[str],
    *,
    fruit_ids: Iterable[str],
    fruit_id_regex: str,
) -> dict[str, Any]:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit UC Davis Dryad strawberry weight metadata without adding XLSX dependencies")
    parser.add_argument("--datasheet", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Download the official Dryad datasheet if --datasheet does not exist")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if not args.datasheet.exists():
        if not args.download:
            raise SystemExit("datasheet does not exist; pass --download to retrieve the official Dryad datasheet")
        download_datasheet(args.datasheet)

    report = audit_datasheet(args.datasheet)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "AUDITED_METADATA" else 2


if __name__ == "__main__":
    raise SystemExit(main())
