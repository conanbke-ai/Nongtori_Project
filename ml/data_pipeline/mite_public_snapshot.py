from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .mite_public_acquisition import BOUNDARY_EPSILON, _origin_key, _sha256
from .split import _bucket, _choose_split


FIELD_SOURCE_ID = "DATA-PEST-001"
MORPH_SOURCE_ID = "DATA-PEST-002"
FIELD_SNAPSHOT_ID = "MITE-PUBLIC-FIELD-CONTEXT-V001"
MORPH_SNAPSHOT_ID = "MITE-PUBLIC-MORPHOLOGY-V001"


class _UnionFind:
    def __init__(self, items: list[str]):
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            nxt = self.parent[item]
            self.parent[item] = root
            item = nxt
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _is_valid_yolo_line(line: str) -> tuple[bool, int | None]:
    parts = line.split()
    if len(parts) != 5:
        return False, None
    try:
        class_id = int(parts[0])
        xc, yc, bw, bh = [float(v) for v in parts[1:]]
    except ValueError:
        return False, None
    x1 = xc - bw / 2.0
    y1 = yc - bh / 2.0
    x2 = xc + bw / 2.0
    y2 = yc + bh / 2.0
    valid = (
        bw > 0
        and bh > 0
        and xc >= -BOUNDARY_EPSILON
        and yc >= -BOUNDARY_EPSILON
        and xc <= 1.0 + BOUNDARY_EPSILON
        and yc <= 1.0 + BOUNDARY_EPSILON
        and x1 >= -BOUNDARY_EPSILON
        and y1 >= -BOUNDARY_EPSILON
        and x2 <= 1.0 + BOUNDARY_EPSILON
        and y2 <= 1.0 + BOUNDARY_EPSILON
    )
    return valid, class_id


