from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.rgb_v001 import (
    EPOCHS,
    PATIENCE,
    EXPECTED_VIEWS_PER_FRUIT,
    SnapshotRow,
    WeightViewDataset,
    _open_snapshot_rgb,
    _sha256_file,
    _training_history_state,
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

    def test_decode_failure_rejects_changed_asset_bytes(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jpg"
            path.write_bytes(b"not-a-jpeg")
            actual = _sha256_file(path)
            self.assertEqual(len(actual), 64)
            with self.assertRaisesRegex(
                RuntimeError,
                "no longer matches frozen SHA-256",
            ):
                _open_snapshot_rgb(path, "0" * 64)

    def test_hash_verified_truncated_jpeg_uses_controlled_fallback(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "truncated.jpg"
            image = Image.new("RGB", (128, 128))
            image.putdata(
                [
                    ((x * 17) % 256, (y * 29) % 256, ((x + y) * 13) % 256)
                    for y in range(128)
                    for x in range(128)
                ]
            )
            image.save(path, format="JPEG", quality=95)
            payload = path.read_bytes()
            # Remove a bounded tail while retaining a recognizable JPEG stream.
            path.write_bytes(payload[:-128])
            expected = _sha256_file(path)
            decoded = _open_snapshot_rgb(path, expected)
            self.assertEqual(decoded.mode, "RGB")
            self.assertEqual(decoded.size, (128, 128))

    def test_dataset_requires_asset_root_for_eval_loader_shape(self):
        row = SnapshotRow(
            fruit_id="A",
            split="train",
            target_g=12.3,
            relative_path="a.jpg",
            sha256="a" * 64,
        )
        dataset = WeightViewDataset([row], Path("assets"), transform=lambda image: image)
        self.assertEqual(dataset.asset_root, Path("assets"))
        self.assertEqual(dataset.items[0].relative_path, "a.jpg")

    def test_completed_history_resumes_final_evaluation(self):
        history = []
        for epoch in range(1, PATIENCE + 2):
            history.append(
                {
                    "epoch": epoch,
                    "validation_fruit_metrics": {
                        "mae_g": 1.0 if epoch == 1 else 2.0 + epoch,
                    },
                }
            )
        state = _training_history_state(history)
        self.assertTrue(state["complete"])
        self.assertEqual(state["best_epoch"], 1)
        self.assertGreaterEqual(state["stale_epochs"], PATIENCE)

    def test_full_epoch_history_is_complete_even_without_patience(self):
        history = [
            {
                "epoch": epoch,
                "validation_fruit_metrics": {"mae_g": 10.0 - epoch * 0.1},
            }
            for epoch in range(1, EPOCHS + 1)
        ]
        state = _training_history_state(history)
        self.assertTrue(state["complete"])
        self.assertEqual(state["best_epoch"], EPOCHS)

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
