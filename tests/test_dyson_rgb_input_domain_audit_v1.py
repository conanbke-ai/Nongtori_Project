from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ml.weight_baseline.dyson_rgb_input_domain_audit_v1 import run_input_domain_audit


class DysonRgbInputDomainAuditTests(unittest.TestCase):
    def test_domain_shift_summary_uses_same_probe_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "snapshot"
            assets = root / "assets"
            snapshot.mkdir()
            assets.mkdir()

            dryad_file = assets / "dryad.png"
            dryad_file.write_bytes(b"x")
            import hashlib
            digest = hashlib.sha256(b"x").hexdigest()

            (snapshot / "WEIGHT_SNAPSHOT.json").write_text(
                json.dumps({
                    "status":"WEIGHT_SNAPSHOT_FROZEN",
                    "split_group":"FRUIT_ID",
                    "primary_target":"weight_with_calyx_g",
                    "image_count":22,
                    "fruit_count":1,
                    "materialized_asset_root":str(assets),
                }),
                encoding="utf-8",
            )
            with (snapshot / "sample-manifest.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["fruit_id","split","weight_with_calyx_g","relative_path","sha256"],
                )
                writer.writeheader()
                for index in range(22):
                    name = f"dryad-{index}.png"
                    path = assets / name
                    path.write_bytes(b"x")
                    writer.writerow({
                        "fruit_id":"f1","split":"test","weight_with_calyx_g":"10",
                        "relative_path":name,"sha256":digest,
                    })

            crop_root = root / "crops"
            crop_root.mkdir()
            crop = crop_root / "crop.png"
            crop.write_bytes(b"y")
            manifest = root / "crop-manifest.csv"
            with manifest.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "berry_key","crop_relative_path","materialization_status",
                        "dataset_role","commercial_training_ready",
                    ],
                )
                writer.writeheader()
                writer.writerow({
                    "berry_key":"b1","crop_relative_path":"crop.png",
                    "materialization_status":"MATERIALIZED",
                    "dataset_role":"NON_COMMERCIAL_REFERENCE",
                    "commercial_training_ready":"False",
                })

            def fake_probe(path: Path):
                is_dyson = path.name == "crop.png"
                base = 2.0 if is_dyson else 1.0
                return {
                    "source_width":100.0 * base,
                    "source_height":100.0,
                    "source_aspect_ratio":base,
                    "center_crop_retained_fraction":0.8,
                    "r_mean":0.4 * base,
                    "g_mean":0.3,
                    "b_mean":0.2,
                    "r_std":0.1,
                    "g_std":0.1,
                    "b_std":0.1,
                    "luminance_mean":0.3,
                    "luminance_std":0.1,
                    "saturation_mean":0.2,
                }

            report = run_input_domain_audit(
                dryad_snapshot_dir=snapshot,
                dyson_crop_manifest=manifest,
                dyson_crop_root=crop_root,
                output_dir=root / "out",
                probe=fake_probe,
            )

            self.assertEqual(report["status"], "DYSON_RGB_INPUT_DOMAIN_AUDIT_COMPLETE")
            self.assertEqual(report["dryad_test"]["image_count"], 22)
            self.assertEqual(report["dyson"]["image_count"], 1)
            self.assertGreater(
                report["metric_shift"]["source_aspect_ratio"]["mean_delta"],
                0,
            )
            self.assertEqual(report["preprocessing_contract"]["center_crop"], 224)


if __name__ == "__main__":
    unittest.main()
