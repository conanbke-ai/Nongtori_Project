from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path


def _safe_target(root: Path, member_name: str) -> Path:
    root = root.resolve()
    target = (root / member_name).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"unsafe archive member path: {member_name}")
    return target


def extract_archive(archive: Path, output_dir: Path) -> tuple[Path, ...]:
    archive = Path(archive)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as handle:
            for member in handle.infolist():
                target = _safe_target(output_dir, member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with handle.open(member) as source, target.open("wb") as destination:
                    destination.write(source.read())
                extracted.append(target)
        return tuple(extracted)
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as handle:
            for member in handle.getmembers():
                if not member.isfile():
                    continue
                target = _safe_target(output_dir, member.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = handle.extractfile(member)
                if source is None:
                    continue
                with source, target.open("wb") as destination:
                    destination.write(source.read())
                extracted.append(target)
        return tuple(extracted)
    raise ValueError(f"unsupported archive: {archive.name}")
