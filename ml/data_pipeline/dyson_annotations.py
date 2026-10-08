from __future__ import annotations

import csv
import hashlib
import json
import shutil
import stat
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .dyson_weight_reference import (
    DATASET_ROLE,
    LICENSE,
    SOURCE_ID,
    DysonPipelineError,
    is_macos_metadata_path,
    sha256_file,
)

ANNOTATION_REPO = "https://github.com/imanlab/strawberry-pp-w-r-dataset"
ANNOTATION_URL = (
    "https://raw.githubusercontent.com/imanlab/"
    "strawberry-pp-w-r-dataset/master/annotations/dyson_annotations.zip"
)
ANNOTATION_GIT_BLOB_SHA1 = "6f9263b45f9dc7c2456cbab3fbc52930136df105"
ANNOTATION_ARCHIVE_SIZE = 5_222_590

DEFAULT_ANNOTATION_ROOT = Path("data/external/icra-dyson-annotations")
DEFAULT_ANNOTATION_AUDIT_ROOT = Path("data/audit/icra-dyson-annotations")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_blob_sha1(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha1()
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_zip_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
    member = PurePosixPath(info.filename)
    if member.is_absolute() or ".." in member.parts:
        raise DysonPipelineError(
            f"unsafe path in Dyson annotation archive: {info.filename!r}"
        )
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        raise DysonPipelineError(
            f"symlink member is not allowed in Dyson annotation archive: {info.filename!r}"
        )
    parts = tuple(part for part in member.parts if part not in {"", "."})
    if not parts:
        raise DysonPipelineError(
            f"empty member path in Dyson annotation archive: {info.filename!r}"
        )
    return parts


def _download(
    url: str,
    destination: Path,
    *,
    timeout: int,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Nongtori-Dyson-Annotation-Audit/1.0"},
    )
    part = destination.with_name(destination.name + ".part")
    part.unlink(missing_ok=True)
    try:
        with opener(request, timeout=timeout) as response, part.open("wb") as sink:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                sink.write(chunk)
        part.replace(destination)
    except Exception:
        part.unlink(missing_ok=True)
        raise


def extract_dyson_annotations(
    archive_path: Path,
    extracted_root: Path,
) -> dict[str, Any]:
    archive_path = Path(archive_path)
    extracted_root = Path(extracted_root)
    extracted_root.mkdir(parents=True, exist_ok=True)

    extracted = 0
    reused = 0
    skipped_metadata = 0
    skipped_non_json = 0
    json_members = 0

    try:
        with zipfile.ZipFile(archive_path) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise DysonPipelineError(
                    f"CRC failure in Dyson annotation archive: {bad}"
                )
            for info in zf.infolist():
                if info.is_dir():
                    continue
                parts = _safe_zip_parts(info)
                member_path = Path(*parts)
                if is_macos_metadata_path(member_path):
                    skipped_metadata += 1
                    continue
                if member_path.suffix.lower() != ".json":
                    skipped_non_json += 1
                    continue

                json_members += 1
                destination = extracted_root.joinpath(*parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if (
                    destination.is_file()
                    and destination.stat().st_size == info.file_size
                ):
                    reused += 1
                    continue

                part = destination.with_name(destination.name + ".part")
                try:
                    with zf.open(info, "r") as source, part.open("wb") as sink:
                        shutil.copyfileobj(source, sink, length=1024 * 1024)
                    if part.stat().st_size != info.file_size:
                        raise DysonPipelineError(
                            f"annotation member size mismatch: {info.filename}"
                        )
                    part.replace(destination)
                    extracted += 1
                except Exception:
                    part.unlink(missing_ok=True)
                    raise
    except zipfile.BadZipFile as exc:
        raise DysonPipelineError(
            f"invalid Dyson annotation ZIP: {archive_path}"
        ) from exc

    return {
        "status": "DYSON_ANNOTATIONS_MATERIALIZED",
        "archive_path": str(archive_path),
        "extracted_root": str(extracted_root),
        "json_member_count": json_members,
        "extracted_json_count": extracted,
        "reused_json_count": reused,
        "skipped_macos_metadata_count": skipped_metadata,
        "skipped_non_json_count": skipped_non_json,
    }


def acquire_dyson_annotations(
    annotation_root: Path = DEFAULT_ANNOTATION_ROOT,
    audit_root: Path = DEFAULT_ANNOTATION_AUDIT_ROOT,
    *,
    url: str = ANNOTATION_URL,
    timeout: int = 120,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    annotation_root = Path(annotation_root)
    audit_root = Path(audit_root)
    annotation_root.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)

    archive_path = annotation_root / "dyson_annotations.zip"
    reuse = False
    if archive_path.is_file():
        reuse = (
            archive_path.stat().st_size == ANNOTATION_ARCHIVE_SIZE
            and _git_blob_sha1(archive_path) == ANNOTATION_GIT_BLOB_SHA1
        )
    if not reuse:
        _download(url, archive_path, timeout=timeout, opener=opener)

    actual_size = archive_path.stat().st_size
    if actual_size != ANNOTATION_ARCHIVE_SIZE:
        raise DysonPipelineError(
            f"Dyson annotation ZIP size mismatch: "
            f"{actual_size}/{ANNOTATION_ARCHIVE_SIZE}"
        )
    actual_blob_sha1 = _git_blob_sha1(archive_path)
    if actual_blob_sha1 != ANNOTATION_GIT_BLOB_SHA1:
        raise DysonPipelineError(
            "Dyson annotation ZIP Git blob SHA-1 mismatch: "
            f"{actual_blob_sha1}/{ANNOTATION_GIT_BLOB_SHA1}"
        )

    extraction = extract_dyson_annotations(
        archive_path,
        annotation_root / "extracted",
    )
    manifest = {
        "status": "DYSON_ANNOTATION_ACQUISITION_COMPLETE",
        "contract": "nongtori-dyson-annotations-acquisition.v1",
        "source_id": SOURCE_ID,
        "dataset_role": DATASET_ROLE,
        "license": LICENSE,
        "commercial_training_ready": False,
        "source_repository": ANNOTATION_REPO,
        "source_url": url,
        "expected_git_blob_sha1": ANNOTATION_GIT_BLOB_SHA1,
        "verified_git_blob_sha1": actual_blob_sha1,
        "archive_size_bytes": actual_size,
        "archive_sha256": sha256_file(archive_path),
        "reused_verified_archive": reuse,
        "retrieved_at": _utc_now(),
        "annotation_root": str(annotation_root),
        "extraction": extraction,
    }
    output = audit_root / "annotation-acquisition-manifest.json"
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


INTERESTING_KEY_TOKENS = (
    "bbox",
    "bound",
    "box",
    "keypoint",
    "category",
    "class",
    "label",
    "image",
    "file",
    "id",
    "segment",
    "point",
)


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def _walk_schema(
    value: Any,
    *,
    path: str,
    key_counts: Counter[str],
    interesting_keys: Counter[str],
    list_path_counts: Counter[str],
    list_dict_keysets: dict[str, Counter[str]],
    string_asset_values: list[dict[str, str]],
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            key_counts[key_text] += 1
            lowered = key_text.lower()
            if any(token in lowered for token in INTERESTING_KEY_TOKENS):
                interesting_keys[key_text] += 1
            child_path = f"{path}.{key_text}" if path else key_text
            _walk_schema(
                child,
                path=child_path,
                key_counts=key_counts,
                interesting_keys=interesting_keys,
                list_path_counts=list_path_counts,
                list_dict_keysets=list_dict_keysets,
                string_asset_values=string_asset_values,
            )
        return

    if isinstance(value, list):
        list_path_counts[path or "$"] += 1
        for child in value:
            if isinstance(child, dict):
                keyset = "|".join(sorted(str(key) for key in child))
                list_dict_keysets[path or "$"][keyset] += 1
            _walk_schema(
                child,
                path=f"{path}[]" if path else "$[]",
                key_counts=key_counts,
                interesting_keys=interesting_keys,
                list_path_counts=list_path_counts,
                list_dict_keysets=list_dict_keysets,
                string_asset_values=string_asset_values,
            )
        return

    if isinstance(value, str):
        lowered = value.lower()
        if lowered.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")):
            if len(string_asset_values) < 100:
                string_asset_values.append({"path": path, "value": value})


def audit_dyson_annotations(
    annotation_root: Path = DEFAULT_ANNOTATION_ROOT,
    audit_root: Path = DEFAULT_ANNOTATION_AUDIT_ROOT,
) -> dict[str, Any]:
    annotation_root = Path(annotation_root)
    audit_root = Path(audit_root)
    extracted_root = annotation_root / "extracted"
    if not extracted_root.is_dir():
        raise DysonPipelineError(
            f"Dyson annotation extraction root is missing: {extracted_root}. "
            "Run dyson-annotations-acquire first."
        )
    audit_root.mkdir(parents=True, exist_ok=True)

    json_paths = sorted(extracted_root.rglob("*.json"))
    if not json_paths:
        raise DysonPipelineError(
            f"Dyson annotation extraction contains no JSON files: {extracted_root}"
        )

    top_level_types: Counter[str] = Counter()
    top_level_keysets: Counter[str] = Counter()
    key_counts: Counter[str] = Counter()
    interesting_keys: Counter[str] = Counter()
    list_path_counts: Counter[str] = Counter()
    list_dict_keysets: dict[str, Counter[str]] = defaultdict(Counter)
    filename_stems: Counter[str] = Counter()
    string_asset_values: list[dict[str, str]] = []
    parse_errors: list[dict[str, str]] = []
    inventory_rows: list[dict[str, Any]] = []
    representative_documents: list[dict[str, Any]] = []

    for path in json_paths:
        relative = path.relative_to(extracted_root).as_posix()
        stem = path.stem
        filename_stems[stem] += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            parse_errors.append({"path": relative, "error": str(exc)})
            continue

        top_type = _json_type(payload)
        top_level_types[top_type] += 1
        if isinstance(payload, dict):
            top_keys = tuple(sorted(str(key) for key in payload))
            top_level_keysets["|".join(top_keys)] += 1
        else:
            top_keys = ()

        _walk_schema(
            payload,
            path="$",
            key_counts=key_counts,
            interesting_keys=interesting_keys,
            list_path_counts=list_path_counts,
            list_dict_keysets=list_dict_keysets,
            string_asset_values=string_asset_values,
        )

        inventory_rows.append(
            {
                "annotation_stem": stem,
                "relative_path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "top_level_type": top_type,
                "top_level_keys": "|".join(top_keys),
            }
        )
        if len(representative_documents) < 5:
            representative_documents.append(
                {
                    "relative_path": relative,
                    "payload": payload,
                }
            )

    inventory_path = audit_root / "annotation-inventory.csv"
    with inventory_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "annotation_stem",
            "relative_path",
            "size_bytes",
            "sha256",
            "top_level_type",
            "top_level_keys",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(inventory_rows)

    duplicate_stems = {
        stem: count
        for stem, count in filename_stems.items()
        if count > 1
    }
    list_keyset_summary = {
        path: [
            {"keyset": keyset, "count": count}
            for keyset, count in counts.most_common(20)
        ]
        for path, counts in sorted(list_dict_keysets.items())
    }

    report = {
        "status": (
            "DYSON_ANNOTATION_SCHEMA_AUDIT_COMPLETE"
            if not parse_errors
            else "DYSON_ANNOTATION_SCHEMA_AUDIT_WITH_PARSE_ERRORS"
        ),
        "contract": "nongtori-dyson-annotation-schema-audit.v1",
        "source_id": SOURCE_ID,
        "dataset_role": DATASET_ROLE,
        "license": LICENSE,
        "commercial_training_ready": False,
        "json_file_count": len(json_paths),
        "parsed_json_count": len(inventory_rows),
        "parse_error_count": len(parse_errors),
        "parse_errors": parse_errors[:50],
        "unique_filename_stem_count": len(filename_stems),
        "duplicate_filename_stem_count": len(duplicate_stems),
        "duplicate_filename_stems": dict(list(sorted(duplicate_stems.items()))[:50]),
        "top_level_type_counts": dict(sorted(top_level_types.items())),
        "top_level_keyset_counts": dict(top_level_keysets.most_common(20)),
        "interesting_key_counts": dict(interesting_keys.most_common(100)),
        "all_key_counts_top100": dict(key_counts.most_common(100)),
        "list_path_counts": dict(list_path_counts.most_common(100)),
        "list_dict_keysets": list_keyset_summary,
        "image_reference_values_sample": string_asset_values[:100],
        "representative_documents": representative_documents,
        "artifacts": {
            "annotation_inventory": str(inventory_path),
            "schema_audit": str(audit_root / "annotation-schema-audit.json"),
        },
        "note": (
            "Schema discovery is intentionally descriptive. No bbox/keypoint/category "
            "field is promoted into a canonical join until observed JSON structure is reviewed."
        ),
    }
    (audit_root / "annotation-schema-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
