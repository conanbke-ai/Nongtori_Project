from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.dyson_external_rgb_v001 import (
    aggregate_view_predictions,
    run_dyson_external_rgb_benchmark,
)


class DysonExternalRgbBenchmarkTests(unittest.TestCase):
    def test_aggregate_available_views_by_berry(self):
        rows = [
            {"berry_key":"b1","actual_weight_g":10,"predicted_weight_g":9},
            {"berry_key":"b1","actual_weight_g":10,"predicted_weight_g":11},
            {"berry_key":"b2","actual_weight_g":20,"predicted_weight_g":19},
        ]
        result = aggregate_view_predictions(rows)
        self.assertEqual(result[0]["berry_key"], "b1")
        self.assertEqual(result[0]["predicted_weight_g"], 10)
        self.assertEqual(result[0]["view_count"], 2)
        self.assertEqual(result[1]["view_count"], 1)

    def test_benchmark_is_external_only_and_no_retraining(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crop_root = root / "crops"
            crop_root.mkdir()
            crop = crop_root / "a.png"
            crop.write_bytes(b"crop")

            import hashlib
            digest = hashlib.sha256(b"crop").hexdigest()

            manifest = root / "manifest.csv"
            with manifest.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "berry_key","view_index","weight_g","category_id",
                        "crop_relative_path","crop_sha256","materialization_status",
                        "dataset_role","commercial_training_ready",
                    ],
                )
                writer.writeheader()
                writer.writerow({
                    "berry_key":"b1","view_index":"1","weight_g":"10",
                    "category_id":"0","crop_relative_path":"a.png","crop_sha256":digest,
                    "materialization_status":"MATERIALIZED",
                    "dataset_role":"NON_COMMERCIAL_REFERENCE",
                    "commercial_training_ready":"False",
                })

            baseline = root / "rgb-v001"
            baseline.mkdir()
            (baseline / "best.pt").write_bytes(b"checkpoint")
            (baseline / "rgb_baseline.json").write_text(
                json.dumps({
                    "status":"RGB_BASELINE_COMPLETE",
                    "model":"EFFICIENTNET_B0_IMAGENET",
                }),
                encoding="utf-8",
            )

            def fake_predictor(rows, **kwargs):
                return [{
                    "berry_key":"b1",
                    "view_index":"1",
                    "actual_weight_g":10.0,
                    "predicted_weight_g":9.5,
                    "category_id":"0",
                    "crop_relative_path":"a.png",
                }]

            report = run_dyson_external_rgb_benchmark(
                crop_manifest=manifest,
                crop_root=crop_root,
                rgb_baseline_dir=baseline,
                output_dir=root / "out",
                predictor=fake_predictor,
            )

            self.assertEqual(report["status"], "DYSON_EXTERNAL_RGB_BENCHMARK_COMPLETE")
            self.assertEqual(report["training_policy"], "NO_RETRAINING_NO_TUNING")
            self.assertEqual(report["benchmark_role"], "EXTERNAL_NON_COMMERCIAL_REFERENCE")
            self.assertFalse(report["commercial_training_ready"])
            self.assertEqual(report["eligible_crop_view_count"], 1)
            self.assertEqual(report["evaluated_berry_count"], 1)


if __name__ == "__main__":
    unittest.main()
