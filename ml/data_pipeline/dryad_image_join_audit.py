from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .dryad_acquisition import (
    DryadAccessError,
    fetch_file_range,
    sha256_file,
    resolve_access_token,
    resolve_manifest,
)
from .dryad_weight_audit import EXPECTED_VIEWS_PER_FRUIT, fruit_ids_from_datasheet


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
IMAGE_JOIN_AUDIT_SCHEMA_VERSION = 1


class RemoteZipRangeReader(io.RawIOBase):
    def __init__(
        self,
        record: dict[str, Any],
        *,
        access_token: str,
        timeout: int = 120,
        min_chunk_size: int = 1024 * 1024,
        fetcher: Callable[..., bytes] = fetch_file_range,
    ) -> None:
        self.record = record
        self.size = int(record.get("size") or 0)
        if self.size <= 0:
            raise DryadAccessError("Dryad archive manifest has no positive size")
        self.access_token = access_token
        self.timeout = timeout
        self.min_chunk_size = max(64 * 1024, int(min_chunk_size))
        self.fetcher = fetcher
        self.position = 0
        self.cache_start = -1
        self.cache = b""

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            target = offset
        elif whence == io.SEEK_CUR:
            target = self.position + offset
        elif whence == io.SEEK_END:
            target = self.size + offset
        else:
            raise ValueError("invalid whence")
        if target < 0:
            raise ValueError("negative seek position")
        self.position = min(target, self.size)
        return self.position

    def _read_cached(self, n: int) -> bytes | None:
        if self.cache_start < 0:
            return None
        rel = self.position - self.cache_start
        if rel < 0 or rel >= len(self.cache):
            return None
        available = len(self.cache) - rel
        if available <= 0:
            return None
        take = min(n, available)
        return self.cache[rel : rel + take]

    def read(self, n: int = -1) -> bytes:
        if self.position >= self.size:
            return b""
        if n is None or n < 0:
            n = self.size - self.position
        n = min(n, self.size - self.position)
        if n <= 0:
            return b""

        cached = self._read_cached(n)
        if cached is not None and len(cached) >= n:
            self.position += len(cached)
            return cached

        fetch_len = max(n, self.min_chunk_size)
        end = min(self.size - 1, self.position + fetch_len - 1)
        payload = self.fetcher(
            self.record,
            self.position,
            end,
            access_token=self.access_token,
            timeout=self.timeout,
        )
        self.cache_start = self.position
        self.cache = payload
        out = payload[:n]
        self.position += len(out)
        return out


