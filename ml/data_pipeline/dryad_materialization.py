from __future__ import annotations

import hashlib
import json
import os
import zlib
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .dryad_acquisition import DryadAccessError, resolve_access_token, resolve_manifest, sha256_file
from .dryad_image_join_audit import RemoteZipRangeReader

MATERIALIZATION_SCHEMA_VERSION = 1
VERIFIED_CANDIDATE_STATUS = "STRICT_CANDIDATE_MANIFEST_VERIFIED"
MATERIALIZED_STATUS = "STRICT_CANDIDATE_ASSETS_VERIFIED"


def load_candidate_manifest(path: Path) -> dict[str, Any]:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DryadAccessError(f"Cannot read strict candidate manifest: {exc}") from exc
    if payload.get("status") != VERIFIED_CANDIDATE_STATUS:
        raise DryadAccessError(
            f"Candidate manifest is not verified: {payload.get('status')!r}"
        )
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise DryadAccessError("Candidate manifest has no rows")
    if int(payload.get("image_count") or 0) != len(rows):
        raise DryadAccessError("Candidate manifest image_count does not match rows")
    return payload


def _safe_member_path(filename: str) -> PurePosixPath:
    member = PurePosixPath(filename.replace("\\", "/"))
    if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
        raise DryadAccessError(f"Unsafe ZIP member path: {filename!r}")
    return member


def _relative_output_path(row: dict[str, Any]) -> Path:
    archive = Path(str(row.get("archive_path") or "")).stem
    if not archive:
        raise DryadAccessError("Candidate row has no archive_path")
    member = _safe_member_path(str(row.get("filename") or ""))
    return Path(archive, *member.parts)


def _crc32_file(path: Path) -> str:
    crc = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            crc = zlib.crc32(chunk, crc)
    return f"{crc & 0xFFFFFFFF:08x}"


def _verify_existing(path: Path, row: dict[str, Any], expected_sha256: str | None) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    expected_size = int(row.get("file_size") or -1)
    if path.stat().st_size != expected_size:
        return None
    expected_crc = str(row.get("crc32") or "").lower()
    if expected_crc and _crc32_file(path) != expected_crc:
        return None
    digest = sha256_file(path)
    if expected_sha256 and digest != expected_sha256:
        return None
    return digest


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    with temp.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def _write_report_atomic(report: dict[str, Any], output: Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".part")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(output)


def _previous_sha_by_key(output: Path, candidate_rows_sha256: str) -> dict[tuple[str, str], str]:
    output = Path(output)
    if not output.exists():
        return {}
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if payload.get("candidate_rows_sha256") != candidate_rows_sha256:
        return {}
    result: dict[tuple[str, str], str] = {}
    for row in payload.get("files") or []:
        if not isinstance(row, dict):
            continue
        archive = str(row.get("archive_path") or "")
        filename = str(row.get("filename") or "")
        digest = str(row.get("sha256") or "")
        if archive and filename and len(digest) == 64:
            result[(archive, filename)] = digest
    return result


def _materialization_report(
    candidate: dict[str, Any],
    files: list[dict[str, Any]],
    *,
    root: Path,
    reused_count: int,
    downloaded_count: int,
    repaired_count: int,
    complete: bool,
) -> dict[str, Any]:
    return {
        "schema_version": MATERIALIZATION_SCHEMA_VERSION,
        "status": MATERIALIZED_STATUS if complete else "PARTIAL_MATERIALIZATION",
        "candidate_rows_sha256": candidate["rows_sha256"],
        "candidate_image_count": int(candidate["image_count"]),
        "root": str(root),
        "verified_file_count": len(files),
        "reused_count": reused_count,
        "downloaded_count": downloaded_count,
        "repaired_count": repaired_count,
        "files": files,
    }


