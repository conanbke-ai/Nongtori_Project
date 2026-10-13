from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ml.data_pipeline.mite_public_source_audit import audit_mite_public_sources


class MitePublicSourceAuditTests(unittest.TestCase):
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
                {row["source_id"] for row in report["sources"]},
                {"DATA-PEST-001", "DATA-PEST-002"},
            )
            self.assertTrue(output.is_file())
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "MITE_PUBLIC_SOURCE_GATE_READY")


if __name__ == "__main__":
    unittest.main()
