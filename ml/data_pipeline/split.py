from __future__ import annotations

import csv
import hashlib
from pathlib import Path


def _bucket(group: str, seed: str) -> float:
    digest = hashlib.sha256(f"{seed}|{group}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _choose_split(value: float, train_ratio: float, val_ratio: float) -> str:
    if value < train_ratio:
        return "train"
    if value < train_ratio + val_ratio:
        return "validation"
    return "test"


def create_split_manifest(input_path: Path, output_path: Path, *, seed: str = "nongtori-v1", train_ratio: float = 0.70, val_ratio: float = 0.15, test_ratio: float = 0.15) -> dict[str, int]:
    if min(train_ratio, val_ratio, test_ratio) < 0 or abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-9:
        raise ValueError("split ratios must be non-negative and sum to 1")
    with Path(input_path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("dedup manifest has no header")
        rows = list(reader)
        fieldnames = list(reader.fieldnames)

    group_to_split: dict[str, str] = {}
    counts = {"train": 0, "validation": 0, "test": 0, "excluded": 0}
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames + ["split"])
        writer.writeheader()
        for row in rows:
            if row.get("dedup_status") == "DUPLICATE" or row.get("task_eligible") != "true":
                row["split"] = "excluded"
                counts["excluded"] += 1
                writer.writerow(row)
                continue
            group = (row.get("atomic_group") or row.get("sample_id") or "").strip()
            if not group:
                raise ValueError("eligible row requires atomic_group or sample_id")
            split = group_to_split.setdefault(group, _choose_split(_bucket(group, seed), train_ratio, val_ratio))
            row["split"] = split
            counts[split] += 1
            writer.writerow(row)
    verify_split_manifest(output_path)
    return counts


def verify_split_manifest(path: Path) -> None:
    groups: dict[str, str] = {}
    hashes: dict[str, str] = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            split = (row.get("split") or "").strip()
            if split == "excluded":
                continue
            group = (row.get("atomic_group") or row.get("sample_id") or "").strip()
            previous = groups.setdefault(group, split)
            if previous != split:
                raise ValueError(f"atomic-group leakage: {group} in {previous} and {split}")
            digest = (row.get("content_sha256") or "").strip().lower()
            if digest:
                previous_hash_split = hashes.setdefault(digest, split)
                if previous_hash_split != split:
                    raise ValueError(f"exact-duplicate leakage: sha256 {digest} in {previous_hash_split} and {split}")