def materialize_strict_candidates(
    candidate_manifest: Path,
    output_root: Path,
    output_manifest: Path,
    *,
    timeout: int = 120,
    range_chunk_mb: int = 32,
    checkpoint_every: int = 25,
    reader_factory: Callable[..., Any] = RemoteZipRangeReader,
) -> dict[str, Any]:
    candidate = load_candidate_manifest(candidate_manifest)
    rows = candidate["rows"]
    candidate_rows_sha256 = str(candidate["rows_sha256"])
    output_root = Path(output_root)
    output_manifest = Path(output_manifest)
    previous_sha = _previous_sha_by_key(output_manifest, candidate_rows_sha256)

    _, official_files = resolve_manifest(timeout=min(timeout, 60))
    picture_records = {
        str(record.get("path") or ""): record
        for record in official_files
        if str(record.get("path") or "").lower().startswith("pictures_")
        and str(record.get("path") or "").lower().endswith(".zip")
    }

    by_archive: dict[str, list[dict[str, Any]]] = defaultdict(list)
    relative_paths: set[str] = set()
    for row in rows:
        archive_path = str(row.get("archive_path") or "")
        record = picture_records.get(archive_path)
        if record is None:
            raise DryadAccessError(f"Official manifest lacks archive {archive_path!r}")
        expected_archive_digest = str(row.get("archive_sha256") or "").lower()
        actual_archive_digest = str(record.get("digest") or "").lower()
        if expected_archive_digest and actual_archive_digest != expected_archive_digest:
            raise DryadAccessError(f"Archive digest changed for {archive_path}")
        relative = _relative_output_path(row).as_posix()
        if relative in relative_paths:
            raise DryadAccessError(f"Duplicate output path in candidate manifest: {relative}")
        relative_paths.add(relative)
        by_archive[archive_path].append(row)

    access_token = resolve_access_token(timeout=min(timeout, 60))
    materialized: list[dict[str, Any]] = []
    reused_count = 0
    downloaded_count = 0
    repaired_count = 0

    for archive_path in sorted(by_archive):
        record = picture_records[archive_path]
        pending: list[tuple[dict[str, Any], Path, bool]] = []
        for row in by_archive[archive_path]:
            relative = _relative_output_path(row)
            destination = output_root / relative
            prior = previous_sha.get((archive_path, str(row["filename"])))
            verified = _verify_existing(destination, row, prior)
            if verified is not None:
                reused_count += 1
                materialized.append({
                    "fruit_id": row["fruit_id"],
                    "archive_path": archive_path,
                    "filename": row["filename"],
                    "relative_path": relative.as_posix(),
                    "size": int(row["file_size"]),
                    "crc32": str(row["crc32"]).lower(),
                    "sha256": verified,
                })
            else:
                pending.append((row, destination, destination.exists()))

        if pending:
            pending.sort(key=lambda item: int(item[0].get("header_offset") or 0))
            reader = reader_factory(
                record,
                access_token=access_token,
                timeout=timeout,
                min_chunk_size=max(1, range_chunk_mb) * 1024 * 1024,
                min_request_interval_seconds=0.25,
            )
            try:
                with zipfile.ZipFile(reader) as archive:
                    info_by_name = {info.filename: info for info in archive.infolist() if not info.is_dir()}
                    for row, destination, existed_before in pending:
                        filename = str(row["filename"])
                        info = info_by_name.get(filename)
                        if info is None:
                            raise DryadAccessError(
                                f"Candidate member disappeared from {archive_path}: {filename}"
                            )
                        payload = archive.read(info)
                        if len(payload) != int(row["file_size"]):
                            raise DryadAccessError(
                                f"Uncompressed size mismatch for {archive_path}:{filename}"
                            )
                        crc = f"{zlib.crc32(payload) & 0xFFFFFFFF:08x}"
                        if crc != str(row["crc32"]).lower():
                            raise DryadAccessError(
                                f"CRC32 mismatch for {archive_path}:{filename}"
                            )
                        digest = hashlib.sha256(payload).hexdigest()
                        _atomic_write(destination, payload)
                        if _verify_existing(destination, row, digest) != digest:
                            raise DryadAccessError(
                                f"Post-write verification failed for {destination}"
                            )
                        downloaded_count += 1
                        if existed_before:
                            repaired_count += 1
                        relative = _relative_output_path(row)
                        materialized.append({
                            "fruit_id": row["fruit_id"],
                            "archive_path": archive_path,
                            "filename": filename,
                            "relative_path": relative.as_posix(),
                            "size": int(row["file_size"]),
                            "crc32": crc,
                            "sha256": digest,
                        })
                        if checkpoint_every > 0 and len(materialized) % checkpoint_every == 0:
                            checkpoint = _materialization_report(
                                candidate,
                                sorted(materialized, key=lambda item: (item["fruit_id"], item["archive_path"], item["filename"])),
                                root=output_root,
                                reused_count=reused_count,
                                downloaded_count=downloaded_count,
                                repaired_count=repaired_count,
                                complete=False,
                            )
                            _write_report_atomic(checkpoint, output_manifest)
            except zipfile.BadZipFile as exc:
                raise DryadAccessError(
                    f"Cannot read remote ZIP for selective materialization: {archive_path}: {exc}"
                ) from exc

    materialized.sort(key=lambda item: (item["fruit_id"], item["archive_path"], item["filename"]))
    complete = len(materialized) == int(candidate["image_count"])
    report = _materialization_report(
        candidate,
        materialized,
        root=output_root,
        reused_count=reused_count,
        downloaded_count=downloaded_count,
        repaired_count=repaired_count,
        complete=complete,
    )
    _write_report_atomic(report, output_manifest)
    return report