def _picture_records(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = [
        record
        for record in files
        if str(record.get("path") or "").lower().startswith("pictures_")
        and str(record.get("path") or "").lower().endswith(".zip")
    ]
    records.sort(key=lambda item: str(item.get("path") or ""))
    return records


def build_image_join_cache_identity(
    datasheet: Path,
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    records = _picture_records(files)
    archive_identity = [
        {
            "path": str(record.get("path") or ""),
            "size": int(record.get("size") or 0),
            "digest_type": str(record.get("digestType") or ""),
            "digest": str(record.get("digest") or ""),
        }
        for record in records
    ]
    identity = {
        "schema_version": IMAGE_JOIN_AUDIT_SCHEMA_VERSION,
        "datasheet_sha256": sha256_file(datasheet),
        "expected_views_per_fruit": EXPECTED_VIEWS_PER_FRUIT,
        "picture_archives": archive_identity,
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **identity,
        "fingerprint": hashlib.sha256(encoded).hexdigest(),
    }


def load_cached_image_join_report(
    output: Path,
    *,
    datasheet: Path,
    files: list[dict[str, Any]],
) -> dict[str, Any] | None:
    output = Path(output)
    if not output.exists():
        return None
    try:
        report = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    current = build_image_join_cache_identity(datasheet, files)
    cached = report.get("cache_identity")
    if not isinstance(cached, dict):
        return None
    if cached.get("fingerprint") != current["fingerprint"]:
        return None
    if cached.get("schema_version") != IMAGE_JOIN_AUDIT_SCHEMA_VERSION:
        return None
    return report


def list_remote_zip_names(
    record: dict[str, Any],
    *,
    access_token: str,
    timeout: int = 120,
    min_chunk_size: int = 1024 * 1024,
) -> list[str]:
    reader = RemoteZipRangeReader(
        record,
        access_token=access_token,
        timeout=timeout,
        min_chunk_size=min_chunk_size,
    )
    try:
        with zipfile.ZipFile(reader) as archive:
            return [info.filename for info in archive.infolist() if not info.is_dir()]
    except zipfile.BadZipFile as exc:
        raise DryadAccessError(
            f"Dryad archive central directory could not be read for {record.get('path')}: {exc}"
        ) from exc


def infer_fruit_id(filename: str, known_ids: set[str]) -> tuple[str | None, str]:
    basename = Path(filename).name
    tokens = re.findall(r"(?<!\d)(\d{4})(?!\d)", basename)
    candidates = sorted({token for token in tokens if token in known_ids})
    if len(candidates) == 1:
        return candidates[0], "MATCHED"
    if not candidates:
        return None, "UNMATCHED"
    return None, "AMBIGUOUS"


def audit_filename_inventory(
    archive_names: dict[str, list[str]],
    *,
    fruit_ids: list[str],
) -> dict[str, Any]:
    known = set(fruit_ids)
    counts: Counter[str] = Counter()
    unmatched: list[dict[str, str]] = []
    ambiguous: list[dict[str, str]] = []
    image_count = 0

    per_archive: list[dict[str, Any]] = []
    for archive_name, names in sorted(archive_names.items()):
        archive_images = 0
        archive_matched = 0
        for name in names:
            if Path(name).suffix.lower() not in _IMAGE_EXTENSIONS:
                continue
            image_count += 1
            archive_images += 1
            fruit_id, status = infer_fruit_id(name, known)
            if status == "MATCHED" and fruit_id is not None:
                counts[fruit_id] += 1
                archive_matched += 1
            elif status == "AMBIGUOUS":
                if len(ambiguous) < 100:
                    ambiguous.append({"archive": archive_name, "filename": name})
            else:
                if len(unmatched) < 100:
                    unmatched.append({"archive": archive_name, "filename": name})
        per_archive.append(
            {
                "archive": archive_name,
                "entry_count": len(names),
                "image_count": archive_images,
                "matched_image_count": archive_matched,
            }
        )

    wrong_view_counts = {
        fruit_id: counts.get(fruit_id, 0)
        for fruit_id in fruit_ids
        if counts.get(fruit_id, 0) != EXPECTED_VIEWS_PER_FRUIT
    }
    missing_fruit_ids = [
        fruit_id for fruit_id in fruit_ids if counts.get(fruit_id, 0) == 0
    ]

    expected_images = len(fruit_ids) * EXPECTED_VIEWS_PER_FRUIT
    matched_image_count = sum(counts.values())
    status = (
        "JOIN_VERIFIED"
        if image_count == expected_images
        and matched_image_count == expected_images
        and not wrong_view_counts
        and not unmatched
        and not ambiguous
        else "REVIEW_REQUIRED"
    )

    return {
        "status": status,
        "fruit_id_count": len(fruit_ids),
        "expected_views_per_fruit": EXPECTED_VIEWS_PER_FRUIT,
        "expected_image_count": expected_images,
        "image_count": image_count,
        "matched_image_count": matched_image_count,
        "unmatched_image_count": image_count - matched_image_count,
        "missing_fruit_id_count": len(missing_fruit_ids),
        "wrong_view_count_fruit_count": len(wrong_view_counts),
        "missing_fruit_ids_sample": missing_fruit_ids[:100],
        "wrong_view_counts_sample": dict(list(sorted(wrong_view_counts.items()))[:100]),
        "unmatched_filename_sample": unmatched,
        "ambiguous_filename_sample": ambiguous,
        "per_archive": per_archive,
    }


def audit_remote_picture_archives(
    datasheet: Path,
    *,
    dataset: dict[str, Any] | None = None,
    files: list[dict[str, Any]] | None = None,
    timeout: int = 120,
    min_chunk_size: int = 1024 * 1024,
) -> dict[str, Any]:
    fruit_ids = fruit_ids_from_datasheet(datasheet)
    if dataset is None or files is None:
        dataset, files = resolve_manifest(timeout=min(timeout, 60))
    records = _picture_records(files)
    if len(records) != 7:
        raise DryadAccessError(
            f"Expected 7 Dryad picture archives, found {len(records)}"
        )
    token = resolve_access_token(timeout=min(timeout, 60))
    archive_names: dict[str, list[str]] = {}
    archive_meta: list[dict[str, Any]] = []
    for record in records:
        name = str(record.get("path") or "")
        names = list_remote_zip_names(
            record,
            access_token=token,
            timeout=timeout,
            min_chunk_size=min_chunk_size,
        )
        archive_names[name] = names
        archive_meta.append(
            {
                "archive": name,
                "size": int(record.get("size") or 0),
                "entry_count": len(names),
            }
        )

    audit = audit_filename_inventory(archive_names, fruit_ids=fruit_ids)
    return {
        "dataset_doi": dataset.get("identifier") or dataset.get("doi"),
        "mode": "REMOTE_ZIP_CENTRAL_DIRECTORY_ONLY",
        "full_archive_download_performed": False,
        "cache_identity": build_image_join_cache_identity(datasheet, files),
        "archive_count": len(records),
        "archives": archive_meta,
        "audit": audit,
    }


def write_image_join_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
