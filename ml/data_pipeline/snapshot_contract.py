from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_snapshot_manifest(manifest_path: Path, descriptor_path: Path) -> dict[str, Any]:
    descriptor = json.loads(Path(descriptor_path).read_text(encoding="utf-8"))
    actual_sha = sha256_file(manifest_path)
    with Path(manifest_path).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    eligible = [row for row in rows if row.get("snapshot_eligible") == "true"]
    split_counts = Counter(row.get("split", "") for row in eligible)
    maturity_counts = Counter(row.get("nongtori_maturity", "") for row in eligible)
    split_maturity: dict[str, Counter[str]] = defaultdict(Counter)
    for row in eligible:
        split_maturity[row.get("split", "")][row.get("nongtori_maturity", "")] += 1

    checks = {
        "manifest_sha256": actual_sha == descriptor["manifest_sha256"],
        "all_object_rows": len(rows) == descriptor["all_object_rows"],
        "snapshot_eligible_rows": len(eligible) == descriptor["snapshot_eligible_rows"],
        "split_counts": dict(split_counts) == descriptor["split_policy"]["actual_sample_counts"],
        "maturity_counts": dict(maturity_counts) == descriptor["maturity_counts"],
        "split_maturity_counts": {
            split: dict(counts) for split, counts in split_maturity.items()
        } == descriptor["split_policy"]["actual_maturity_counts"],
        "all_eligible_have_hash": all(bool(row.get("content_sha256")) for row in eligible),
        "all_eligible_have_split": all(row.get("split") in {"train", "valid", "test"} for row in eligible),
    }
    return {
        "snapshot_id": descriptor["snapshot_id"],
        "status": "MATCH" if all(checks.values()) else "MISMATCH",
        "checks": checks,
        "actual_manifest_sha256": actual_sha,
        "eligible_rows": len(eligible),
    }
