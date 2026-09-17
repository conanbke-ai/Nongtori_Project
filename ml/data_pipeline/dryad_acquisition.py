from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DRYAD_API_BASE = "https://datadryad.org/api/v2"
DEFAULT_DATASET_DOI = "doi:10.25338/B8V308"
DEFAULT_DATASHEET_PATH = "datasheet.xlsx"


class DryadAccessError(RuntimeError):
    pass


class _DropAuthOnCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        old_host = urllib.parse.urlsplit(req.full_url).netloc.lower()
        new_host = urllib.parse.urlsplit(newurl).netloc.lower()
        if old_host != new_host:
            redirected.remove_header("Authorization")
        return redirected


_OPENER = urllib.request.build_opener(_DropAuthOnCrossHostRedirect())


def encode_doi(doi: str) -> str:
    normalized = doi if doi.startswith("doi:") else f"doi:{doi}"
    return urllib.parse.quote(normalized, safe="")


def _request_json(url: str, *, timeout: int = 60) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "Nongtori-Dryad/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def resolve_dataset(doi: str = DEFAULT_DATASET_DOI, *, timeout: int = 60) -> dict[str, Any]:
    return _request_json(f"{DRYAD_API_BASE}/datasets/{encode_doi(doi)}", timeout=timeout)


def _absolute_api_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return f"https://datadryad.org{href}"


def fetch_version_files(version_href: str, *, timeout: int = 60, per_page: int = 100) -> list[dict[str, Any]]:
    base = _absolute_api_url(version_href.rstrip("/") + "/files")
    files: list[dict[str, Any]] = []
    page = 1
    total: int | None = None
    while total is None or len(files) < total:
        separator = "&" if "?" in base else "?"
        payload = _request_json(f"{base}{separator}per_page={per_page}&page={page}", timeout=timeout)
        embedded = payload.get("_embedded", {}) or {}
        batch = embedded.get("stash:files", []) or []
        files.extend(batch)
        total = int(payload.get("total", len(files)))
        if not batch:
            break
        page += 1
    if total is not None and len(files) != total:
        raise DryadAccessError(f"Dryad file manifest incomplete: fetched {len(files)} of {total}")
    return files


def resolve_manifest(doi: str = DEFAULT_DATASET_DOI, *, timeout: int = 60) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    dataset = resolve_dataset(doi, timeout=timeout)
    links = dataset.get("_links", {}) or {}
    version = links.get("stash:version", {}) or {}
    version_href = version.get("href")
    if not version_href:
        raise DryadAccessError("Dryad dataset response has no stash:version link")
    return dataset, fetch_version_files(version_href, timeout=timeout)


def select_file(files: list[dict[str, Any]], path: str) -> dict[str, Any]:
    matches = [item for item in files if str(item.get("path", "")) == path]
    if len(matches) != 1:
        raise DryadAccessError(f"Expected exactly one Dryad file named {path!r}, found {len(matches)}")
    return matches[0]


def file_id(file_record: dict[str, Any]) -> str:
    links = file_record.get("_links", {}) or {}
    self_href = (links.get("self", {}) or {}).get("href", "")
    value = str(self_href).rstrip("/").rsplit("/", 1)[-1]
    if not value.isdigit():
        raise DryadAccessError(f"Cannot resolve Dryad file id from {self_href!r}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_download(path: Path, file_record: dict[str, Any]) -> dict[str, Any]:
    path = Path(path)
    expected_size = file_record.get("size")
    actual_size = path.stat().st_size
    if expected_size is not None and actual_size != int(expected_size):
        raise DryadAccessError(f"Dryad file size mismatch: got {actual_size}, expected {expected_size}")

    digest_type = str(file_record.get("digestType") or "").lower()
    expected_digest = str(file_record.get("digest") or "").lower()
    actual_digest = sha256_file(path)
    if expected_digest and digest_type in {"sha-256", "sha256"} and actual_digest != expected_digest:
        raise DryadAccessError("Dryad SHA-256 mismatch")

    return {
        "path": str(path),
        "size": actual_size,
        "sha256": actual_digest,
        "expected_sha256": expected_digest or None,
        "digest_verified": bool(expected_digest and digest_type in {"sha-256", "sha256"}),
    }


def download_file(
    file_record: dict[str, Any],
    output: Path,
    *,
    token: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    token = token or os.environ.get("DRYAD_TOKEN")
    if not token:
        raise DryadAccessError(
            "Dryad file bytes require DRYAD_TOKEN. Anonymous metadata access is sufficient for manifest audit, "
            "but not for file download."
        )

    fid = file_id(file_record)
    url = f"{DRYAD_API_BASE}/files/{fid}/download"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Nongtori-Dryad/1.0",
            "Authorization": f"Bearer {token}",
        },
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with _OPENER.open(request, timeout=timeout) as response, output.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    return verify_download(output, file_record)


def acquire_datasheet(
    output: Path,
    *,
    doi: str = DEFAULT_DATASET_DOI,
    token: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    dataset, files = resolve_manifest(doi, timeout=min(timeout, 60))
    record = select_file(files, DEFAULT_DATASHEET_PATH)
    verification = download_file(record, output, token=token, timeout=timeout)
    return {
        "dataset_doi": dataset.get("identifier") or dataset.get("doi") or doi,
        "publication_date": dataset.get("publicationDate"),
        "version_number": dataset.get("versionNumber"),
        "file": {
            "id": file_id(record),
            "path": record.get("path"),
            "size": record.get("size"),
            "mime_type": record.get("mimeType"),
            "digest_type": record.get("digestType"),
            "digest": record.get("digest"),
        },
        "verification": verification,
    }
