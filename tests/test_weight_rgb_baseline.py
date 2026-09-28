from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.rgb_v001 import (
    EXPECTED_VIEWS_PER_FRUIT,
    SnapshotRow,
    WeightViewDataset,
    aggregate_fruit_predictions,
    evaluate_fruit_records,
)


class WeightRgbBaselineTest(unittest.TestCase):
    def test_aggregates_22_views_per_fruit(self):
        records = []
        for fruit_id, split, target, prediction in [
            ("A", "validation", 12.0, 13.0),
            ("B", "test", 20.0, 18.0),
        ]:
            for _ in range(EXPECTED_VIEWS_PER_FRUIT):
                records.append(
                    {
                        "fruit_id": fruit_id,
                        "split": split,
                        "target_g": target,
                        "prediction_g": prediction,
                    }
                )
        aggregated = aggregate_fruit_predictions(records)
        self.assertEqual(len(aggregated), 2)
        self.assertEqual(aggregated[0]["view_count"], 22)
        self.assertEqual(aggregated[0]["predicted_weight_g"], 13.0)
        self.assertEqual(aggregated[1]["predicted_weight_g"], 18.0)

        report = evaluate_fruit_records(aggregated)
        self.assertEqual(report["n_fruits"], 2)
        self.assertGreater(report["mae_g"], 0)

    def test_dataset_class_is_module_level_and_pickleable_shape(self):
        row = SnapshotRow(
            fruit_id="A",
            split="train",
            target_g=12.3,
            relative_path="a.jpg",
            sha256="a" * 64,
        )
        dataset = WeightViewDataset([row], Path("."), transform=lambda image: image)
        self.assertEqual(dataset.__class__.__qualname__, "WeightViewDataset")
        self.assertEqual(dataset.items[0].fruit_id, "A")

    def test_blocks_wrong_view_count(self):
        records = [
            {
                "fruit_id": "A",
                "split": "validation",
                "target_g": 12.0,
                "prediction_g": 12.0,
            }
            for _ in range(EXPECTED_VIEWS_PER_FRUIT - 1)
        ]
        with self.assertRaisesRegex(ValueError, "expected 22"):
            aggregate_fruit_predictions(records)


if __name__ == "__main__":
    unittest.main()
