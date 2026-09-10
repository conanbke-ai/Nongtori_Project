from __future__ import annotations

import csv
from pathlib import Path

DEDUP_EXTRA_COLUMNS = ["dedup_status", "duplicate_of"]


def deduplicate_manifest(input_path: Path, output_path: Path) -> dict[str, int]:
    with Path(input_path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("normalized manifest has no header")
        rows = list(reader)
        fieldnames = list(reader.fieldnames)

    seen_hashes: dict[str, str] = {}
    unique = duplicate = 0
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames + DEDUP_EXTRA_COLUMNS)
        writer.writeheader()
        for row in rows:
            digest = (row.get("content_sha256") or "").strip().lower()
            sample_id = (row.get("sample_id") or "").strip()
            if digest and digest in seen_hashes:
                row["dedup_status"] = "DUPLICATE"
                row["duplicate_of"] = seen_hashes[digest]
                duplicate += 1
            else:
                row["dedup_status"] = "UNIQUE"
                row["duplicate_of"] = ""
                unique += 1
                if digest:
                    seen_hashes[digest] = sample_id
            writer.writerow(row)
    return {"total": len(rows), "unique": unique, "duplicate": duplicate}
