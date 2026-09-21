from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .dryad_acquisition import DEFAULT_DATASET_DOI, file_id, resolve_manifest

EXPECTED_DATASHEET = "datasheet.xlsx"
EXPECTED_PICTURES = tuple(f"Pictures_{index:02d}.zip" for index in range(1, 8))
EXPECTED_SCANS = tuple(f"Scans_{index:02d}.zip" for index in range(1, 21))
EXPECTED_PATHS = (EXPECTED_DATASHEET, *EXPECTED_PICTURES, *EXPECTED_SCANS)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _normalized_record(record: dict[str, Any]) -> dict[str, Any]:
    path = str(record.get("path") or "")
    digest_type = str(record.get("digestType") or "").strip().lower()
    digest = str(record.get("digest") or "").strip().lower()
    size_raw = record.get("size")
    try:
        size = int(size_raw)
    except (TypeError, ValueError):
        size = None

    try:
        dryad_file_id = file_id(record)
    except Exception:
        dryad_file_id = None

    return {
        "path": path,
        "file_id": dryad_file_id,
        "size": size,
        "digest_type": digest_type,
        "digest": digest,
    }


def _canonical_rows_sha256(rows: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        sorted(rows, key=lambda item: (item["path"], item["file_id"] or "")),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def audit_manifest_records(
    dataset: dict[str, Any],
    files: list[dict[str, Any]],
    *,
    doi: str = DEFAULT_DATASET_DOI,
) -> dict[str, Any]:
    rows = [_normalized_record(record) for record in files]
    expected = set(EXPECTED_PATHS)
    path_counts = Counter(row["path"] for row in rows)
    id_counts = Counter(row["file_id"] for row in rows if row["file_id"])
    digest_to_paths: dict[str, list[str]] = defaultdict(list)

    missing_paths = sorted(path for path in expected if path_counts[path] == 0)
    duplicate_paths = sorted(path for path, count in path_counts.items() if count > 1)
    unexpected_paths = sorted(path for path in path_counts if path not in expected)
    duplicate_file_ids = sorted(file_id_ for file_id_, count in id_counts.items() if count > 1)

    invalid_sizes: list[dict[str, Any]] = []
    invalid_digests: list[dict[str, Any]] = []
    for row in rows:
        if row["size"] is None or row["size"] <= 0:
            invalid_sizes.append({"path": row["path"], "size": row["size"]})

        digest_type = row["digest_type"]
        digest = row["digest"]
        if digest_type not in {"sha-256", "sha256"} or not _SHA256_RE.fullmatch(digest):
            invalid_digests.append(
                {
                    "path": row["path"],
                    "digest_type": digest_type or None,
                    "digest": digest or None,
                }
            )
        else:
            digest_to_paths[digest].append(row["path"])

    duplicate_digests = [
        {"digest": digest, "paths": sorted(paths)}
        for digest, paths in sorted(digest_to_paths.items())
        if len(paths) > 1
    ]

    category_counts = {
        "datasheet": sum(1 for row in rows if row["path"] == EXPECTED_DATASHEET),
        "pictures": sum(1 for row in rows if row["path"] in EXPECTED_PICTURES),
        "scans": sum(1 for row in rows if row["path"] in EXPECTED_SCANS),
        "unexpected": sum(1 for row in rows if row["path"] not in expected),
    }

    checks = {
        "expected_file_count": len(EXPECTED_PATHS),
        "actual_file_count": len(rows),
        "file_count_match": len(rows) == len(EXPECTED_PATHS),
        "all_expected_paths_present": not missing_paths,
        "no_duplicate_paths": not duplicate_paths,
        "no_unexpected_paths": not unexpected_paths,
        "all_file_ids_present": all(row["file_id"] for row in rows),
        "no_duplicate_file_ids": not duplicate_file_ids,
        "all_sizes_positive": not invalid_sizes,
        "all_digests_sha256": not invalid_digests,
        "no_duplicate_sha256": not duplicate_digests,
    }
    verified = all(checks.values())

    return {
        "source_id": "DATA-QUAL-002",
        "dataset_doi": dataset.get("identifier") or dataset.get("doi") or doi,
        "publication_date": dataset.get("publicationDate"),
        "version_number": dataset.get("versionNumber"),
        "status": "MANIFEST_VERIFIED" if verified else "MANIFEST_REVIEW_REQUIRED",
        "checks": checks,
        "category_counts": category_counts,
        "missing_paths": missing_paths,
        "duplicate_paths": duplicate_paths,
        "unexpected_paths": unexpected_paths,
        "duplicate_file_ids": duplicate_file_ids,
        "invalid_sizes": invalid_sizes,
        "invalid_digests": invalid_digests,
        "duplicate_sha256": duplicate_digests,
        "manifest_rows_sha256": _canonical_rows_sha256(rows),
        "files": sorted(rows, key=lambda item: item["path"]),
    }


def audit_official_manifest(
    *,
    doi: str = DEFAULT_DATASET_DOI,
    timeout: int = 60,
) -> dict[str, Any]:
    dataset, files = resolve_manifest(doi, timeout=timeout)
    return audit_manifest_records(dataset, files, doi=doi)


def write_manifest_audit(report: dict[str, Any], output: Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
