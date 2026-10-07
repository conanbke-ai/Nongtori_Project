from __future__ import annotations

import unittest

from ml.weight_baseline.rgb_multiview_v002 import (
    AGGREGATIONS,
    _aggregate_values,
    _candidate_key,
    aggregate_view_records,
)
from ml.weight_baseline.rgb_v001 import EXPECTED_VIEWS_PER_FRUIT


class WeightRgbMultiviewV002Test(unittest.TestCase):
    def test_mean_median_and_trimmed_aggregations(self):
        values = [10.0] * 20 + [0.0, 100.0]

        self.assertAlmostEqual(
            _aggregate_values(values, "MEAN_22_VIEW"),
            sum(values) / 22,
        )
        self.assertEqual(
            _aggregate_values(values, "MEDIAN_22_VIEW"),
            10.0,
        )
        self.assertAlmostEqual(
            _aggregate_values(values, "TRIMMED_MEAN_10PCT_EACH_TAIL"),
            10.0,
        )
        self.assertAlmostEqual(
            _aggregate_values(values, "TRIMMED_MEAN_20PCT_EACH_TAIL"),
            10.0,
        )

    def test_aggregate_view_records_requires_exact_22_views(self):
        records = [
            {
                "fruit_id": "A",
                "target_g": 15.0,
                "prediction_g": 15.0,
            }
            for _ in range(EXPECTED_VIEWS_PER_FRUIT - 1)
        ]
        with self.assertRaisesRegex(ValueError, "expected 22"):
            aggregate_view_records(records, "MEAN_22_VIEW")

    def test_candidate_selection_prioritizes_grade_and_crossing_errors(self):
        candidates = [
            {
                "aggregation": "MEAN_22_VIEW",
                "oof_metrics": {
                    "grade_error_count": 10,
                    "threshold_crossing_count": 12,
                    "mae_g": 1.0,
                    "rmse_g": 1.5,
                },
            },
            {
                "aggregation": "MEDIAN_22_VIEW",
                "oof_metrics": {
                    "grade_error_count": 9,
                    "threshold_crossing_count": 20,
                    "mae_g": 2.0,
                    "rmse_g": 3.0,
                },
            },
        ]
        selected = min(candidates, key=_candidate_key)
        self.assertEqual(selected["aggregation"], "MEDIAN_22_VIEW")

    def test_aggregation_catalog_is_fixed(self):
        self.assertEqual(
            AGGREGATIONS,
            (
                "MEAN_22_VIEW",
                "MEDIAN_22_VIEW",
                "TRIMMED_MEAN_10PCT_EACH_TAIL",
                "TRIMMED_MEAN_20PCT_EACH_TAIL",
            ),
        )


if __name__ == "__main__":
    unittest.main()
