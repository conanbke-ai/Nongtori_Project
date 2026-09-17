from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from ml.data_pipeline.dryad_weight_audit import audit_datasheet, audit_image_inventory


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _column_name(index: int) -> str:
    result = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def write_xlsx(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    shared: list[str] = []
    shared_index: dict[str, int] = {}

    def s(value: object) -> int:
        text = str(value)
        if text not in shared_index:
            shared_index[text] = len(shared)
            shared.append(text)
        return shared_index[text]

    all_rows = [headers, *rows]
    row_xml = []
    for row_number, row in enumerate(all_rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            ref = f"{_column_name(column_index)}{row_number}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="s"><v>{s(value)}</v></c>')
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')

    shared_xml = "".join(f"<si><t>{escape(value)}</t></si>" for value in shared)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            f'<?xml version="1.0"?><workbook xmlns="{MAIN_NS}" xmlns:r="{OFFICE_REL_NS}"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<?xml version="1.0"?><Relationships xmlns="{REL_NS}"><Relationship Id="rId1" Type="{OFFICE_REL_NS}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<?xml version="1.0"?><sst xmlns="{MAIN_NS}" count="{len(shared)}" uniqueCount="{len(shared)}">{shared_xml}</sst>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<?xml version="1.0"?><worksheet xmlns="{MAIN_NS}"><sheetData>{"".join(row_xml)}</sheetData></worksheet>',
        )


class DryadWeightAuditTests(unittest.TestCase):
    def test_audit_resolves_dual_weight_columns_and_preserves_target_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "datasheet.xlsx"
            write_xlsx(
                path,
                ["Fruit ID", "Variety", "Shape", "Width mm", "Height mm", "Weight with calyx g", "Weight without calyx g"],
                [
                    ["1", "A", "normal", 30.0, 40.0, 23.0, 22.0],
                    ["2", "A", "normal", 27.0, 36.0, 17.0, 16.2],
                    ["3", "B", "normal", 24.0, 32.0, 12.4, 11.8],
                    ["4", "B", "normal", 20.0, 29.0, 10.0, 9.5],
                ],
            )
            report = audit_datasheet(path)
            self.assertEqual(report["status"], "AUDITED_METADATA")
            self.assertEqual(report["fruit_id_count"], 4)
            self.assertFalse(report["official_count_match"])
            self.assertEqual(report["calyx_weight_relation"]["violations_without_gt_with"], 0)
            self.assertEqual(report["weight_grade_bins"]["weight_with_calyx"]["SP_WEIGHT"], 1)
            self.assertEqual(report["weight_grade_bins"]["weight_with_calyx"]["HI_WEIGHT"], 1)
            self.assertEqual(report["weight_grade_bins"]["weight_with_calyx"]["MD_WEIGHT"], 1)
            self.assertEqual(report["weight_grade_bins"]["weight_with_calyx"]["JM_WEIGHT_CANDIDATE"], 1)
            self.assertEqual(report["target_alignment"], "FIELD_PROTOCOL_REQUIRED")
            self.assertFalse(report["weight_training_ready"])

    def test_duplicate_fruit_identity_blocks_metadata_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "datasheet.xlsx"
            write_xlsx(
                path,
                ["Strawberry ID", "Weight"],
                [["42", 14.0], ["42", 14.1]],
            )
            report = audit_datasheet(path)
            self.assertEqual(report["status"], "REVIEW_REQUIRED")
            self.assertEqual(report["duplicate_fruit_id_count"], 1)
            self.assertIn("weight_generic", report["resolved_columns"])

    def test_image_inventory_requires_all_views_to_stay_with_known_fruit_ids(self) -> None:
        names = [f"fruit_1_view_{index:02d}.jpg" for index in range(1, 23)]
        names += [f"fruit_2_view_{index:02d}.jpg" for index in range(1, 23)]
        result = audit_image_inventory(
            names,
            fruit_ids=["1", "2"],
            fruit_id_regex=r"fruit_(?P<fruit_id>\d+)_view_\d+\.jpg$",
        )
        self.assertEqual(result["status"], "JOIN_VERIFIED")
        self.assertEqual(result["wrong_view_count_fruit_count"], 0)

        broken = audit_image_inventory(
            names[:-1],
            fruit_ids=["1", "2"],
            fruit_id_regex=r"fruit_(?P<fruit_id>\d+)_view_\d+\.jpg$",
        )
        self.assertEqual(broken["status"], "REVIEW_REQUIRED")
        self.assertEqual(broken["wrong_view_count_fruit_count"], 1)


if __name__ == "__main__":
    unittest.main()
