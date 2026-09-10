from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def audit_directory(root: Path, output_dir: Path) -> dict[str, object]:
    root = Path(root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    hashes: Counter[str] = Counter()
    extensions: Counter[str] = Counter()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest = sha256_file(path)
        size = path.stat().st_size
        suffix = path.suffix.lower() or "<none>"
        hashes[digest] += 1
        extensions[suffix] += 1
        rows.append({
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": size,
            "sha256": digest,
            "extension": suffix,
            "empty": size == 0,
        })
    manifest_path = output_dir / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["relative_path", "size_bytes", "sha256", "extension", "empty"])
        writer.writeheader()
        writer.writerows(rows)
    duplicate_hashes = {key: count for key, count in hashes.items() if count > 1}
    report = {
        "root": str(root),
        "file_count": len(rows),
        "total_bytes": sum(int(row["size_bytes"]) for row in rows),
        "empty_files": sum(bool(row["empty"]) for row in rows),
        "duplicate_hash_groups": len(duplicate_hashes),
        "extensions": dict(sorted(extensions.items())),
        "status": "AUDITED" if rows and not any(row["empty"] for row in rows) else "REVIEW_REQUIRED",
    }
    (output_dir / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
