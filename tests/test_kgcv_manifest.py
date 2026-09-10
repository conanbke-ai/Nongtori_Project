from __future__ import annotations

import unittest

from ml.data_pipeline.kgcv_manifest import build_manifest_from_pages, build_summary


class KgcvManifestTest(unittest.TestCase):
    def test_stage_mapping_and_unresolved_turning(self):
        page = {"rows": [{"row_idx": 7, "row": {"source": "tagged", "objects": {
            "categories": [4, 1, 6, 5, 3, 2, 0],
            "decimal_stage": [0.2, 0.3, 0.5, 0.8, 0.4, 0.5, 0.5],
        }}}]}
        rows = build_manifest_from_pages([page])
        by_label = {row["source_label"]: row for row in rows}
        self.assertEqual(by_label["small g"]["nongtori_maturity"], "0")
        self.assertEqual(by_label["green"]["nongtori_maturity"], "0")
        self.assertEqual(by_label["white"]["nongtori_maturity"], "1")
        self.assertEqual(by_label["red"]["nongtori_maturity"], "4")
        self.assertEqual(by_label["overripe"]["nongtori_maturity"], "4")
        self.assertEqual(by_label["overripe"]["nongtori_grade"], "JM")
        self.assertEqual(by_label["turning red"]["source_decimal_stage"], "0.8")
        self.assertEqual(by_label["turning red"]["mapping_status"], "UNRESOLVED")
        self.assertEqual(by_label["turning red"]["task_eligible"], "false")
        self.assertEqual(by_label["turning red"]["exclusion_reason"], "UNRESOLVED_TURNING_BOUNDARY")
        self.assertEqual(by_label["flower"]["exclusion_reason"], "NON_FRUIT_RIPENESS_TARGET")
        self.assertTrue(all(row["snapshot_eligible"] == "false" for row in rows))

    def test_summary_does_not_claim_training_ready(self):
        page = {"rows": [{"row_idx": 1, "row": {"source": "random", "objects": {
            "categories": [1, 5], "decimal_stage": [-1, -1]
        }}}]}
        summary = build_summary(build_manifest_from_pages([page]))
        self.assertEqual(summary["manifest_rows"], 2)
        self.assertEqual(summary["task_eligible_rows"], 1)
        self.assertFalse(summary["snapshot_eligible"])
        self.assertEqual(summary["asset_status"], "ASSET_NOT_MATERIALIZED")


if __name__ == "__main__":
    unittest.main()
