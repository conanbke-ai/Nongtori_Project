from __future__ import annotations

import csv
import json
from pathlib import Path

from ml.data_pipeline.snapshot_contract import sha256_file, verify_snapshot_manifest


def test_snapshot_contract_matches(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    fields = ["snapshot_eligible", "split", "nongtori_maturity", "content_sha256"]
    with manifest.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([
            {"snapshot_eligible": "true", "split": "train", "nongtori_maturity": "0", "content_sha256": "a" * 64},
            {"snapshot_eligible": "true", "split": "valid", "nongtori_maturity": "1", "content_sha256": "b" * 64},
            {"snapshot_eligible": "false", "split": "test", "nongtori_maturity": "", "content_sha256": "c" * 64},
        ])
    descriptor = tmp_path / "snapshot.json"
    descriptor.write_text(json.dumps({
        "snapshot_id": "TEST-V001",
        "manifest_sha256": sha256_file(manifest),
        "all_object_rows": 3,
        "snapshot_eligible_rows": 2,
        "maturity_counts": {"0": 1, "1": 1},
        "split_policy": {
            "actual_sample_counts": {"train": 1, "valid": 1},
            "actual_maturity_counts": {"train": {"0": 1}, "valid": {"1": 1}},
        },
    }), encoding="utf-8")
    result = verify_snapshot_manifest(manifest, descriptor)
    assert result["status"] == "MATCH"
    assert all(result["checks"].values())