def _read_audit_manifest(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _dataset_root(summary: dict[str, Any], source_id: str) -> Path:
    return Path(summary["sources"][source_id]["dataset_root"])


def _build_atomic_components(rows: list[dict[str, str]]) -> dict[str, str]:
    keys = [row["image"] for row in rows]
    uf = _UnionFind(keys)

    by_origin: defaultdict[str, list[str]] = defaultdict(list)
    by_hash: defaultdict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_origin[row["origin_key"]].append(row["image"])
        by_hash[row["image_sha256"]].append(row["image"])

    for groups in (by_origin, by_hash):
        for members in groups.values():
            head = members[0]
            for member in members[1:]:
                uf.union(head, member)

    components: defaultdict[str, list[str]] = defaultdict(list)
    for item in keys:
        components[uf.find(item)].append(item)

    result: dict[str, str] = {}
    for members in components.values():
        canonical = sorted(members)[0]
        group_id = hashlib.sha256(("mite-public-v001|" + canonical).encode("utf-8")).hexdigest()[:20]
        for member in members:
            result[member] = group_id
    return result


def _write_snapshot(
    *,
    snapshot_id: str,
    source_id: str,
    dataset_root: Path,
    audit_manifest: Path,
    snapshot_root: Path,
    preserve_source_split: bool,
    seed: str,
) -> dict[str, Any]:
    output = Path(snapshot_root) / snapshot_id
    if output.exists():
        raise FileExistsError(f"immutable snapshot already exists: {output}")
    labels_root = output / "labels"
    labels_root.mkdir(parents=True)

    rows = _read_audit_manifest(audit_manifest)
    atomic_groups = (
        {row["image"]: row["origin_key"] for row in rows}
        if preserve_source_split
        else _build_atomic_components(rows)
    )

    output_rows: list[dict[str, Any]] = []
    split_counts: Counter[str] = Counter()
    valid_box_counts: Counter[str] = Counter()
    excluded_box_counts: Counter[str] = Counter()
    class_counts: Counter[int] = Counter()
    group_splits: dict[str, str] = {}
    hash_splits: dict[str, str] = {}

    for row in rows:
        source_split = row["split"]
        image_rel = row["image"]
        label_rel = row["label"]
        image_path = dataset_root / Path(image_rel)
        label_path = dataset_root / Path(label_rel)

        atomic_group = atomic_groups[image_rel]
        if preserve_source_split:
            split = source_split
        else:
            split = group_splits.setdefault(
                atomic_group,
                _choose_split(_bucket(atomic_group, seed), 0.70, 0.15),
            )

        previous_group_split = group_splits.setdefault(atomic_group, split)
        if previous_group_split != split:
            raise RuntimeError(f"atomic group leakage: {atomic_group}")

        image_sha = row["image_sha256"]
        previous_hash_split = hash_splits.setdefault(image_sha, split)
        if previous_hash_split != split:
            raise RuntimeError(f"exact hash leakage: {image_sha}")

        valid_lines: list[str] = []
        excluded = 0
        for raw in label_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line:
                continue
            valid, class_id = _is_valid_yolo_line(line)
            if not valid:
                excluded += 1
                continue
            valid_lines.append(line)
            if class_id is not None:
                class_counts[class_id] += 1

        clean_label_rel = Path(split) / Path(label_rel).name
        clean_label_path = labels_root / clean_label_rel
        clean_label_path.parent.mkdir(parents=True, exist_ok=True)
        clean_label_path.write_text(
            ("\n".join(valid_lines) + "\n") if valid_lines else "",
            encoding="utf-8",
        )

        split_counts[split] += 1
        valid_box_counts[split] += len(valid_lines)
        excluded_box_counts[split] += excluded

        output_rows.append({
            "source_id": source_id,
            "source_split": source_split,
            "split": split,
            "atomic_group": atomic_group,
            "image": image_rel,
            "source_label": label_rel,
            "snapshot_label": str(clean_label_rel).replace("\\", "/"),
            "image_sha256": image_sha,
            "valid_bbox_count": len(valid_lines),
            "excluded_bbox_count": excluded,
        })

    manifest_path = output / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0].keys()))
        writer.writeheader()
        writer.writerows(output_rows)

    manifest_sha = _sha256(manifest_path)
    descriptor = {
        "snapshot_id": snapshot_id,
        "status": "SNAPSHOT_READY",
        "source_id": source_id,
        "dataset_root": str(dataset_root),
        "source_images_are_read_only": True,
        "image_integrity": "SHA256_FROZEN",
        "annotation_policy": "COPY_VALID_YOLO_ROWS_EXCLUDE_INVALID_ZERO_OR_OUT_OF_RANGE_BOXES",
        "split_policy": (
            "PRESERVE_SOURCE_SPLIT"
            if preserve_source_split
            else "REASSIGN_BY_CONNECTED_ORIGIN_AND_EXACT_HASH_GROUP_70_15_15"
        ),
        "seed": seed,
        "image_count": len(output_rows),
        "valid_bbox_count": sum(valid_box_counts.values()),
        "excluded_bbox_count": sum(excluded_box_counts.values()),
        "split_image_counts": dict(sorted(split_counts.items())),
        "split_valid_bbox_counts": dict(sorted(valid_box_counts.items())),
        "split_excluded_bbox_counts": dict(sorted(excluded_box_counts.items())),
        "class_id_counts": {str(k): v for k, v in sorted(class_counts.items())},
        "manifest_sha256": manifest_sha,
        "field_acceptance": "NOT_ESTABLISHED",
        "public_test_policy": "DO_NOT_USE_FOR_NONGTORI_FIELD_READINESS_CLAIM",
    }
    (output / "SNAPSHOT.json").write_text(
        json.dumps(descriptor, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return descriptor


def build_mite_public_snapshots(
    *,
    audit_summary: Path = Path("data/audit/mite-public-v001/summary.json"),
    audit_root: Path = Path("data/audit/mite-public-v001"),
    snapshot_root: Path = Path("data/snapshots"),
) -> dict[str, Any]:
    summary = json.loads(Path(audit_summary).read_text(encoding="utf-8"))

    field = _write_snapshot(
        snapshot_id=FIELD_SNAPSHOT_ID,
        source_id=FIELD_SOURCE_ID,
        dataset_root=_dataset_root(summary, FIELD_SOURCE_ID),
        audit_manifest=Path(audit_root) / FIELD_SOURCE_ID / "image-manifest.csv",
        snapshot_root=snapshot_root,
        preserve_source_split=True,
        seed="mite-public-field-v001",
    )
    morphology = _write_snapshot(
        snapshot_id=MORPH_SNAPSHOT_ID,
        source_id=MORPH_SOURCE_ID,
        dataset_root=_dataset_root(summary, MORPH_SOURCE_ID),
        audit_manifest=Path(audit_root) / MORPH_SOURCE_ID / "image-manifest.csv",
        snapshot_root=snapshot_root,
        preserve_source_split=False,
        seed="mite-public-morphology-v001",
    )
    result = {
        "status": "MITE_PUBLIC_SNAPSHOTS_READY",
        "snapshots": {
            FIELD_SNAPSHOT_ID: field,
            MORPH_SNAPSHOT_ID: morphology,
        },
        "policy": {
            "roles_merged": False,
            "field_acceptance": "NOT_ESTABLISHED",
        },
    }
    Path(snapshot_root).mkdir(parents=True, exist_ok=True)
    (Path(snapshot_root) / "MITE-PUBLIC-V001-SUMMARY.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result
