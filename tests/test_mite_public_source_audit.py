from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Callable

from ml.data_pipeline.mite_public_source_audit import audit_mite_public_sources


class MitePublicSourceAuditTests(unittest.TestCase):
    def _audit_source_derived_fixture(
        self,
        mutate: Callable[[dict[str, dict]], None],
    ) -> dict:
        """Audit a source-derived fixture without changing canonical registry records."""
        canonical_dir = Path("ml/data_pipeline/sources")
        records = {
            source_id: json.loads(
                (canonical_dir / f"{source_id}.json").read_text(encoding="utf-8")
            )
            for source_id in ("DATA-PEST-001", "DATA-PEST-002")
        }
        mutate(records)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "sources"
            source_dir.mkdir()
            for source_id, record in records.items():
                (source_dir / f"{source_id}.json").write_text(
                    json.dumps(record, ensure_ascii=False),
                    encoding="utf-8",
                )
            return audit_mite_public_sources(
                source_dir=source_dir,
                output=root / "audit.json",
            )

    def test_registered_sources_are_role_separated_and_commercially_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "audit.json"
            report = audit_mite_public_sources(
                source_dir=Path("ml/data_pipeline/sources"),
                output=output,
            )
            self.assertEqual(report["status"], "MITE_PUBLIC_SOURCE_GATE_READY")
            self.assertTrue(report["policy"]["do_not_merge_roles"])
            self.assertTrue(report["policy"]["no_field_ready_claim_from_public_sources_only"])
            self.assertEqual(
                report["policy"]["gate_scope"],
                "REGISTERED_SOURCE_CONTRACT_PRE_ACQUISITION_ONLY",
            )
            self.assertEqual(
                {row["source_id"] for row in report["sources"]},
                {"DATA-PEST-001", "DATA-PEST-002"},
            )
            self.assertEqual(
                {row["source_id"]: row["version_or_revision"] for row in report["sources"]},
                {"DATA-PEST-001": "1", "DATA-PEST-002": "210"},
            )
            self.assertTrue(all(row["status"] == "REVIEW_REQUIRED" for row in report["sources"]))
            self.assertTrue(output.is_file())
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "MITE_PUBLIC_SOURCE_GATE_READY")

    def test_missing_version_pin_blocks_registry_gate(self):
        def mutate(records: dict[str, dict]) -> None:
            records["DATA-PEST-001"].pop("version_or_revision")

        report = self._audit_source_derived_fixture(mutate)

        self.assertEqual(report["status"], "MITE_PUBLIC_SOURCE_GATE_BLOCKED")
        self.assertIn(
            "DATA-PEST-001:VERSION_OR_REVISION_MISSING",
            report["blocking_reasons"],
        )

    def test_registry_and_retrieval_revision_mismatch_blocks_registry_gate(self):
        def mutate(records: dict[str, dict]) -> None:
            records["DATA-PEST-002"]["retrieval"]["version_number"] = 211

        report = self._audit_source_derived_fixture(mutate)

        self.assertEqual(report["status"], "MITE_PUBLIC_SOURCE_GATE_BLOCKED")
        self.assertIn(
            "DATA-PEST-002:RETRIEVAL_VERSION_MISMATCH",
            report["blocking_reasons"],
        )

    def test_unapproved_revision_change_blocks_registry_gate(self):
        def mutate(records: dict[str, dict]) -> None:
            records["DATA-PEST-002"]["version_or_revision"] = "211"
            records["DATA-PEST-002"]["retrieval"]["version_number"] = 211

        report = self._audit_source_derived_fixture(mutate)

        self.assertEqual(report["status"], "MITE_PUBLIC_SOURCE_GATE_BLOCKED")
        self.assertIn(
            "DATA-PEST-002:VERSION_PIN_MISMATCH",
            report["blocking_reasons"],
        )

    def test_source_role_swap_blocks_registry_gate(self):
        def mutate(records: dict[str, dict]) -> None:
            first = records["DATA-PEST-001"]["nongtori_mapping"]["role"]
            second = records["DATA-PEST-002"]["nongtori_mapping"]["role"]
            records["DATA-PEST-001"]["nongtori_mapping"]["role"] = second
            records["DATA-PEST-002"]["nongtori_mapping"]["role"] = first

        report = self._audit_source_derived_fixture(mutate)

        self.assertEqual(report["status"], "MITE_PUBLIC_SOURCE_GATE_BLOCKED")
        self.assertIn("DATA-PEST-001:ROLE_MISMATCH", report["blocking_reasons"])
        self.assertIn("DATA-PEST-002:ROLE_MISMATCH", report["blocking_reasons"])

    def test_v210_class_drift_blocks_registry_gate(self):
        def mutate(records: dict[str, dict]) -> None:
            drifted = copy.deepcopy(records["DATA-PEST-002"]["original_labels"])
            drifted.append("Biocontrol_mite")
            records["DATA-PEST-002"]["original_labels"] = drifted
            records["DATA-PEST-002"]["nongtori_mapping"]["tssm_positive_labels"] = drifted

        report = self._audit_source_derived_fixture(mutate)

        self.assertEqual(report["status"], "MITE_PUBLIC_SOURCE_GATE_BLOCKED")
        self.assertIn("DATA-PEST-002:CLASS_PIN_MISMATCH", report["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
